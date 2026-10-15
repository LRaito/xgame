#!/usr/bin/env bash
#
# 组装「解压即用」的 Windows 包。**整个组装过程都在 WSL / Linux 上跑**，不需要 Windows。
#
# 产物：dist-win/xgame_v<版本>.zip
#   解压出来是一个 xgame/ 目录，双击里面的「启动游戏平台.cmd」就能玩。
#
# 依赖从哪来：优先用构建环境镜像里预置的那份（/opt/winbuild，见 Dockerfile.build）——
# 前端依赖、EmulatorJS 资产、Windows 轮子、Windows 版 CPython 全在里面，
# 于是**这一步完全不联网**，宿主机也不需要 node / npm。没有那个目录时（直接在本机 Linux 上跑）
# 退回联网下载 / 宿主机自己的 node_modules。
#
# 用法：
#   make win                                     # 正常路径：在容器里跑本脚本
#   bash packaging/windows/build-win-dist.sh     # 直接在本机 Linux 上跑（要自备 node/python/curl/zip）
#   SKIP_FRONTEND=1 bash .../build-win-dist.sh   # 复用已有的 frontend/dist，跳过前端构建（迭代时快很多）
#   APP_VERSION=v1.2.3 bash .../build-win-dist.sh  # 指定版本号（默认由 scripts/version.sh 从 git tag 算）
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT_DIR:-$REPO/dist-win}"
PKG="$OUT/xgame"
CACHE="$OUT/cache"

# 构建环境镜像里预置依赖的位置；不在容器里跑时这个目录不存在，各处会自己退到联网那条路。
WINBUILD="${WINBUILD_DIR:-/opt/winbuild}"
# 前端在容器里的临时构建目录：源码拷进来、node_modules 从镜像里拿，
# 于是宿主机既不用装 node，它自己的 frontend/node_modules 也一点不被碰。
FE_BUILD="${FE_BUILD_DIR:-/tmp/xgame-fe}"

# Windows 版 Python 运行时的版本与 sha256 在 runtime.env（唯一出处，镜像构建也读它）
# shellcheck source=runtime.env
. "$HERE/runtime.env"

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

for tool in curl zip python3; do
    command -v "$tool" >/dev/null 2>&1 || { say "缺少命令：$tool"; exit 1; }
done

# ---------- 版本号 ----------
# 默认由 scripts/version.sh 从 git tag 算：
#   HEAD 正好在最新 tag 上 → v1.0.0；在 tag 之后的提交上 → v1.0.0-<HEAD 提交时间毫秒>
# （升级时先比 tag 再比那串时间戳，见 launcher.py 的 _version_key）。
# 也可以直接指定：APP_VERSION=v9.9.9 make win
VERSION="${APP_VERSION:-$(bash "$REPO/scripts/version.sh")}"
ZIP_NAME="xgame_${VERSION}.zip"

step "组装 xgame ${VERSION}"
say "仓库：$REPO"
say "输出：$OUT/$ZIP_NAME"

mkdir -p "$OUT" "$CACHE"
# 重新组装：只清包目录，保留 cache/ 里下过的运行时，免得每次重下 46MB
rm -rf "$PKG"
mkdir -p "$PKG"

# ---------- 1. 前端构建产物 ----------
step "1/6 前端"
if [ "${SKIP_FRONTEND:-0}" = "1" ] && [ -d "$REPO/frontend/dist" ]; then
    say "SKIP_FRONTEND=1，复用已有的 frontend/dist"
elif [ -d "$WINBUILD/frontend/node_modules" ]; then
    # 构建环境镜像里那份依赖：源码拷到容器内的临时目录里构建（不碰宿主机的 node_modules），
    # 前端依赖、Ruffle（从 node_modules 拷）、EmulatorJS 资产全都来自镜像，全程离线。
    say "用构建环境里的前端依赖构建（源码拷到 $FE_BUILD）"
    rm -rf "$FE_BUILD"
    mkdir -p "$FE_BUILD"
    rsync -a --delete \
        --exclude node_modules --exclude dist \
        --exclude public/emulatorjs --exclude public/ruffle \
        "$REPO/frontend/" "$FE_BUILD/"
    cp -a "$WINBUILD/frontend/node_modules" "$FE_BUILD/node_modules"
    # EmulatorJS 资产（含 .emulatorjs.done 标记）：给了标记，构建时的 fetch 脚本就走离线快路径
    cp -a "$WINBUILD/frontend/public/emulatorjs" "$FE_BUILD/public/emulatorjs"
    ( cd "$FE_BUILD" && APP_VERSION="$VERSION" npm run build )
    # 产物同步回仓库一份：本机调试（STATIC_DIR=frontend/dist）与 SKIP_FRONTEND 迭代都用得上
    rm -rf "$REPO/frontend/dist"
    cp -a "$FE_BUILD/dist" "$REPO/frontend/dist"
    rm -rf "$FE_BUILD"
