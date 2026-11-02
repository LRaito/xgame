"""xgame 启动器：解压即用包的双击入口。

它做三件事，按顺序：

1. **自检**（缺 MSVC 运行库、SQLite 没有 FTS5、数据目录被 Docker 路线用过）；
2. **起服务**：进程内跑 uvicorn（不起子进程——Windows 上硬杀进程会把 SQLite 留在半路，
   而进程内跑时关窗口 / Ctrl+C 都能走优雅退出），顺带按环境变量让后端托管前端 dist；
3. **等它就绪**再打开浏览器，并打印本机与局域网两个地址。

配置文件是旁边的 `xgame.ini`（没有就用默认值建一份）。整个包不写注册表、不装服务、
不碰系统目录，删掉文件夹就算卸载。**包里没有任何自动升级的代码**：升级是手动的
（关窗口 → 解压新包 → 把 data 目录搬过去），步骤见 README.md 与 说明.txt。

这个文件在包里位于 `xgame/launcher.py`，与 `backend/`、`web/`、`python/` 同级。
"""

from __future__ import annotations

import configparser
import ctypes
import logging
import logging.handlers
import os
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INI_PATH = ROOT / "xgame.ini"
RUNTIME_DIR = ROOT / "runtime"
WEB_DIR_NAME = "web"
DEFAULT_PORT = 8910
STARTUP_TIMEOUT_SECONDS = 120

logger = logging.getLogger("xgame.launcher")


# ---------- 配置 ----------

_DEFAULTS = {
    "data_dir": "data",
    "host": "0.0.0.0",
    "port": str(DEFAULT_PORT),
    "open_browser": "yes",
}

_INI_TEMPLATE = """\
[xgame]
# 数据目录：账号、存档、截图、游戏本体与攻略包全在这里。
# 相对路径按本文件所在目录算；想让数据待在包外面（换新版本时更省事），
# 填绝对路径，例如：data_dir = D:\\xgame-data
# 也可以直接指向以前 WSL 那份数据（如 X:\\xgame），存档与截图会原样续用——
# 但**别和 Docker 路线同时开着**，两边一起写会把库写坏。
data_dir = data

# 运行时目录：数据库（db/app.db）与 H5/攻略的解包缓存都在这里。
# 不填就是 <data_dir>/runtime（跟着 data_dir 走），一般不用改。
# 解包缓存是派生物，删掉只会让下次播放/查看时重新解压一遍。
# runtime_dir = data\\runtime

# 监听地址：0.0.0.0 = 局域网里的手机、平板也能连；127.0.0.1 = 只有本机能连。
host = 0.0.0.0

# 端口。**改端口等于换了一个站点**：浏览器里的本地存档、模拟器设置都跟着端口走，
# 改了会觉得「档没了」，所以除非端口被占用，否则不要动它。
port = 8910

# 启动后自动打开浏览器：yes / no
open_browser = yes
"""


class Config:
    def __init__(self, parser: configparser.ConfigParser) -> None:
        section = parser["xgame"] if parser.has_section("xgame") else {}
        self.data_dir = self._path(section.get("data_dir", _DEFAULTS["data_dir"]))
        # 运行时目录没配时跟着数据目录走（与 Docker 的 STORAGE_ROOT / RUNTIME_ROOT 两个根同一个模型）
        raw_runtime = (section.get("runtime_dir") or "").strip()
        self.runtime_dir = (
            self._path(raw_runtime) if raw_runtime else self.data_dir / "runtime"
        )
        self.host = (section.get("host") or _DEFAULTS["host"]).strip()
        self.port = self._port(section.get("port", _DEFAULTS["port"]))
        self.open_browser = self._flag(section.get("open_browser", _DEFAULTS["open_browser"]))

    @staticmethod
    def _path(raw: str) -> Path:
        path = Path(raw.strip()).expanduser()
        return path if path.is_absolute() else (ROOT / path)

    @staticmethod
    def _port(raw: str) -> int:
        try:
            port = int(str(raw).strip())
        except ValueError:
            port = DEFAULT_PORT
        return port if 1 <= port <= 65535 else DEFAULT_PORT

    @staticmethod
    def _flag(raw: str) -> bool:
        return str(raw).strip().lower() in ("yes", "true", "1", "on")


