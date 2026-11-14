"""数据库结构版本不匹配时的启动阻塞。

不照搬 ``mount_guard`` 的「等几秒后退出」：这里按需求**永久阻塞**，进程不退出、
也不进入 FastAPI 建 app 阶段，因此不会监听端口。日志只由 ``create_app()`` 打一次，
Docker 的 gunicorn worker 超时重生后会再次打印。
"""

import time
from typing import NoReturn

# 醒来只是为了让 Python 有机会响应 KeyboardInterrupt；没有业务含义
BLOCK_SECONDS = 3600


def block_forever() -> NoReturn:
    while True:
        time.sleep(BLOCK_SECONDS)
