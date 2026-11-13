import { bindingMatchesEvent, bindingParts } from "@/constants/shortcuts";
import { useShortcutsStore } from "@/store/shortcuts";

/**
 * 当前账号下某个动作是否匹配这次按键。
 *
 * 只判断键位，不拦事件、不看焦点——各页面自己保留原有的守卫
 * （输入框、弹框、引擎未就绪等），避免把播放页的特殊规则搬进通用工具。
 */
export function matchesShortcut(event, actionId) {
    // 配置由 Layout / 登录流程在进入应用时拉取一次；按键处理只读缓存，
    // 避免接口异常时每次按键都发请求、弹错误提示。
    return bindingMatchesEvent(useShortcutsStore().bindingOf(actionId), event);
}

/** 当前绑定串的显示文案（如 `Esc`、`Ctrl+Shift+S`）；已关闭时返回空串。 */
export function shortcutLabel(actionId) {
    return bindingParts(useShortcutsStore().bindingOf(actionId)).join("+");
}
