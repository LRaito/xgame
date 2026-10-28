# 基础镜像固定到具体补丁版本 + 发行版代号（不用 python:3.12-slim 这类浮动标签）：
# 浮动标签会在上游重发时悄悄换掉 Python 版本与 Debian 基线，构建产物跟着变、还难排查。
# 升级请手动改这一行（改完跑一遍 pytest 再上线）。
FROM python:3.12.15-slim-trixie

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt

COPY backend/ ./backend/
# 入口脚本要在 exec gunicorn 之前过一道数据根目录哨兵检查（缺 .mounted 就退出、让 compose
# 重启容器，见 backend/mount_guard.py）。显式给执行位，别指望从 git 带过来的权限位。
RUN chmod +x backend/entrypoint.sh

# 两个根目录：宿主目录经 compose 挂到这两个固定路径（见根目录 docker-compose.yml）。
# 游戏文件与检索索引在 STORAGE_ROOT 下面，SQLite 库在 RUNTIME_ROOT 下面的 db/ 里
# （backend/config.py 的 DB_SUBDIR）；月度备份写在 STORAGE_ROOT 的 db/ 里。
# 这是后端进程唯一认的**业务**环境变量，其余配置都写死在 backend/config.py。
# （compose 另外会传 STORAGE_HOST_DIR / RUNTIME_HOST_DIR，只给启动时的哨兵判断用——
# 容器里看不出宿主路径。）
ENV STORAGE_ROOT=/data
ENV RUNTIME_ROOT=/runtime

# 中国上海时区：日志时间、月度备份文件名（<YYYY-MM>.db）与索引里的时间戳都按本地时间走。
# 基础镜像自带 /usr/share/zoneinfo（tzdata），所以只设环境变量 + 指向时区文件即可；
# 库里的 created_at 等仍是 UTC（代码用 datetime.now(timezone.utc)），不受影响。
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

EXPOSE 8910

# ENTRYPOINT 只做启动前的哨兵检查，真正的服务命令留在 CMD 里（unix 惯例：ENTRYPOINT 固定、
# CMD 可被覆盖），两者合起来等价于「检查通过后跑下面的 gunicorn」。
ENTRYPOINT ["/app/backend/entrypoint.sh"]
CMD ["gunicorn", "backend.asgi:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8910", "--workers", "1", "--threads", "8", "--timeout", "300"]
