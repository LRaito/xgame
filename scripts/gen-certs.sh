#!/usr/bin/env bash
# 生成自签名 HTTPS 证书，写进仓库里的 certs/（固定文件名 cert.pem / cert.key）。
#
# 证书是随仓库提交的，只有换域名/IP 时才需要重新跑这个脚本；不需要 docker，
# 全程就是 openssl。web 容器把 certs/ 只读挂到 /etc/nginx/certs。
#
# 用法:
#   bash scripts/gen-certs.sh                          # 默认 CN=localhost
#   bash scripts/gen-certs.sh my.host.com              # 指定域名
#   bash scripts/gen-certs.sh 192.168.1.10             # 指定 IP（自动用 IP SAN）
#   bash scripts/gen-certs.sh xxx.com 192.168.100.100  # 多个域名/IP
#   bash scripts/gen-certs.sh example.com "DNS:example.com,DNS:www.example.com"  # 自定义 SAN
#
# 证书已存在时默认跳过（不会被动覆盖）；强制重新生成:
#   FORCE=1 bash scripts/gen-certs.sh
#
# 有效期 36500 天（100 年）。注意：Chrome/Edge 会拒绝有效期超过 398 天的
# TLS 证书（NET::ERR_CERT_VALIDITY_TOO_LONG），如需兼容请改回 -days 3650。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

die() { printf '错误：%s\n' "$*" >&2; exit 1; }

# 证书目录与文件名写死在仓库里，与 docker-compose.yml / frontend/nginx.conf.template 一致。
CERTS_DIR="$REPO_ROOT/certs"
CERT_FILE="cert.pem"
KEY_FILE="cert.key"

mkdir -p "$CERTS_DIR"
CERT_PATH="$CERTS_DIR/$CERT_FILE"
KEY_PATH="$CERTS_DIR/$KEY_FILE"

is_ip() {
    [[ "$1" =~ ^[0-9.]+$ ]]
}

# 组装 SAN；始终包含 localhost / 127.0.0.1，已存在则不重复。
# 参数为裸主机名或 IP；也可传入已格式化的 DNS:/IP: 条目（自定义 SAN 模式）。
build_san() {
    local -a parts=()
    local -A seen=()
    local item

    san_add() {
        [[ -n "${seen[$1]:-}" ]] && return
        seen[$1]=1
        parts+=("$1")
    }

    san_add_host() {
        if is_ip "$1"; then
            san_add "IP:$1"
        else
            san_add "DNS:$1"
        fi
    }

    for item in "$@"; do
        if [[ "$item" == DNS:* || "$item" == IP:* ]]; then
            san_add "$item"
        else
            san_add_host "$item"
        fi
    done

    san_add "DNS:localhost"
    san_add "IP:127.0.0.1"

    local IFS=,
    echo "${parts[*]}"
}

parse_custom_san() {
    local san_str="$1"
    local -a entries=()
    local IFS=,
    read -ra entries <<< "$san_str"
    build_san "${entries[@]}"
}

if [ -f "$CERT_PATH" ] && [ -f "$KEY_PATH" ] && [[ "${FORCE:-}" != "1" ]]; then
    echo "证书已存在：$CERT_PATH（重新生成：FORCE=1 bash scripts/gen-certs.sh [主机名/IP ...]）"
    exit 0
fi

# 现代浏览器（Chrome 58+）要求证书带 SAN 才认主机名/IP，CN 单独填无效。
if [[ $# -eq 2 && ( "$2" == DNS:* || "$2" == IP:* || "$2" == *","* ) ]]; then
    CN="$1"
    SAN="$(parse_custom_san "$2")"
elif [[ $# -ge 1 ]]; then
    CN="$1"
    SAN="$(build_san "$@")"
else
    CN="localhost"
    SAN="$(build_san)"
fi

command -v openssl >/dev/null 2>&1 || die "找不到 openssl，先安装它（apt install openssl）。"

openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY_PATH" \
    -out "$CERT_PATH" \
    -days 36500 \
    -subj "/CN=$CN" \
    -addext "subjectAltName=$SAN"

chmod 644 "$CERT_PATH"
chmod 600 "$KEY_PATH"

echo "已生成自签名证书（有效期 36500 天，约 100 年）："
echo "  证书  $CERT_PATH"
echo "  密钥  $KEY_PATH"
echo "web 容器里对应 /etc/nginx/certs/$CERT_FILE 与 /etc/nginx/certs/$KEY_FILE。"
echo "浏览器会提示不受信任（自签名），需手动「继续访问」。"
