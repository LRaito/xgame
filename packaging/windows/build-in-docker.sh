#!/usr/bin/env bash
#
# `make win` 的入口：在容器里组装 Windows「解压即用」包。两步——
#
#   1. 构建环境镜像（`packaging/windows/Dockerfile.build`）不存在就先建一次。
#      镜像里预置了**所有能固定的依赖**（Windows 版 CPython、win 轮子、前端 node_modules、
#      EmulatorJS 资产），所以第 2 步不联网、也不依赖宿主机装了什么。
#   2. 在容器里跑 build-win-dist.sh，产物落在宿主机仓库的 dist-win/。
#
# 镜像 tag 里带着「Dockerfile + 它 COPY 的那些输入文件」的哈希（见下面的 HASH_INPUTS）：
# 任何一处改了 tag 就变、自动重建，没改就一直复用。
#
# 用法：
#   make win                       # 出包
#   make win-image                 # 只建/更新构建环境镜像，不出包
#   APP_VERSION=v9.9.9 make win    # 指定版本号（默认由 scripts/version.sh 从 git tag 算）
#   SKIP_FRONTEND=1 make win       # 复用已有的 frontend/dist，跳过前端构建（迭代时快很多）
#   WINBUILD_NO_CACHE=1 make win-image   # 忽略缓存重建镜像（拿传递依赖的安全更新时用）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DOCKERFILE="$HERE/Dockerfile.build"

say() { printf '%s\n' "$*"; }
die() { printf '%s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "没找到 docker：Windows 包在容器里构建，请先装好 Docker。"

IMAGE_ONLY=0
[ "${1:-}" = "--image-only" ] && IMAGE_ONLY=1

# 镜像 tag = 构建环境镜像里那些东西的哈希。除了 Dockerfile 本身，还要带上它 COPY 进去的
# 输入文件——改了任何一个（升运行时、换依赖、升 EmulatorJS 引擎版本）都得重建镜像，
# 否则会拿一个内容已经过时的旧镜像出包。
HASH_INPUTS=(
    "$DOCKERFILE"
    "$HERE/runtime.env"
    "$HERE/requirements-win.txt"
    "$REPO/frontend/package.json"
    "$REPO/frontend/package-lock.json"
    "$REPO/frontend/scripts/fetch-emulatorjs.mjs"
)
HASH="$(cat "${HASH_INPUTS[@]}" | sha256sum | cut -c1-12)"
IMAGE="xgame-winbuild:$HASH"

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    say "构建环境镜像已存在，直接复用：$IMAGE"
else
    say "构建环境镜像不存在，先建一次：$IMAGE"
    say "（装工具链 + 下 Windows 运行时/轮子/前端依赖/引擎资产，首次几分钟且要联网，之后就都复用了）"
    # 构建上下文是仓库根：Dockerfile 要从 frontend/ 里取 package.json、lock 与引擎脚本。
    # 不 COPY 的一律不会进镜像，所以不需要 .dockerignore。
    BUILD_ARGS=()
    [ "${WINBUILD_NO_CACHE:-0}" = "1" ] && BUILD_ARGS+=(--no-cache)
    docker build -f "$DOCKERFILE" -t "$IMAGE" "${BUILD_ARGS[@]}" "$REPO"
fi
[ "$IMAGE_ONLY" = "1" ] && { say "只建镜像，按 --image-only 退出。"; exit 0; }

# 以宿主机用户身份跑，产出的 dist-win/ 与前端产物才不会变成 root 所有（那样宿主机删不掉）。
# HOME 指向 /tmp：容器里没有这个 uid 的家目录，npm 需要一个可写的家。
say ""
say "在容器里组装 Windows 包……"
docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e APP_VERSION \
    -e SKIP_FRONTEND \
    -v "$REPO:/repo" \
    -w /repo \
    "$IMAGE" \
    bash packaging/windows/build-win-dist.sh

# 包内自检挪到宿主机上跑：容器里没有 binfmt_misc，执行不了包里那份 Windows 的 python.exe；
# 而宿主机是 WSL 时可以直接跑（验证 FTS5、依赖、没有混进 gunicorn/uvloop、MSVC 运行库在位）。
if [ -e /proc/sys/fs/binfmt_misc/WSLInterop ]; then
    say ""
    say "在宿主机上补一次包内自检……"
    ( cd "$REPO/dist-win/xgame" && ./python/python.exe -X utf8 smoke_win.py ) \
        || die "包内自检没通过，先别发这个包。"
else
    say ""
    say "提示：本机不是 WSL（没有 interop），跳过包内自检。"
    say "     到 Windows 上可以手动跑：xgame\\python\\python.exe smoke_win.py"
fi
