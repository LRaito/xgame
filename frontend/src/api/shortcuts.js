import request from "@/utils/request";

/** 当前账号的全部快捷键覆盖配置；没有出现过的动作使用前端默认键位。 */
export function listShortcutsAPI() {
    return request({ url: "/api/user-shortcuts", method: "get" });
}

/** 设置一个动作的键位；`binding` 传空串表示关闭该快捷键。 */
export function setShortcutAPI(actionId, binding) {
    return request({
        url: `/api/user-shortcuts/${encodeURIComponent(actionId)}`,
        method: "put",
        data: { binding },
    });
}

/** 删除覆盖配置，恢复默认键位。 */
export function resetShortcutAPI(actionId) {
    return request({
        url: `/api/user-shortcuts/${encodeURIComponent(actionId)}`,
        method: "delete",
    });
}
