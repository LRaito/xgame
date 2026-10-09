/**
 * 卡带图配置：游戏中心里这类游戏的封面**不单独出图**，而是把封面贴进「整张卡带图的贴纸窗」。
 *
 * 每个游戏类型一组卡带图（public 下按 URL 引用的静态文件）
 * + 两个像素几何：image 整图尺寸、label 贴纸窗（封面落位）在整图里的矩形。
 * 每个类型固定一张图（不按卡带ID 挑配色）。
 *
 * 换图必须同步改这两组数字。卡片的尺寸规则见 constants/gameCardAspect.js 与
 * GameCover.vue：卡片宽就是「正方形限制框」的边长，卡带按自身比例缩到高度触到框边
 * （竖长形状），所以在 rail（正方形框）与「全部游戏」网格里一样大。
 *
 * 贴纸窗在卡片里用**整图百分比**定位（见 GameCard.vue 的 cartLabelStyle），
 * 所以卡带图缩到多大封面都跟着窗走；封面一律拉伸填满这扇窗（object-fit: fill），
 * 不裁切、不留黑边——这就是这个类型的封面算法。
 *
 * 目前只有 GB/GBC：`.gb` 与 `.gbc` 在项目里是同一个游戏类型（`gb`，显示名 Game_Boy_Color），
 * 所以两类游戏共用这张 GBC 卡带。
 */

export const GAME_CARTRIDGES = {
    gb: {
        // 卡带底图（public/gbc-cart.png）
        url: "/gbc-cart.png",
        image: { width: 702, height: 807 },
        // 贴纸窗：机身中部那块凹槽的内沿。实测内沿 ≈ (83,246)–(611,712) = 529×467，
        // 这里取 **528×464 = 正好 99/87**（整数、比例精确；与实测差 ≤3px、居中，看不出来），
        // 封面就按这扇窗拉伸填满（GB/GBC 的封面按 99/87 出图就不会变形）
        label: { x: 84, y: 248, width: 528, height: 464 },
    },
};

/** 取该游戏类型的卡带图配置；没配到就返回 null（按普通封面渲染）。 */
export function cartridgeFor(gameType) {
    return GAME_CARTRIDGES[gameType] || null;
}