else
    # 没在构建环境镜像里跑：退回宿主机自己的 node_modules（首次构建要联网，脚本幂等、重复构建不重下）
    say "没有构建环境镜像，用宿主机的 node_modules 构建"
    if [ ! -d "$REPO/frontend/node_modules" ]; then
        ( cd "$REPO/frontend" && npm ci )
    fi
    ( cd "$REPO/frontend" && APP_VERSION="$VERSION" npm run build )
fi
test -s "$REPO/frontend/dist/version.txt" || {
    say "！前端产物里没有 version.txt，构建没成功。"
    exit 1
}
mkdir -p "$PKG/web"
cp -a "$REPO/frontend/dist/." "$PKG/web/"
say "前端产物：$(du -sh "$PKG/web" | cut -f1)，版本 $(cat "$PKG/web/version.txt")"

# ---------- 2. Windows 版 Python ----------
step "2/6 Windows 版 Python（$PBS_ASSET）"
if [ -f "$WINBUILD/runtime/$PBS_ASSET" ]; then
    say "用构建环境里预置的运行时"
    RUNTIME="$WINBUILD/runtime/$PBS_ASSET"
else
    say "构建环境里没有预置运行时，改用 $CACHE（那儿没有就联网取一份）"
    bash "$HERE/fetch-runtime.sh" "$CACHE"
    RUNTIME="$CACHE/$PBS_ASSET"
fi
# 无论来自镜像还是刚下的，都再校一次：镜像层被换掉、文件被截断都在这里拦住
echo "$PBS_SHA256  $RUNTIME" | sha256sum -c - >/dev/null || {
    say "！运行时压缩包的 sha256 与 runtime.env 里钉死的不符，已中止。"
    exit 1
}
say "sha256 校验通过"
tar -xzf "$RUNTIME" -C "$PKG"
[ -x "$PKG/python/python.exe" ] || { say "！解出来的运行时里没有 python.exe"; exit 1; }

# 瘦身：调试符号（*.pdb）与用不到的 tkinter/tcl 占了差不多一半体积，删掉不影响运行。
# 刻意**保留** Lib/site-packages/pip：哪天用户要自救（补装个包）还能用。
find "$PKG/python" -name '*.pdb' -delete
rm -rf "$PKG/python/tcl" "$PKG/python/Lib/tkinter" "$PKG/python/Lib/test" \
       "$PKG/python/DLLs/_tkinter.pyd" "$PKG/python/DLLs/tk86t.dll" "$PKG/python/DLLs/tcl86t.dll"
say "运行时：$(du -sh "$PKG/python" | cut -f1)"

# ---------- 3. Windows 依赖 ----------
step "3/6 依赖（win_amd64 轮子）"
# 在 Linux 上直接装 Windows 轮子：--only-binary 是 --platform 的硬要求，
# 三个 --python-version/--implementation/--abi 不能省，否则会被当前解释器的 tag 带偏。
if [ -d "$WINBUILD/wheels" ]; then
    say "从构建环境里的轮子仓库离线安装（$(ls "$WINBUILD/wheels" | wc -l) 个）"
    PIP_SOURCE=(--no-index --find-links "$WINBUILD/wheels")
else
    say "构建环境里没有轮子仓库，联网从 PyPI 取"
    PIP_SOURCE=()
fi
python3 -m pip install --quiet --upgrade \
    --target "$PKG/python/Lib/site-packages" \
    "${PIP_SOURCE[@]}" \
    --platform win_amd64 \
    --python-version 3.12 \
    --implementation cp \
    --abi cp312 \
    --only-binary=:all: \
    -r "$HERE/requirements-win.txt"
