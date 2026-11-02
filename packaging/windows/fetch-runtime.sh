#!/usr/bin/env bash
#
# 取一份 Windows 版 CPython 运行时压缩包到指定目录，并校验 sha256。
#
#   bash packaging/windows/fetch-runtime.sh <目标目录>
#
# 版本与校验和都在同目录的 runtime.env 里（唯一出处）。文件已存在且校验通过时不重下。
# 两处调用：Dockerfile.build 建镜像时（固化进 /opt/winbuild/runtime），
# build-win-dist.sh 在没有构建环境镜像、直接在本机 Linux 上跑时（下到 dist-win/cache）。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime.env
. "$HERE/runtime.env"

DEST="${1:-}"
[ -n "$DEST" ] || { printf '用法：%s <目标目录>\n' "$0" >&2; exit 2; }
mkdir -p "$DEST"

TARGET="$DEST/$PBS_ASSET"
if [ ! -f "$TARGET" ]; then
    printf '下载 Windows 版 Python：%s\n' "$PBS_ASSET"
    # 先落 .part 再改名：中断留下的是 .part，下次重跑不会把半个文件当成品
    curl -fSL --retry 3 -o "$TARGET.part" "$PBS_URL"
    mv "$TARGET.part" "$TARGET"
fi

echo "$PBS_SHA256  $TARGET" | sha256sum -c - >/dev/null || {
    printf '！%s 的 sha256 与 runtime.env 里钉死的不符，已中止。\n' "$TARGET" >&2
    exit 1
}
printf '运行时已就绪：%s\n' "$TARGET"
