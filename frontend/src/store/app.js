import { defineStore } from "pinia";

export const useAppStore = defineStore("app", {
    state: () => ({
        sidebarCollapsed: false,
    }),
    actions: {
        toggleSidebar() {
            this.sidebarCollapsed = !this.sidebarCollapsed;
        },
    },
});
