.PHONY: all build up certs test index win win-image upgrade

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

# 构建 api / web 镜像。
# --pull=false：构建前不主动拉取更新的基础镜像（基础镜像已按 digest 固定，见两个 Dockerfile）。
# 注意 Docker 在本地缺基础镜像时仍会联网拉取；要完全离线，先手动 docker pull 好再用。
build:
	$(COMPOSE) build --pull=false

# 后台启动（api + web）
up:
	$(COMPOSE) up -d
	$(COMPOSE) restart api
	$(COMPOSE) restart web

# 构建并后台启动
all: build up upgrade

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

# 全量构建「游戏名录」「游戏榜单」与卡带映射，并同步两个库的库存/榜单标记。
# 必须先执行 make upgrade（app.db/game.db 结构就位）；执行前建议停止 api（会写 app.db）。
# 服务启动只建空的 game.db 结构，不写数据；这个 target 是游戏名录/榜单数据的唯一入口。
# 运行时根取自 .env 的 RUNTIME_HOST_DIR，缺失时退回 STORAGE_HOST_DIR；与容器挂的是同一个宿主目录。
index:
	@root="$${RUNTIME_HOST_DIR:-$${STORAGE_HOST_DIR:-./data/storage}}"; \
	test -d "$$root" && ! test -w "$$root" \
		&& { \
			bash scripts/log.sh fail "运行时根不可写：$$root"; \
			bash scripts/log.sh fail "（多半是 Docker 容器以 root 建的目录）先执行一次："; \
			bash scripts/log.sh fail "    sudo chown -R \"$$USER\" \"$$root\""; \
			exit 1; \
		} || true
	RUNTIME_ROOT=$${RUNTIME_HOST_DIR:-$${STORAGE_HOST_DIR:-./data/storage}} \
	STORAGE_ROOT=$${STORAGE_HOST_DIR:-./data/storage} \
	python3 -m backend.cli index

# 手动升级 app.db 的结构（<运行时根>/db/app.db）。执行前先停止服务：
# SQLite 单写者，升级期间不能有 api 在写库。根取值与 compose 一致。
# 升级代码在 upgrade/，按 system_config.db_version 逐版本执行；已是最新时只提示。
upgrade:
	@bash scripts/log.sh info "请先停止服务（docker compose down，或关闭 Windows 启动窗口）。"
	STORAGE_ROOT=$${STORAGE_HOST_DIR:-./data/storage} \
	RUNTIME_ROOT=$${RUNTIME_HOST_DIR:-$${STORAGE_HOST_DIR:-./data/storage}} \
	python3 -m upgrade $(ARGS)
