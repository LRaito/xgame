"""xgame 启动器：解压即用包的双击入口。

它做四件事，按顺序：

1. **自检**（缺 MSVC 运行库、SQLite 没有 FTS5、数据目录被 Docker 路线用过）；
2. **看有没有新版本**（`updates/xgame_v*.zip`），有就交给 `升级.bat` 并退出；
3. **起服务**：进程内跑 uvicorn（不起子进程——Windows 上硬杀进程会把 SQLite 留在半路，
   而进程内跑时关窗口 / 收到关机请求都能走优雅退出），顺带按环境变量让后端托管前端 dist；
4. **等它就绪**再打开浏览器，并打印本机与局域网两个地址。

配置文件是旁边的 `xgame.ini`（没有就用默认值建一份）。整个包不写注册表、不装服务、
不碰系统目录，删掉文件夹就算卸载。

这个文件在包里位于 `xgame/launcher.py`，与 `backend/`、`web/`、`python/` 同级。
"""

from __future__ import annotations

import configparser
import ctypes
import logging
import logging.handlers
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
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
    "auto_update": "yes",
}

_INI_TEMPLATE = """\
[xgame]
# 数据目录：账号、存档、截图、游戏本体和数据库全在这里。
# 相对路径按本文件所在目录算；想让数据待在包外面（换新版本时更省事），
# 填绝对路径，例如：data_dir = D:\\xgame-data
# 也可以直接指向以前 WSL 那份数据（如 X:\\xgame），存档与截图会原样续用——
# 但**别和 Docker 路线同时开着**，两边一起写会把库写坏。
data_dir = data

# 监听地址：0.0.0.0 = 局域网里的手机、平板也能连；127.0.0.1 = 只有本机能连。
host = 0.0.0.0

# 端口。**改端口等于换了一个站点**：浏览器里的本地存档、模拟器设置都跟着端口走，
# 改了会觉得「档没了」，所以除非端口被占用，否则不要动它。
port = 8910

# 启动后自动打开浏览器：yes / no
open_browser = yes

# 启动时发现 updates 目录（或包目录、上一层目录）里有更新的 xgame_v*.zip 就自动升级：
# yes / no。升级会先停服务、替换程序文件后重新启动，数据目录原地不动。
auto_update = yes
"""


class Config:
    def __init__(self, parser: configparser.ConfigParser) -> None:
        section = parser["xgame"] if parser.has_section("xgame") else {}
        self.data_dir = self._path(section.get("data_dir", _DEFAULTS["data_dir"]))
        self.host = (section.get("host") or _DEFAULTS["host"]).strip()
        self.port = self._port(section.get("port", _DEFAULTS["port"]))
        self.open_browser = self._flag(section.get("open_browser", _DEFAULTS["open_browser"]))
        self.auto_update = self._flag(section.get("auto_update", _DEFAULTS["auto_update"]))

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
        say("提示：本机 Python 的 SQLite 没有 FTS5，「游戏检索」页会一直显示尚未构建索引。")


def check_data_dir(data_dir: Path) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".write-probe"
        probe.touch()
        probe.unlink()
    except OSError as exc:
        fatal(
            f"数据目录用不了：{data_dir}\n"
            f"（{exc}）\n"
            "常见原因是路径指向了需要管理员权限的位置（如 C:\\Program Files 下）"
            "或盘符不存在。请改 xgame.ini 里的 data_dir。"
        )
    marker = data_dir / ".mounted"
    if marker.exists():
        say()
        say("!" * 62)
        say("注意：这个数据目录里有 .mounted 哨兵，说明它是 Docker/WSL 那条路线在用的。")
        say("两边同时打开同一份数据会把数据库写坏——请先执行 docker compose down，")
        say("或者把 xgame.ini 里的 data_dir 换成另一个目录。")
        say("!" * 62)


# ---------- 更新包 ----------


def _version_key(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text)
    return tuple(int(item) for item in numbers) if numbers else (0,)


def current_version() -> str:
    path = ROOT / "version.txt"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "v0.0.0"


def find_update() -> tuple[Path, str] | None:
    """找有没有比当前版本更新的安装包。

    找三个地方：包的 `updates/`（推荐）、包目录本身、包目录的上一层
    （很多人习惯把新 zip 解压/下载到 xgame 旁边）。版本按数字段比大小，不按字符串比。
    """
    current = _version_key(current_version())
    found: tuple[Path, str] | None = None
    candidates: list[Path] = []
    for folder in (ROOT / "updates", ROOT, ROOT.parent):
        if folder.is_dir():
            candidates.extend(sorted(folder.glob("xgame_v*.zip")))
    for path in candidates:
        match = re.search(r"xgame_(v[\w.\-]+)\.zip$", path.name, re.IGNORECASE)
        if not match:
            continue
        version = match.group(1)
        if _version_key(version) <= current:
            continue
        if found is None or _version_key(version) > _version_key(found[1]):
            found = (path, version)
    return found


