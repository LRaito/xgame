"""快捷键键位的合法词汇与规范化。

绑定串的形态是 `修饰键+…+主键`，例如 `Ctrl+Shift+KeyS`、`Alt+Backquote`、`Enter`。
主键一律用浏览器的 `KeyboardEvent.code`（物理键），与键盘布局、输入法无关；
前端 `frontend/src/constants/shortcuts.js` 维护同一份词汇与展示文案。
空串 `""` 是用户主动关闭该快捷键的标记，不在这里校验。
"""

from __future__ import annotations

import re

from backend.errors import ValidationError

# 输出时修饰键固定按这个顺序，保证数据库里同一个组合只有一种写法。
MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Meta")
_MODIFIER_SET = frozenset(MODIFIER_ORDER)

_LETTER_KEYS = tuple(f"Key{chr(code)}" for code in range(ord("A"), ord("Z") + 1))
_DIGIT_KEYS = tuple(f"Digit{number}" for number in range(10))
_FUNCTION_KEYS = tuple(f"F{number}" for number in range(1, 13))
_ARROW_KEYS = ("ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight")
_NAVIGATION_KEYS = ("Home", "End", "PageUp", "PageDown", "Insert", "Delete")
_EDIT_KEYS = ("Backspace", "Tab", "Enter", "Escape", "Space")
_PUNCTUATION_KEYS = (
    "Backquote",
    "Minus",
    "Equal",
    "BracketLeft",
    "BracketRight",
    "Backslash",
    "IntlBackslash",
    "Semicolon",
    "Quote",
    "Comma",
    "Period",
    "Slash",
)
_NUMPAD_KEYS = (
    *(f"Numpad{number}" for number in range(10)),
    "NumpadAdd",
    "NumpadSubtract",
    "NumpadMultiply",
    "NumpadDivide",
    "NumpadDecimal",
    "NumpadEnter",
)

SUPPORTED_KEYS = frozenset(
    (
        *_LETTER_KEYS,
        *_DIGIT_KEYS,
        *_FUNCTION_KEYS,
        *_ARROW_KEYS,
        *_NAVIGATION_KEYS,
        *_EDIT_KEYS,
        *_PUNCTUATION_KEYS,
        *_NUMPAD_KEYS,
    )
)

# 浏览器或系统会先一步消费、页面拦不住的组合。与前端 RESERVED_BINDINGS 保持一致。
RESERVED_BINDINGS = frozenset(
    {
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
    }
)

_ACTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
_MAX_BINDING_LENGTH = 64


def normalize_binding(raw: str) -> str:
    """校验并返回规范写法的绑定串；空串表示关闭该快捷键。"""
    if not isinstance(raw, str):
        raise ValidationError("快捷键格式错误。")
    binding = raw.strip()
    if binding == "":
        return ""
    if len(binding) > _MAX_BINDING_LENGTH:
        raise ValidationError("快捷键过长。")

    parts = [part.strip() for part in binding.split("+")]
    key = parts[-1]
    modifiers = parts[:-1]

    if key not in SUPPORTED_KEYS:
        raise ValidationError("该键暂不支持设置，请换一个键。")
    if any(modifier not in _MODIFIER_SET for modifier in modifiers):
        raise ValidationError("快捷键的修饰键不合法。")
    if len(set(modifiers)) != len(modifiers):
        raise ValidationError("快捷键的修饰键重复。")

    normalized = "+".join(
        [*(modifier for modifier in MODIFIER_ORDER if modifier in modifiers), key]
    )
    if key == "Escape":
        raise ValidationError("Esc 用于取消和关闭弹框，请换一个键。")
    if normalized == "Tab":
        raise ValidationError("Tab 用于切换焦点，请配合 Ctrl / Alt / Shift 使用。")
    if normalized in RESERVED_BINDINGS:
        raise ValidationError("该组合键被浏览器或系统占用，无法设置。")
    return normalized


def require_action_id(action_id: str) -> str:
    """动作标识只允许小写字母、数字、点和下划线，避免落库垃圾键。"""
    if not _ACTION_ID_PATTERN.fullmatch(action_id or ""):
        raise ValidationError("快捷键标识不合法。")
    return action_id
