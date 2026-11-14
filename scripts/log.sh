#!/usr/bin/env bash
# 统一的脚本输出：四个固定状态标签，终端带颜色，管道 / 重定向时退回纯文本。
#
#   source scripts/log.sh
#   log_info "读取配置"
#   log_ok "构建完成"
#   log_warn "没有 .env，用默认值"
#   log_fail "端口 8080 被占用"
#
# 也可以直接执行，供 Makefile 使用：
#   bash scripts/log.sh fail "运行时根不可写"
#
# 标签与 ANSI 颜色的唯一出处；脚本里不要再手写 echo + 颜色。

_log_emit() {
    local tag="$1" code="$2" fd="$3" line
    shift 3
    while IFS= read -r line; do
        if [ -t "$fd" ]; then
            printf '\033[%sm%s\033[0m %s\n' "$code" "$tag" "$line"
        else
            printf '%s %s\n' "$tag" "$line"
        fi
    done <<< "$*"
}

log_ok() { _log_emit '[ OK ]' 32 1 "$@"; }
log_fail() { _log_emit '[FAIL]' 31 2 "$@"; }
log_warn() { _log_emit '[WARN]' 33 1 "$@"; }
log_info() { _log_emit '[INFO]' 36 1 "$@"; }

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    case "${1:-}" in
        ok) shift; log_ok "$@" ;;
        fail) shift; log_fail "$@" ;;
        warn) shift; log_warn "$@" ;;
        info) shift; log_info "$@" ;;
        *) log_fail "用法：$0 {ok|fail|warn|info} <消息>"; exit 2 ;;
    esac
fi
