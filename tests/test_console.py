import io
import time

from backend.console import Progress


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_progress_prints_one_stage_line_when_not_a_tty():
    stream = io.StringIO()
    progress = Progress(stream)

    progress.report("读取游戏名录", 1, 2)
    progress.report("读取游戏名录", 2, 2)
    progress.report("优化索引")
    progress.finish()

    assert stream.getvalue() == "[INFO] 读取游戏名录\n[INFO] 优化索引\n"


def test_progress_draws_percentage_bar_in_tty():
    stream = _Tty()
    progress = Progress(stream)

    progress.report("写入游戏名录", 0, 4)
    progress.report("写入游戏名录", 2, 4)
    progress.report("写入游戏名录", 4, 4)
    progress.finish()

    out = stream.getvalue()
    assert "\r" in out
    assert " 50%" in out
    assert "100%" in out
    assert out.endswith("\n")


def test_progress_spins_on_stages_without_percentage():
    stream = _Tty()
    progress = Progress(stream)

    progress.report("优化索引")
    time.sleep(0.4)
    progress.finish()

    out = stream.getvalue()
    assert "优化索引" in out
    assert out.endswith("\n")
