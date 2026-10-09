import { markGamePlayedAPI } from "@/api/games";

/**
 * 「最近游玩」上报：即发即忘，绝不 await、绝不抛错。
 *
 * 三个播放页在真正拉起播放器的那一刻各调一次；上报失败只丢一条最近记录，
 * 不影响游玩。不做本地去重：SPA 内「A → 列表 → B → A」会把第二次 A 吃掉，
 * 导致 A 回不到游戏中心 rail 的首位；重复上报只是把时间往后推，无害。
 */
export function reportGamePlayed(gameId) {
    const id = Number(gameId);
    if (!id) {
        return;
    }
    markGamePlayedAPI(id).catch(() => {});
}
