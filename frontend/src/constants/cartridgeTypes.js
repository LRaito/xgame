/**
 * 卡带类型（cartridge_type）展示层配置。
 *
 * 后端 backend/games/models.py 的 CARTRIDGE_TYPE_* / CARTRIDGE_TYPES_BY_GAME_TYPE
 * 是「可落库、接口只认」的权威来源；这里只负责 UI 展示：详情里的国旗、
 * 添加/编辑弹框的单选项、游戏中心按卡带类型分行的顺序。两者新增/修改取值时需同步。
 *
 * 「默认」是真实值而不是空值：每个游戏始终有且只有一个卡带类型。
 * 目前只有 FC NES 区分日版/美版，其余游戏类型只有「默认」。
 *
 * UI 上不用文字、只显示国旗（frontend/public/flags/，22×16 的普通静态文件，
 * 与 flash-logo.png / gba-shell.png 一样按 URL 引用）。图片按国家/地区英文全称命名
 * （Japan.png、USA.png、United Kingdom.png…），目录里已经放好了其它地区
 * （Australia/Brazil/Canada/Europe/France/Germany/Italy/Scandinavia/Spain…），
 * 以后要扩取值只需在后端 CARTRIDGE_TYPES_BY_GAME_TYPE 与这里同时加一项。
 */

export const CARTRIDGE_TYPE_DEFAULT = "default";

/** 全部取值，顺序即游戏中心分组分行的顺序。 */
export const CARTRIDGE_TYPE_LIST = [
    { value: "jp", label: "日版", flag: "/flags/Japan.png" },
    { value: "us", label: "美版", flag: "/flags/USA.png" },
    // 「默认」没有地区：用一张空白图占位，不借用任何国家的旗
    { value: CARTRIDGE_TYPE_DEFAULT, label: "默认", flag: "/flags/Default.png" },
];

const DEFAULT_META = CARTRIDGE_TYPE_LIST.find(
    (item) => item.value === CARTRIDGE_TYPE_DEFAULT
);
const DEFAULT_ONLY = [DEFAULT_META];

/** 某个游戏类型可选的卡带类型；未知类型只给「默认」。 */
export function cartridgeTypesFor(gameType) {
    return gameType === "nes" ? CARTRIDGE_TYPE_LIST : DEFAULT_ONLY;
}

/**
 * 选项列表的排序，给单选用：「默认」永远第一，其余按取值字符串排（以后加地区照这个规则）。
 * 与 CARTRIDGE_TYPE_LIST 的顺序（游戏中心分行用）是两回事，别混用。
 */
export function sortedCartridgeTypes(items) {
    return [...items].sort((a, b) => {
        if (a.value === CARTRIDGE_TYPE_DEFAULT) {
            return -1;
        }
        if (b.value === CARTRIDGE_TYPE_DEFAULT) {
            return 1;
        }
        return a.value < b.value ? -1 : a.value > b.value ? 1 : 0;
    });
}

/** 卡带类型的展示配置；未知/空值回退为「默认」。 */
function cartridgeTypeMeta(value) {
    return CARTRIDGE_TYPE_LIST.find((item) => item.value === value) || DEFAULT_META;
}

/** 卡带类型的中文名，用作图片的 alt（界面上不直接显示文字）。 */
export function cartridgeTypeLabel(value) {
    return cartridgeTypeMeta(value).label;
}

/** 卡带类型对应的国旗图片地址（public/flags 下的静态文件）。 */
export function cartridgeTypeFlag(value) {
    return cartridgeTypeMeta(value).flag;
}