def load_config() -> Config:
    if not INI_PATH.exists():
        INI_PATH.write_text(_INI_TEMPLATE, encoding="utf-8")
        logger.info("已生成默认配置：%s", INI_PATH)
    parser = configparser.ConfigParser()
    parser.read(INI_PATH, encoding="utf-8")
    return Config(parser)


# ---------- 输出 ----------


def say(message: str = "") -> None:
    if QUIET:
        logger.info(message)
        return
    print(message, flush=True)


def fatal(message: str) -> None:
    """启动失败：写日志 + 留一份 last-error.txt，安静模式下再弹个框（否则用户什么都看不到）。"""
    logger.error("启动失败：%s", message)
    try:
        (RUNTIME_DIR).mkdir(parents=True, exist_ok=True)
        (RUNTIME_DIR / "last-error.txt").write_text(message + "\n", encoding="utf-8")
    except OSError:
        pass
    say(f"\n[启动失败] {message}")
    if QUIET and os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "XGame 启动失败", 0x10)
        except Exception:  # noqa: BLE001 - 弹框失败也不能影响退出
            pass
    raise SystemExit(1)


# ---------- 自检 ----------


def check_runtime() -> None:
    """跑之前先确认几件「缺了会一脸茫然」的事。"""
    if os.name == "nt":
        try:
            ctypes.WinDLL("vcruntime140.dll")
        except OSError:
            fatal(
                "缺少 Windows 运行库 vcruntime140.dll。\n"
                "请安装「Microsoft Visual C++ 2015-2022 可再发行组件包 (x64)」后重试，"
                "或重新解压一份完整安装包。"
            )
    try:
        connection = sqlite3.connect(":memory:")
        with connection:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")
        connection.close()
    except sqlite3.Error:
        say("提示：本机 Python 的 SQLite 没有 FTS5，「游戏发现」的检索会一直显示尚未构建索引。")


def check_data_dir(data_dir: Path, *, label: str = "数据目录") -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".write-probe"
        probe.touch()
        probe.unlink()
    except OSError as exc:
        fatal(
            f"{label}用不了：{data_dir}\n"
            f"（{exc}）\n"
            "常见原因是路径指向了需要管理员权限的位置（如 C:\\Program Files 下）"
            "或盘符不存在。请改 xgame.ini 里的 data_dir / runtime_dir。"
        )
    marker = data_dir / ".mounted"
    if marker.exists() and label == "数据目录":
        say()
        say("!" * 62)
        say("注意：这个数据目录里有 .mounted 哨兵，说明它是 Docker/WSL 那条路线在用的。")
        say("两边同时打开同一份数据会把数据库写坏——请先执行 docker compose down，")
        say("或者把 xgame.ini 里的 data_dir 换成另一个目录。")
        say("!" * 62)


# ---------- 「来自 Internet」标记 ----------


def still_locked() -> bool:
    """包里那几个双击入口是否还带着「来自 Internet」标记（MOTW）。

    带标记时，**每双击一次 `.cmd`/`.bat`**，Windows 都会先弹一次「打开文件 - 安全警告：
    无法验证发布者」（点「运行」能继续，但每次都要点一次）。原因是这个 zip 从网上下载、
    被浏览器打了标记，解压工具又把标记复制给里面每一个文件——用户在解压**之前**右键 zip
    勾了「解除锁定」就不会这样。

    这件事只能提醒、不能替用户做：清标记要跑 PowerShell，而任何一个包内脚本自己就是
    被弹窗拦的那个。见 说明.txt 第一节与「解除锁定.bat」。
    """
    if os.name != "nt":
        return False
    for name in ("启动游戏平台.cmd", "解除锁定.bat"):
        try:
            # NTFS 备用数据流：带标记的文件都有它，没有就抛 FileNotFoundError
            os.stat(f"{ROOT / name}:Zone.Identifier")
        except OSError:
            continue
        return True
    return False


