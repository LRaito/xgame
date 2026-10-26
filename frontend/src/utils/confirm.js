import { ElMessageBox } from "element-plus";

// 所有 ElMessageBox 确认框共用：取消文案、禁止点遮罩关闭、warning 图标。
const BASE = {
    cancelButtonText: "取消",
    closeOnClickModal: false,
    distinguishCancelAndClose: false,
    type: "warning",
};

/**
 * 通用确认框。返回 true = 确认，false = 取消/关闭。
 * danger 为 true 时确认按钮用统一的红色危险样式。
 */
export async function confirmAction(message, options = {}) {
    const {
        title = "请确认",
        confirmText = "确定",
        cancelText = "取消",
        danger = false,
        type = "warning",
        ...rest
    } = options;
    try {
        await ElMessageBox.confirm(message, title, {
            ...BASE,
            ...rest,
            type,
            confirmButtonText: confirmText,
            cancelButtonText: cancelText,
            confirmButtonClass: danger ? "el-button--danger" : "",
        });
        return true;
    } catch {
        return false;
    }
}

/** 删除类确认：红色「删除」按钮。 */
export function dangerConfirm(message, options = {}) {
    return confirmAction(message, {
        title: "删除确认",
        confirmText: "删除",
        danger: true,
        ...options,
    });
}

/** 删除类输入确认（例如删游戏要手打卡带 ID）：红色「删除」按钮。 */
export async function dangerPrompt(message, options = {}) {
    const {
        title = "删除确认",
        confirmText = "删除",
        cancelText = "取消",
        ...rest
    } = options;
    try {
        await ElMessageBox.prompt(message, title, {
            ...BASE,
            ...rest,
            type: "warning",
            confirmButtonText: confirmText,
            cancelButtonText: cancelText,
            confirmButtonClass: "el-button--danger",
        });
        return true;
    } catch {
        return false;
    }
}
