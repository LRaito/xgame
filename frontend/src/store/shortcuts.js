import { defineStore } from "pinia";
import { listShortcutsAPI, resetShortcutAPI, setShortcutAPI } from "@/api/shortcuts";
import { defaultBindingOf } from "@/constants/shortcuts";

// 单飞：同一时刻只发一次列表请求；登出时用代次丢弃迟到的响应，
// 否则换账号后可能把上一个账号的覆盖配置当成新账号的。
let pending = null;
let generation = 0;

export const useShortcutsStore = defineStore("shortcuts", {
    state: () => ({
        // action_id -> 绑定串。空串表示用户关闭了该快捷键；没有键 = 使用默认值。
        overrides: {},
        loaded: false,
    }),
    getters: {
        /** 当前生效的绑定串；空串表示该快捷键已关闭。 */
        // 直接按键读取而不是 hasOwnProperty：Vue 的 hasOwnProperty 不追踪响应性，
        // 页面在保存后会读不到新值。
        bindingOf: (state) => (actionId) => {
            const override = state.overrides[actionId];
            return override === undefined ? defaultBindingOf(actionId) : override;
        },
        /** 该动作是否有用户覆盖（自定义或关闭）。 */
        isOverridden: (state) => (actionId) =>
            state.overrides[actionId] !== undefined,
    },
    actions: {
        async ensureLoaded() {
            if (this.loaded) {
                return this.overrides;
            }
            if (!pending) {
                pending = this._fetchOverrides().finally(() => {
                    pending = null;
                });
            }
            return pending;
        },
        async _fetchOverrides() {
            const requestGeneration = generation;
            const data = await listShortcutsAPI();
            // 请求在途时登出或换了账号：这次结果作废。
            if (requestGeneration !== generation) {
                return this.overrides;
            }
            const overrides = {};
            for (const item of data?.overrides || []) {
                if (item && typeof item.action_id === "string") {
                    overrides[item.action_id] = item.binding || "";
                }
            }
            this.overrides = overrides;
            this.loaded = true;
            return overrides;
        },
        async setBinding(actionId, binding) {
            const item = await setShortcutAPI(actionId, binding);
            this.overrides = {
                ...this.overrides,
                [actionId]: item.binding ?? binding,
            };
            return item;
        },
        async resetBinding(actionId) {
            await resetShortcutAPI(actionId);
            const overrides = { ...this.overrides };
            delete overrides[actionId];
            this.overrides = overrides;
        },
        clearAll() {
            generation += 1;
            pending = null;
            this.overrides = {};
            this.loaded = false;
        },
    },
});
