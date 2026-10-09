/**
 * 游戏进度（progress）展示层配置。
 *
 * 后端 backend/games/stats_service.py 的 GAME_PROGRESS 是「可落库、接口只认」
 * 的权威来源；这里只负责 UI 展示：下拉筛选的选项、卡片角标文案。
 * 两者新增/修改取值时需同步。
 *
 * 进度不会因游玩自动变更：只有游戏中心右键菜单手动设置才会变。
 */

export const PROGRESS_NOT_STARTED = "not_started";
export const PROGRESS_IN_PROGRESS = "in_progress";
export const PROGRESS_COMPLETED = "completed";

export const GAME_PROGRESS_LIST = [
    { value: PROGRESS_NOT_STARTED, label: "未开始" },
    { value: PROGRESS_IN_PROGRESS, label: "进行中" },
    { value: PROGRESS_COMPLETED, label: "已通关" },
];
