.PHONY: all build up certs test index win win-image

COMPOSE ?= docker compose

# 作为环境变量导出，compose 里的 ${STORAGE_HOST_DIR} / ${RUNTIME_HOST_DIR} / ${WEB_HTTPS_PORT} 从这里取
# （index 目标也靠 $${STORAGE_HOST_DIR} 读它）。
# 没有 .env 也没关系：compose 会退到默认值（数据与库都放 ./data/storage、端口 443）。
#
# 精确导出而不是裸 `export`：后者会把 .env 与 Makefile 里的每个变量都塞进所有子进程的环境。
# 注意这两个 *_HOST_DIR 确实会被 `make test` 带进 pytest 的环境，而 `Settings` 会读环境变量——
# 测试侧由 tests/conftest.py 的 `_hide_host_dir_env` 兜住（那条 autouse fixture 别删）。
# WINBUILD_NO_CACHE 也要带上：`make win WINBUILD_NO_CACHE=1` 是命令行变量（不在环境里），
# 而 packaging/windows/build-in-docker.sh 是按环境变量读它的。
-include .env
export STORAGE_HOST_DIR RUNTIME_HOST_DIR WEB_HTTPS_PORT WINBUILD_NO_CACHE

# 构建版本号：取仓库最新 tag；HEAD 停在 tag 之后的提交上时再补一段提交时间戳
# （v1.0.0 或 v1.0.0-1792042865000，规则与比较方式见 scripts/version.sh）。
# 前端把它显示在侧栏标题后、并写进 /version.txt 供已经打开的页面探测新版本。
# 单独导出：docker compose build 要读它（web 镜像的 APP_VERSION 构建参数）。
APP_VERSION ?= $(shell bash scripts/version.sh)
export APP_VERSION

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

# 组装 Windows「解压即用」包：产物 dist-win/xgame_v<版本>.zip，解压后双击「启动游戏平台.cmd」即玩。
# 整个组装在容器里跑（构建环境镜像不存在就先建一次），宿主机只要有 Docker，
# 不需要 node / python / curl / zip。版本号取 scripts/version.sh。
# 依赖都预置在构建环境镜像里（Windows 运行时 / win 轮子 / 前端 node_modules / 引擎资产），
# 所以只有建镜像那一次要联网，之后每次出包都是离线的。
win:
	bash packaging/windows/build-in-docker.sh

# 只构建（或更新）那个构建环境镜像，不出包。镜像 tag 是「Dockerfile + 它 COPY 的输入文件」的哈希，
# 改了任一处会自动重建，一般不用手动跑。WINBUILD_NO_CACHE=1 时忽略缓存重建（拿依赖的安全更新）。
win-image:
	bash packaging/windows/build-in-docker.sh --image-only

# 构建「游戏检索」用的索引库（<数据根>/db/game.db）。可重复执行，直接覆盖旧文件。
# 服务启动时若发现索引不存在，会自动补建一次；这个 target 用于手动重建/更新（换了名录之后）。
# 数据根取自 .env 的 STORAGE_HOST_DIR，与容器挂的是同一个宿主目录，所以构建完 api 立刻能读到。
index:
	@test -d "$${STORAGE_HOST_DIR:-./data/storage}" && ! test -w "$${STORAGE_HOST_DIR:-./data/storage}" \
		&& { \
			echo "数据根不可写：$${STORAGE_HOST_DIR:-./data/storage}"; \
			echo "（多半是 Docker 容器以 root 建的目录）先执行一次："; \
			echo "    sudo chown -R \"$$USER\" \"$${STORAGE_HOST_DIR:-./data/storage}\""; \
			exit 1; \
		} || true
	STORAGE_ROOT=$${STORAGE_HOST_DIR:-./data/storage} python3 -m backend.cli index
