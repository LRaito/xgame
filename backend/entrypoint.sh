#!/bin/sh
# api 容器的入口：先过根目录哨兵检查，再交给 CMD 里的 gunicorn（见 backend/Dockerfile）。
#
# 为什么要单独有这么一层：**退出必须发生在容器主进程上**。gunicorn 的 worker 起来又挂掉时，
# master 不一定跟着退出（换个退出码它就只 fork 一个新 worker 重试），容器就不会重启；
# 在 exec gunicorn 之前退出，退的就是容器主进程，compose 的 `restart: unless-stopped`
# 必然把容器重新拉起，如此反复直到有人把 .mounted 建出来（或把那个根挪出那个前缀）。
#
# 判断与日志只有一份（backend/mount_guard.py::require_mounted：数据根与运行时根的宿主路径
# 落在 Windows 盘挂载前缀（默认 /mnt，见 config.WINDOWS_MOUNT_PREFIX）下、又缺各自挂载点里的
# .mounted 时，打中文提示、等 5 秒、以非零码退出；不在那个前缀下就直接放行），
# 这里不重复实现，只把那个退出码原样透传出去。
set -e

python -c "from backend.config import get_settings; from backend.mount_guard import require_mounted; require_mounted(get_settings())"

exec "$@"