def run_updater(update: tuple[Path, str]) -> None:
    path, version = update
    say()
    say(f"发现新版本 {version}（当前 {current_version()}），正在交给升级程序……")
    say("升级过程中浏览器会短暂打不开，完成后会自动重新启动。")
    bat = ROOT / "升级.bat"
    if not bat.is_file():
        fatal(f"发现新版本 {version}，但包里找不到「升级.bat」，请手动解压新包。")
    creation_flags = 0x00000010 if os.name == "nt" else 0  # CREATE_NEW_CONSOLE
    # cwd 刻意不放包目录：升级最后要把整个 xgame 改名，而任何进程的当前目录会让这次改名失败。
    # `/auto` 告诉升级脚本「是启动器调起来的」，跑完不要 pause。
    subprocess.Popen(  # noqa: S603 - 路径来自包内固定文件名
        ["cmd", "/c", str(bat), "/auto"] if os.name == "nt" else [str(bat)],
        cwd=tempfile.gettempdir(),
        creationflags=creation_flags,
        close_fds=True,
    )


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


def write_runtime_files(port: int, token: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "port.txt").write_text(str(port), encoding="utf-8")
    (RUNTIME_DIR / "control.token").write_text(token, encoding="utf-8")
    (RUNTIME_DIR / "xgame.pid").write_text(str(os.getpid()), encoding="utf-8")


def clear_runtime_files() -> None:
    for name in ("port.txt", "control.token", "xgame.pid"):
        try:
            (RUNTIME_DIR / name).unlink(missing_ok=True)
        except OSError:
            pass


def serve(config: Config, token: str) -> int:
    import uvicorn

    os.environ["STORAGE_ROOT"] = str(config.data_dir)
    os.environ["STATIC_DIR"] = str(ROOT / WEB_DIR_NAME)
    # 局域网走 http（自签证书对手机/平板等于没有），cookie 不能带 Secure，
    # 否则浏览器不保存它，表现是「登录看着成功、下一个请求就 401」。
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    # 本地关机口：升级脚本靠它让服务优雅退出，token 每次启动重新生成
    os.environ["LOCAL_CONTROL"] = "1"
    os.environ["LOCAL_CONTROL_TOKEN"] = token

    # 必须在这里才 import：backend.asgi 在导入时就 create_app()，配置是那一刻读的。
    # 也正是这次导入在建目录、建表、做月度备份、建检索索引，首次启动会明显卡一下。
    prepared_at = time.monotonic()
    from backend.asgi import app

    prepared = time.monotonic() - prepared_at
    if prepared > 3:
        say(f"已准备数据（{prepared:.0f} 秒）：建库、月度备份、检索索引。下次启动会快很多。")

    server = uvicorn.Server(
        uvicorn.Config(app, host=config.host, port=config.port, log_config=None, access_log=False)
    )
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)

    # 进程内跑，不起子进程：Windows 上 terminate 是硬杀，SQLite 可能被留在半路；
    # 进程内跑时关窗口、Ctrl+C、升级脚本的关机请求都能走优雅退出。
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
    say("  XGame 已经跑起来了")
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

_USAGE = "可用参数：" + " / ".join([*_ACTIONS, "--quiet", "--no-browser", "--no-update"])


def parse_args(argv: list[str]) -> dict:
    options = {"quiet": False, "no_browser": False, "no_update": False, "action": None}
    for item in argv:
        if item in _ACTIONS:
            options["action"] = _ACTIONS[item]
        elif item == "--quiet":
            options["quiet"] = True
        elif item == "--no-browser":
            options["no_browser"] = True
        elif item == "--no-update":
            options["no_update"] = True
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
    check_data_dir(config.data_dir)
    setup_logging(config.data_dir)

    # 先确认没有第二个实例在跑。双击第二次不该起第二个服务（除了白占资源，两个进程打开
    # 同一个 SQLite 更容易出事）：这里只把地址告诉用户、顺手把浏览器打开。
    instance = SingleInstance(f"Local\\xgame-port-{config.port}")
    if not instance.acquire():
        pending = find_update() if (config.auto_update and not options["no_update"]) else None
        say()
        say("XGame 已经在运行了，不用再开一个。")
        say_addresses(config)
        if pending is not None:
            say(f"  顺带一提：这里有更新的版本 {pending[1]}，下次启动会自动升级。")
        say()
        if config.open_browser:
            webbrowser.open(f"http://127.0.0.1:{config.port}")
        return 0

    if config.auto_update and not options["no_update"]:
        update = find_update()
        if update is not None:
            run_updater(update)
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

    # 关机口令每次启动重新生成：升级脚本从 runtime/control.token 读它（见 local_control.py）
    token = secrets.token_urlsafe(32)
    write_runtime_files(config.port, token)
    try:
        return serve(config, token)
    finally:
        clear_runtime_files()


if __name__ == "__main__":
    raise SystemExit(main())