# ---------- 版本 ----------


def current_version() -> str:
    """包里那份 `version.txt`（构建时由 scripts/version.sh 写入），只用来在启动横幅上显示。"""
    path = ROOT / "version.txt"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "v0.0.0"


# ---------- 单实例 ----------


class SingleInstance:
    """同一台机器上只允许跑一个（按端口区分）。

    双击第二次不该起第二个服务：除了白占资源，两个进程打开同一个 SQLite 也更容易出事。
    已有实例在跑时，启动器只负责把浏览器打开。
    """

    def __init__(self, name: str) -> None:
        self._handle = None
        self._name = name

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        # 用 use_last_error=True + ctypes.get_last_error()：直接调 kernel32.GetLastError()
        # 会被 ctypes 自己的调用踩掉，拿到的可能不是 CreateMutexW 的错误码。
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._handle = kernel32.CreateMutexW(None, False, self._name)
        if not self._handle:
            return True  # 拿不到互斥体就当没在跑（宁可多起一个，也别误报「已经在运行」）
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


# ---------- 服务 ----------


# 内网网段排序：越像「家里的 Wi-Fi」越靠前。198.18/198.19 是 WSL 与 Hyper-V 用的
# 虚拟网段——只问系统「出口网卡是谁」时经常选到它，用户照着敲手机是连不上的。
_VIRTUAL_PREFIXES = ("198.18.", "198.19.")


def _usable_ip(ip: str) -> bool:
    return not ip.startswith(("127.", "169.254.", "0."))


def _ip_rank(ip: str) -> tuple[int, str]:
    if ip.startswith("192.168."):
        return (0, ip)
    if ip.startswith("10."):
        return (1, ip)
    first, second = (int(part) for part in ip.split(".")[:2])
    if first == 172 and 16 <= second <= 31:
        return (2, ip)
    if ip.startswith(_VIRTUAL_PREFIXES):
        return (4, ip)
    return (3, ip)


def local_ips() -> list[str]:
    """本机可能的局域网地址，可能不止一个，已按「像不像真实网卡」排好序。

    两条线索合起来用：UDP connect 让系统选出默认出口网卡（不真的发包），
    再加上主机名解析出来的地址。装了 Docker/WSL/Hyper-V 的机器上只靠前者会选到虚拟网卡。
    """
    found: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("223.5.5.5", 80))
        found.append(sock.getsockname()[0])
    except OSError:
        pass
    finally:
        sock.close()
    try:
        found.extend(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return sorted({ip for ip in found if _usable_ip(ip)}, key=_ip_rank)


def wait_ready(port: int, deadline: float) -> bool:
    """轮询 /health，直到服务就绪或超时。

    端口在 uvicorn 起来之前根本没监听，所以这里必须容忍连接被拒，而不是一次失败就判定挂了。
    """
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 - 本机固定地址
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    return False


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0


def say_addresses(config: Config) -> None:
    """打印本机与局域网两个地址。

    启动成功时和「已经在运行、不重复启动」时都用它——后者尤其要让用户看到地址，
    因为这时候浏览器不一定能自动打开（比如开机自启起的服务，根本没有窗口）。
    """
    say(f"  本机打开：http://127.0.0.1:{config.port}")
    if config.host != "0.0.0.0":
        return
    ips = local_ips()
    if not ips:
        return
    say(f"  局域网内（手机/平板）：http://{ips[0]}:{config.port}")
    for other in ips[1:]:
        say(f"    （上面那个连不上就试试 http://{other}:{config.port}）")
    say("  手机打不开就先双击一次「允许局域网访问.bat」（会弹一次权限确认）。")


def write_runtime_files(port: int) -> None:
    """记下正在用的端口。

    唯一的用途是「端口被占用」时判断：端口上有人应答、`runtime/port.txt` 又还在，
    那多半是另一个副本 / 另一个用户的会话在跑，而不是别的程序占了端口——两种情况给用户的
    提示完全不一样。正常退出会删掉它，硬杀（直接关窗口）会留下它。
    """
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "port.txt").write_text(str(port), encoding="utf-8")


