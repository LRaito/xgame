#!/usr/bin/env bash
#
# 打印本次构建的版本号。Docker 路线（Makefile）与 Windows 包组装脚本共用这一份。
#
#   HEAD 正好停在最新的 tag 上   → v1.0.0
#   HEAD 在 tag 之后的提交上     → v1.0.0-1792042865000
#   仓库里一个 tag 都没有        → v0.0.0-<当前时间毫秒>
#
# 后缀那串数字是 **HEAD 的提交时间（毫秒）**，不是构建时刻。两个原因：
#   1. 比较版本大小时先比 `v1.0.0` 再比这串数字，越靠后的提交数字越大，正好等于「谁更新」；
#   2. 同一个提交反复构建得到同一个版本号——否则每次重建都会让已经打开的页面弹「有新版本」。
#
# 版本号会写进前端产物（页面左上角显示、`/version.txt` 供老页面探测更新），
# 所以只允许 [0-9A-Za-z._-]（见 frontend/src/utils/versionCheck.js 的白名单）。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# 不在 git 仓库里（比如拿 tar 包构建）也要能出包：退回时间戳
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    printf 'v0.0.0-%s\n' "$(( $(date +%s) * 1000 ))"
    exit 0
fi

tag="$(git describe --tags --abbrev=0 2>/dev/null || true)"
if [ -z "$tag" ]; then
    printf 'v0.0.0-%s\n' "$(( $(git log -1 --format=%ct 2>/dev/null || date +%s) * 1000 ))"
    exit 0
fi

# tag 指的提交就是 HEAD：干净的发布版本，不带后缀
if [ "$(git rev-parse "$tag^{commit}" 2>/dev/null)" = "$(git rev-parse HEAD 2>/dev/null)" ]; then
    printf '%s\n' "$tag"
    exit 0
fi

printf '%s-%s\n' "$tag" "$(( $(git log -1 --format=%ct) * 1000 ))"
