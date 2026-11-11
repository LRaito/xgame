/**
 * 用户级可自定义快捷键的注册表。
 *
 * - 这是前端行为的权威来源：默认键位、页面分组、功能名与说明都只写在这里。
 * - 键位用浏览器的 `KeyboardEvent.code`（物理键）表示，与键盘布局、输入法无关，
 *   例如 `KeyS` / `ArrowLeft` / `Backquote` / `Ctrl+Shift+KeyS`。
 * - `scope` 相同的动作同时生效，设置时不允许撞键；不同页面之间可以复用同一个键。
 * - 后端 `backend/shortcuts/keys.py` 维护同一份键位词汇，只负责落库前校验。
 */

export const MODIFIER_ORDER = ["Ctrl", "Alt", "Shift", "Meta"];

/** 主键 code → 键帽文案。只保留常见键；不在表里的键一律提示「暂不支持」。 */
export const KEY_LABELS = Object.freeze({
    KeyA: "A",
    KeyB: "B",
    KeyC: "C",
    KeyD: "D",
    KeyE: "E",
    KeyF: "F",
    KeyG: "G",
    KeyH: "H",
    KeyI: "I",
    KeyJ: "J",
    KeyK: "K",
    KeyL: "L",
    KeyM: "M",
    KeyN: "N",
    KeyO: "O",
    KeyP: "P",
    KeyQ: "Q",
    KeyR: "R",
    KeyS: "S",
    KeyT: "T",
    KeyU: "U",
    KeyV: "V",
    KeyW: "W",
    KeyX: "X",
    KeyY: "Y",
    KeyZ: "Z",
    Digit0: "0",
    Digit1: "1",
    Digit2: "2",
    Digit3: "3",
    Digit4: "4",
    Digit5: "5",
    Digit6: "6",
    Digit7: "7",
    Digit8: "8",
    Digit9: "9",
    F1: "F1",
    F2: "F2",
    F3: "F3",
    F4: "F4",
    F5: "F5",
    F6: "F6",
    F7: "F7",
    F8: "F8",
    F9: "F9",
    F10: "F10",
    F11: "F11",
    F12: "F12",
    ArrowUp: "↑",
    ArrowDown: "↓",
    ArrowLeft: "←",
    ArrowRight: "→",
    Home: "Home",
    End: "End",
    PageUp: "PgUp",
    PageDown: "PgDn",
    Insert: "Insert",
    Delete: "Delete",
    Backspace: "Backspace",
    Tab: "Tab",
    Enter: "Enter",
    Escape: "Esc",
    Space: "Space",
    Backquote: "`",
    Minus: "-",
    Equal: "=",
    BracketLeft: "[",
    BracketRight: "]",
    Backslash: "\\",
    IntlBackslash: "\\",
    Semicolon: ";",
    Quote: "'",
    Comma: ",",
    Period: ".",
    Slash: "/",
    Numpad0: "Num0",
    Numpad1: "Num1",
    Numpad2: "Num2",
    Numpad3: "Num3",
    Numpad4: "Num4",
    Numpad5: "Num5",
    Numpad6: "Num6",
    Numpad7: "Num7",
    Numpad8: "Num8",
    Numpad9: "Num9",
    NumpadAdd: "Num+",
    NumpadSubtract: "Num-",
    NumpadMultiply: "Num*",
    NumpadDivide: "Num/",
    NumpadDecimal: "Num.",
    NumpadEnter: "NumEnter",
});

/** 浏览器或系统会先一步消费、页面拦不住的组合；与后端保持一致。 */
export const RESERVED_BINDINGS = new Set([
    "Ctrl+KeyW",
    "Ctrl+Shift+KeyW",
    "Ctrl+KeyT",
    "Ctrl+Shift+KeyT",
    "Ctrl+KeyN",
    "Ctrl+Shift+KeyN",
    "Ctrl+KeyR",
    "Ctrl+Shift+KeyR",
    "Ctrl+Tab",
    "Ctrl+Shift+Tab",
    "Alt+ArrowLeft",
    "Alt+ArrowRight",
    "Alt+F4",
    "F5",
    "F11",
    "F12",
]);