def clear_runtime_files() -> None:
    try:
        (RUNTIME_DIR / "port.txt").unlink(missing_ok=True)
    except OSError:
        pass


def serve(config: Config) -> int:
    import uvicorn

    os.environ["STORAGE_ROOT"] = str(config.data_dir)
    # 运行时根：SQLite 库（db/app.db）与 H5/攻略的解包缓存。不设时后端会退回数据根，
    # 那样解包缓存会落进 data\game\... 里；显式设成 data\runtime 与 Docker 那条路线一致。
    os.environ["RUNTIME_ROOT"] = str(config.runtime_dir)
    os.environ["STATIC_DIR"] = str(ROOT / WEB_DIR_NAME)
    # 局域网走 http（自签证书对手机/平板等于没有），cookie 不能带 Secure，
    # 否则浏览器不保存它，表现是「登录看着成功、下一个请求就 401」。
    os.environ["SESSION_COOKIE_SECURE"] = "false"

    # 必须在这里才 import：backend.asgi 在导入时就 create_app()，配置是那一刻读的。
    # 也正是这次导入在建目录、建表、做备份、建检索索引，首次启动会明显卡一下。
    prepared_at = time.monotonic()
    from backend.asgi import app

    prepared = time.monotonic() - prepared_at
    if prepared > 3:
        say(f"已准备数据（{prepared:.0f} 秒）：建库、备份、检索索引。下次启动会快很多。")

    server = uvicorn.Server(
        uvicorn.Config(app, host=config.host, port=config.port, log_config=None, access_log=False)
    )

    # 进程内跑，不起子进程：Windows 上 terminate 是硬杀，SQLite 可能被留在半路；
    # 进程内跑时 Ctrl+C 能走优雅退出（关窗口是硬杀，但 SQLite 有日志、不会坏库）。
    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()

    open_url = f"http://127.0.0.1:{config.port}"
    if not wait_ready(config.port, time.monotonic() + STARTUP_TIMEOUT_SECONDS):
        fatal(
            f"服务在 {STARTUP_TIMEOUT_SECONDS} 秒内没能启动。\n"
            f"请查看日志：{config.data_dir / 'logs' / 'xgame.log'}"
        )

    say()
    say("=" * 62)
    say(f"  XGame {current_version()} 已经跑起来了")
    say_addresses(config)
    if config.host == "0.0.0.0":
        say("  同一个账号在不同地址下算两个站点，本地存档不互通，建议固定用一个地址。")
    say("  数据目录：" + str(config.data_dir))
    say("  关闭本窗口即停止服务。")
    say("=" * 62)
    say()

    if config.open_browser:
        webbrowser.open(open_url)

    try:
        while not server.should_exit:
            if not thread.is_alive():
                # 起来之后又死了（比如端口被抢、启动出错）：别在这儿死等
                return fatal("服务意外退出了。上面的日志和 data\\logs\\xgame.log 里有原因。")
            time.sleep(0.5)
    except KeyboardInterrupt:
        say("收到 Ctrl+C，正在停止服务……")
        server.should_exit = True
        thread.join(timeout=10)
    time.sleep(0.5)  # 给 server 一点时间收尾
    say("服务已停止。")
    return 0


# ---------- 入口 ----------

QUIET = False


