#!/usr/bin/env bash
#
# 组装「解压即用」的 Windows 包。**整个组装过程都在 WSL / Linux 上跑**，不需要 Windows。
#
# 产物：dist-win/xgame_v<最新 tag>.zip
#   解压出来是一个 xgame/ 目录，双击里面的「启动游戏平台.cmd」就能玩。
#
# 用法：
#   bash packaging/windows/build-win-dist.sh              # 完整组装（首次要联网）
#   SKIP_FRONTEND=1 bash .../build-win-dist.sh            # 复用已有的 frontend/dist
#   APP_VERSION=v1.2.3 bash .../build-win-dist.sh         # 指定版本号（默认取最新 git tag）
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT_DIR:-$REPO/dist-win}"
PKG="$OUT/xgame"
CACHE="$OUT/cache"

# Python 运行时：python-build-standalone 的可重定位 CPython，小版本与 api 镜像（python:3.12.15）对齐。
# 这是整份包唯一的供应链入口，所以 release 与 sha256 都钉死；升级时三个值一起改。
PBS_RELEASE="20261013"
PBS_ASSET="cpython-3.12.15+${PBS_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz"
PBS_SHA256="bbc902d4d187ac4914915bf538196a064b49109a33a104965b5164ced5b80a1e"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${PBS_ASSET}"

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

for tool in curl zip python3; do
    command -v "$tool" >/dev/null 2>&1 || { say "缺少命令：$tool"; exit 1; }
done

# ---------- 版本号：默认取当前项目最新 tag ----------
VERSION="${APP_VERSION:-}"
if [ -z "$VERSION" ]; then
    tag="$(git -C "$REPO" describe --tags --abbrev=0 2>/dev/null || true)"
    if [ -z "$tag" ]; then
        say "！仓库里还没有任何 tag，先用 v0.0.0 兜底（正式发包前记得打个 tag）。"
        tag="v0.0.0"
    fi
    VERSION="$tag"
    if [ -n "$(git -C "$REPO" status --porcelain 2>/dev/null | head -1)" ]; then
        VERSION="${tag}-dirty"
        say "！工作区有未提交改动，版本号记作 ${VERSION}（这类包不会被包内升级逻辑当成新版本）。"
    fi
fi
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
else
    # 首次构建要联网：fetch-emulatorjs.mjs 从 cdn.emulatorjs.org 拉 6 个平台的内核，
    # copy-ruffle.mjs 从 node_modules 拷。脚本是幂等的（带 .emulatorjs.done 标记），
    # 重复构建不会重下。
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
if [ ! -f "$CACHE/$PBS_ASSET" ]; then
    say "下载中……"
    curl -fSL --retry 3 -o "$CACHE/$PBS_ASSET.part" "$PBS_URL"
    mv "$CACHE/$PBS_ASSET.part" "$CACHE/$PBS_ASSET"
fi
echo "$PBS_SHA256  $CACHE/$PBS_ASSET" | sha256sum -c - >/dev/null || {
    say "！运行时压缩包的 sha256 与钉死的值不符，已中止。"
    exit 1
}
say "sha256 校验通过"
tar -xzf "$CACHE/$PBS_ASSET" -C "$PKG"
[ -x "$PKG/python/python.exe" ] || { say "！解出来的运行时里没有 python.exe"; exit 1; }

# 瘦身：调试符号（*.pdb）与用不到的 tkinter/tcl 占了差不多一半体积，删掉不影响运行。
# 刻意**保留** Lib/site-packages/pip：哪天用户要自救（补装个包）还能用。
find "$PKG/python" -name '*.pdb' -delete
rm -rf "$PKG/python/tcl" "$PKG/python/Lib/tkinter" "$PKG/python/Lib/test" \
       "$PKG/python/DLLs/_tkinter.pyd" "$PKG/python/DLLs/tcl86t.dll" "$PKG/python/DLLs/tk86t.dll"
say "运行时：$(du -sh "$PKG/python" | cut -f1)"

# ---------- 3. Windows 依赖 ----------
step "3/6 依赖（win_amd64 轮子）"
# 在 Linux 上直接下 Windows 轮子：--only-binary 是 --platform 的硬要求，
# 三个 --python-version/--implementation/--abi 不能省，否则会被当前解释器的 tag 带偏。
python3 -m pip install --quiet --upgrade \
    --target "$PKG/python/Lib/site-packages" \
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

# ---------- 5. 自检（不用碰 Windows：WSL interop 直接跑 python.exe）----------
step "5/6 自检"
if [ -e /proc/sys/fs/binfmt_misc/WSLInterop ]; then
    ( cd "$PKG" && ./python/python.exe -X utf8 smoke_win.py )
else
    say "本机 WSL interop 不可用，跳过自检（到 Windows 上可以手动跑 python\\python.exe smoke_win.py）"
fi

# ---------- 6. 打包 ----------
step "6/6 打包"
rm -f "$OUT/$ZIP_NAME"
( cd "$OUT" && zip -qr "$ZIP_NAME" xgame -x '*/__pycache__/*' )
say "完成：$OUT/$ZIP_NAME（$(du -sh "$OUT/$ZIP_NAME" | cut -f1)）"
say "解压出来是 xgame/ 目录，双击「启动游戏平台.cmd」即可。"
