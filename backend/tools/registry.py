from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    description: str
    path: str


def list_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            id="games",
            name="游戏中心",
            description="Flash 与 8/16-bit 主机游戏，浏览器内即开即玩。",
            path="/games",
        ),
        ToolSpec(
            id="games-manage",
            name="游戏管理",
            description="上传与管理 Flash / 主机游戏本体、封面与元数据。",
            path="/games/manage",
        ),
    ]