def setup_logging(data_dir: Path) -> None:
    """日志同时写文件与控制台。

    写不了文件（数据目录权限有问题之类）不算致命：把服务跑起来更要紧，控制台上还有输出，
    启动失败的原因另外会留在 `runtime/last-error.txt`。
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        logs = data_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            logs / "xgame.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    except OSError as exc:
        say(f"提示：日志文件写不了（{exc}），这次只在窗口里输出。")
    if not QUIET:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root.addHandler(console)


# 这几个不是「启动服务」，而是包内那几个 .bat 入口要做的外壳动作（见 winops.py）
_ACTIONS = {
    "--create-shortcut": "create-shortcut",
    "--toggle-autostart": "toggle-autostart",
    "--unlock": "unlock",
}

_USAGE = "可用参数：" + " / ".join([*_ACTIONS, "--quiet", "--no-browser"])


def parse_args(argv: list[str]) -> dict:
    options = {"quiet": False, "no_browser": False, "action": None}
    for item in argv:
        if item in _ACTIONS:
            options["action"] = _ACTIONS[item]
        elif item == "--quiet":
            options["quiet"] = True
        elif item == "--no-browser":
            options["no_browser"] = True
        else:
            raise SystemExit(f"未知参数：{item}（{_USAGE}）")
    return options


def main(argv: list[str] | None = None) -> int:
    global QUIET

    options = parse_args(list(argv if argv is not None else sys.argv[1:]))
    QUIET = bool(options["quiet"])

    if hasattr(sys.stdout, "reconfigure"):  # cp936 控制台里也要能打出中文
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if options["action"]:
        # 快捷方式 / 开机自启 / 解除锁定：建 .lnk 要用 PowerShell，逻辑在 winops.py
        import winops

        say(winops.run_action(options["action"], ROOT))
        return 0

    config = load_config()
    if options["no_browser"]:
        config.open_browser = False

    # 自检放在配日志之前：数据目录用不了时（路径太深、没权限、盘符不对）要给的是一条能看懂
    # 的中文错误，而不是「建 logs 目录失败」的堆栈。
    check_runtime()
    check_data_dir(config.data_dir, label="数据目录")
    # 运行时目录放库与解包缓存，同样要先确认可写（库建不出来等于账号全没）
    check_data_dir(config.runtime_dir, label="运行时目录")
    setup_logging(config.data_dir)

    if still_locked():
        say()
        say("提示：这一份还带着「来自 Internet」标记，双击 .bat / .cmd 时 Windows 会先弹一次")
        say("      「无法验证发布者」。双击一次「解除锁定.bat」（只需一次）以后就不再弹了。")

    # 先确认没有第二个实例在跑。双击第二次不该起第二个服务（除了白占资源，两个进程打开
    # 同一个 SQLite 更容易出事）：这里只把地址告诉用户、顺手把浏览器打开。
    instance = SingleInstance(f"Local\\xgame-port-{config.port}")
    if not instance.acquire():
        say()
        say("XGame 已经在运行了，不用再开一个。")
        say_addresses(config)
        say()
        if config.open_browser:
            webbrowser.open(f"http://127.0.0.1:{config.port}")
        return 0

    if port_in_use(config.host, config.port):
        hint = ""
        if (RUNTIME_DIR / "port.txt").exists():
            # 端口上有人应答、又留着 runtime 文件：多半是另一个用户的会话或另一个副本在跑
            hint = "\n（这个端口上像是有另一个 XGame 在跑：可能是别的窗口、别的用户，或者是另一个副本。）"
        fatal(
            f"端口 {config.port} 已经被占用了。{hint}\n"
            f"请关掉占用它的程序，或者改 {INI_PATH.name} 里的 port（注意："
            "换端口相当于换了站点，浏览器里的本地存档不会跟着走）。"
        )

    write_runtime_files(config.port)
    try:
        return serve(config)
    finally:
        clear_runtime_files()


if __name__ == "__main__":
    raise SystemExit(main())