/**
 * 按键管理页的展示结构：每个页面一张表，`feature` 相同的连续行合并「功能」格。
 * 一行对应一个可独立设置/清除/重置的动作。
 */
export const SHORTCUT_PAGES = [
    {
        id: "shortcut-manage",
        title: "库存管理",
        scope: "manage",
        rows: [
            {
                id: "manage.page.prev",
                feature: "分页",
                defaultBinding: "ArrowLeft",
                desc: "切换上一页",
            },
            {
                id: "manage.page.next",
                feature: "分页",
                defaultBinding: "ArrowRight",
                desc: "切换下一页",
            },
        ],
    },
    {
        id: "shortcut-discover",
        title: "游戏发现",
        scope: "discover",
        rows: [
            {
                id: "discover.page.prev",
                feature: "分页",
                defaultBinding: "ArrowLeft",
                desc: "切换上一页",
            },
            {
                id: "discover.page.next",
                feature: "分页",
                defaultBinding: "ArrowRight",
                desc: "切换下一页",
            },
        ],
    },
    {
        id: "shortcut-play",
        title: "游玩页面",
        scope: "play",
        rows: [
            {
                id: "play.sync_cloud",
                feature: "存档",
                defaultBinding: "Backquote",
                desc: "将当前进度同步至云端",
            },
            {
                id: "play.load_local",
                feature: "存档",
                defaultBinding: "Enter",
                desc: "载入本地存档并选中游戏画面",
            },
            {
                id: "play.save_manager",
                feature: "存档",
                defaultBinding: "Alt+Backquote",
                desc: "打开存档管理面板",
            },
            {
                id: "play.nds_prev",
                feature: "屏幕布局",
                defaultBinding: "Minus",
                desc: "切换到上一个 NDS 屏幕布局",
            },
            {
                id: "play.nds_next",
                feature: "屏幕布局",
                defaultBinding: "Equal",
                desc: "切换到下一个 NDS 屏幕布局",
            },
            {
                id: "play.screenshot",
                feature: "截图",
                defaultBinding: "Ctrl+Shift+KeyS",
                desc: "截取当前画面并保存到截图图库",
            },
        ],
    },
    {
        id: "shortcut-saves",
        title: "存档管理",
        scope: "saves",
        rows: [
            {
                id: "saves.sync_local",
                feature: "节点操作",
                defaultBinding: "Enter",
                desc: "把本地存档同步到选中的云端节点",
            },
            {
                id: "saves.delete",
                feature: "节点操作",
                defaultBinding: "Delete",
                desc: "删除选中的云端节点",
            },
            {
                id: "saves.move_up",
                feature: "节点操作",
                defaultBinding: "Shift+ArrowUp",
                desc: "调整选中节点的同级顺序（上移）",
            },
            {
                id: "saves.move_down",
                feature: "节点操作",
                defaultBinding: "Shift+ArrowDown",
                desc: "调整选中节点的同级顺序（下移）",
            },
        ],
    },
    {
        id: "shortcut-preview",
        title: "图片预览",
        scope: "preview",
        rows: [
            {
                id: "preview.prev",
                feature: "大图预览",
                defaultBinding: "ArrowLeft",
                desc: "切换上一张",
            },
            {
                id: "preview.next",
                feature: "大图预览",
                defaultBinding: "ArrowRight",
                desc: "切换下一张",
            },
        ],
    },
];

const ACTION_BY_ID = new Map(
    SHORTCUT_PAGES.flatMap((page) =>
        page.rows.map((row) => [
            row.id,
            { ...row, pageId: page.id, pageTitle: page.title, scope: page.scope },
        ])
    )
);

export function shortcutAction(actionId) {
    return ACTION_BY_ID.get(actionId) || null;
}

export function defaultBindingOf(actionId) {
    return ACTION_BY_ID.get(actionId)?.defaultBinding || "";
}

