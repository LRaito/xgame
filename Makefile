.PHONY: all build up certs test

COMPOSE ?= docker compose

# 作为环境变量导出，compose 里的 ${STORAGE_HOST_DIR} / ${WEB_HTTPS_PORT} 从这里取。
# 没有 .env 也没关系：compose 会退到默认值（./data/storage、443）。
-include .env
export

# 构建版本号：git 短 sha，工作区有未提交改动时加 -dirty（否则「改了没提交就重建」会与上一版同号，
# 老页面收不到更新提示）。不在 git 环境时退化为 UTC 时间戳。
# 刻意不用「sha + 每次构建都带时间戳」：那会让任何一次无意义重建都给所有打开的页面弹提示。
# 上面那行裸 export 会把它一并导出，docker compose build 能读到（web 镜像的 APP_VERSION 构建参数）。
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null)
GIT_DIRTY := $(shell git status --porcelain 2>/dev/null | head -1)
APP_VERSION ?= $(if $(GIT_SHA),$(GIT_SHA)$(if $(GIT_DIRTY),-dirty),$(shell date -u +%Y%m%d%H%M%S))

# 重新生成 HTTPS 自签名证书（写进仓库的 certs/，已存在则跳过）。
# 证书已随仓库提供，只有换主机名/IP 时才需要跑：make certs ARGS="192.168.1.10"
certs:
	bash scripts/gen-certs.sh $(ARGS)

# 构建 api / web 镜像
build:
	$(COMPOSE) build

# 后台启动（api + web）
up:
	$(COMPOSE) up -d
	$(COMPOSE) restart api
	$(COMPOSE) restart web

# 构建并后台启动
all: build up

# 跑一次测试（后端 pytest + 前端 eslint），都在本机执行、不动 Docker。
# 用 `python -m pytest` 而不是裸 `pytest`：后者不把仓库根加进 sys.path，会 import 不到 backend。
# 只跑某几个用例：make test ARGS=tests/test_auth.py
test:
	python3 -m pytest $(ARGS)
	cd frontend && npm run lint