# 轮子带的控制台脚本（uvicorn.exe 之类）在 Windows 版 PBS 里本来也是坏的，用不上
rm -rf "$PKG/python/Lib/site-packages/bin"

# ---------- 4. 后端与包内脚本 ----------
step "4/6 后端与启动脚本"
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$REPO/backend/" "$PKG/backend/"
else
    cp -a "$REPO/backend" "$PKG/backend"
    find "$PKG/backend" -name '__pycache__' -type d -prune -exec rm -rf {} +
    find "$PKG/backend" -name '*.pyc' -delete
fi
test -d "$PKG/backend/search/csv" || { say "！backend/search/csv 没带上，检索索引建不出来"; exit 1; }

for name in launcher.py winops.py smoke_win.py upgrade.ps1 allow-lan.ps1 xgame.ico \
            启动游戏平台.cmd 升级.bat 允许局域网访问.bat \
            创建桌面快捷方式.bat 设置开机自启.bat 解除锁定.bat 说明.txt; do
    cp -a "$HERE/$name" "$PKG/$name"
done

# 图标：xgame.ico 是提交进仓库的产物，由 make_icon.py 从 xgame.png（可替换的源图）生成。
# 源图比图标新就顺手重生成一次；本机没装 Pillow 就只提醒、不拦构建（用仓库里那份图标）。
if [ "$HERE/xgame.png" -nt "$HERE/xgame.ico" ]; then
    if python3 -c "import PIL" >/dev/null 2>&1; then
        say "xgame.png 比 xgame.ico 新，正在重新生成图标……"
        python3 "$HERE/make_icon.py"
        cp -a "$HERE/xgame.ico" "$PKG/xgame.ico"
    else
        say "！xgame.png 比 xgame.ico 新，但本机没有 Pillow，包里用的还是旧图标。"
        say "  装好 Pillow 再构建一次，或手动跑：python3 packaging/windows/make_icon.py"
    fi
fi
[ -f "$PKG/xgame.ico" ] || { say "！缺少 xgame.ico（跑 python3 packaging/windows/make_icon.py 生成）"; exit 1; }

# 版本文件：包内升级逻辑拿它跟新包的文件名比大小；前端也用同一个值，
# 所以「服务端换了新构建」的提示照常工作。
printf '%s' "$VERSION" > "$PKG/version.txt"

# 包内默认配置由 launcher.py 的模板生成，保证只有一份定义
python3 -c "
import sys
sys.path.insert(0, r'$HERE')
import launcher
sys.stdout.write(launcher._INI_TEMPLATE)
" > "$PKG/xgame.ini"

mkdir -p "$PKG/updates"
cat > "$PKG/updates/说明.txt" <<'TXT'
把新版本的安装包（xgame_v*.zip）放进这个文件夹，下次启动时会自动升级。

升级过程：停服务 → 解压 → 替换程序文件 → 重新启动。数据目录原地不动，
账号、存档、截图、游戏本体都不受影响。启动器里也可以关掉自动升级（xgame.ini 的 auto_update）。
TXT

# ---------- 5. 自检（WSL interop 可用时直接跑包里那份 python.exe）----------
step "5/6 自检"
if [ -e /proc/sys/fs/binfmt_misc/WSLInterop ]; then
    ( cd "$PKG" && ./python/python.exe -X utf8 smoke_win.py )
else
    # 在容器里构建就是这条路：容器里没有 binfmt_misc，跑不了 Windows 的 python.exe。
    # 交给 build-in-docker.sh 在宿主机上补一次（那儿才有 interop）。
    say "本机（或本容器）跑不了 Windows 的 python.exe，跳过自检。"
fi

# ---------- 6. 打包 ----------
step "6/6 打包"
rm -f "$OUT/$ZIP_NAME"
( cd "$OUT" && zip -qr "$ZIP_NAME" xgame -x '*/__pycache__/*' )
say "完成：$OUT/$ZIP_NAME（$(du -sh "$OUT/$ZIP_NAME" | cut -f1)）"
say "解压出来是 xgame/ 目录，双击「启动游戏平台.cmd」即可。"