/** 解析绑定串；格式不合法时返回 null。 */
export function parseBinding(binding) {
    if (typeof binding !== "string" || binding === "") {
        return null;
    }
    const parts = binding.split("+");
    if (parts.length < 1 || parts.length > MODIFIER_ORDER.length + 1) {
        return null;
    }
    const code = parts[parts.length - 1];
    if (!Object.prototype.hasOwnProperty.call(KEY_LABELS, code)) {
        return null;
    }
    const modifiers = parts.slice(0, -1);
    if (new Set(modifiers).size !== modifiers.length) {
        return null;
    }
    if (modifiers.some((modifier) => !MODIFIER_ORDER.includes(modifier))) {
        return null;
    }
    return { modifiers, code };
}

/** 绑定串 → 键帽文案数组（修饰键在前，主键最后）。 */
export function bindingParts(binding) {
    const parsed = parseBinding(binding);
    if (!parsed) {
        return [];
    }
    return [
        ...MODIFIER_ORDER.filter((modifier) => parsed.modifiers.includes(modifier)),
        KEY_LABELS[parsed.code],
    ];
}

/** 主键是否匹配一次键盘事件。 */
function codeMatches(event, code) {
    if (event.code === code) {
        return true;
    }
    // 小键盘的 Enter / 方向键 / 编辑键在 event.key 上与主键盘同名，按同名键处理。
    if (code === "Space") {
        return event.key === " ";
    }
    return (
        [
            "Enter",
            "Escape",
            "Tab",
            "Backspace",
            "Delete",
            "Insert",
            "Home",
            "End",
            "PageUp",
            "PageDown",
            "ArrowUp",
            "ArrowDown",
            "ArrowLeft",
            "ArrowRight",
        ].includes(code) && event.key === code
    );
}

/** 这次按键是否正好等于绑定串：修饰键要逐项相等，不能多也不能少。 */
export function bindingMatchesEvent(binding, event) {
    const parsed = parseBinding(binding);
    if (!parsed) {
        return false;
    }
    const has = (modifier) => parsed.modifiers.includes(modifier);
    return (
        event.ctrlKey === has("Ctrl") &&
        event.altKey === has("Alt") &&
        event.shiftKey === has("Shift") &&
        event.metaKey === has("Meta") &&
        codeMatches(event, parsed.code)
    );
}

const MODIFIER_EVENT_KEYS = new Set(["Control", "Shift", "Alt", "Meta", "AltGraph"]);

/** 只按下了修饰键时返回 true：捕获时等主键，不算错误。 */
export function isModifierEvent(event) {
    return (
        MODIFIER_EVENT_KEYS.has(event.key) ||
        /^(Control|Shift|Alt|Meta)(Left|Right)$/.test(event.code || "")
    );
}

/**
 * 把一次键盘事件转成绑定串。
 * 不支持的键、被浏览器占用的组合返回 `{ error }`；只按了修饰键返回 null。
 */
export function bindingFromEvent(event) {
    if (isModifierEvent(event)) {
        return null;
    }
    const code = event.code;
    if (!Object.prototype.hasOwnProperty.call(KEY_LABELS, code)) {
        return { error: "该键暂不支持设置，请换一个键。" };
    }
    if (code === "Escape") {
        return { error: "Esc 用于取消和关闭弹框，请换一个键。" };
    }
    if (code === "Tab" && !event.ctrlKey && !event.altKey && !event.shiftKey && !event.metaKey) {
        return { error: "Tab 用于切换焦点，请配合 Ctrl / Alt / Shift 使用。" };
    }
    const modifiers = [];
    if (event.ctrlKey) {
        modifiers.push("Ctrl");
    }
    if (event.altKey) {
        modifiers.push("Alt");
    }
    if (event.shiftKey) {
        modifiers.push("Shift");
    }
    if (event.metaKey) {
        modifiers.push("Meta");
    }
    const binding = [...modifiers, code].join("+");
    if (RESERVED_BINDINGS.has(binding)) {
        return { error: "该组合键被浏览器或系统占用，无法设置。" };
    }
    return { binding };
}
