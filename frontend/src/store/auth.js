import { defineStore } from "pinia";
import { loginAPI, logoutAPI, meAPI, registerAPI } from "@/api/auth";
import { clearSession, getUsername, setUsername } from "@/utils/auth";

export const useAuthStore = defineStore("auth", {
    state: () => ({
        username: getUsername(),
    }),
    actions: {
        async fetchMe() {
            const data = await meAPI();
            this.username = data.username;
            setUsername(data.username);
            return data;
        },
        async login(payload) {
            const data = await loginAPI(payload);
            this.username = data.username;
            setUsername(data.username);
            return data;
        },
        async register(payload) {
            const data = await registerAPI(payload);
            this.username = data.username;
            setUsername(data.username);
            return data;
        },
        async logout() {
            const hasSession = Boolean(this.username);
            try {
                if (hasSession) {
                    await logoutAPI();
                }
            } finally {
                this.username = "";
                clearSession();
            }
        },
    },
});
