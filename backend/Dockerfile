# 基础镜像固定到具体补丁版本 + 发行版代号（不用 python:3.12-slim 这类浮动标签）：
# 浮动标签会在上游重发时悄悄换掉 Python 版本与 Debian 基线，构建产物跟着变、还难排查。
# 升级请手动改这一行（改完跑一遍 pytest 再上线）。
FROM python:3.12.15-slim-trixie

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt

COPY backend/ ./backend/

# 数据根目录：宿主目录经 compose 挂到这个固定路径（见根目录 docker-compose.yml）。
# 游戏文件在它下面，SQLite 固定在它下面的 db/ 里（backend/config.py 的 DB_SUBDIR）。
# 这是后端进程唯一认的环境变量（`STORAGE_ROOT`），其余配置都写死在 backend/config.py。
ENV STORAGE_ROOT=/data

EXPOSE 8910

# 数据根目录的哨兵文件（.mounted）由 create_app() 启动时补上，不再需要入口脚本。
CMD ["gunicorn", "backend.asgi:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8910", "--workers", "1", "--threads", "8", "--timeout", "300"]
