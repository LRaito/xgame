import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
import { writeFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";

/**
 * 版本号：优先用外部注入（Makefile 算好的 git 短 sha，经 compose 的 build.args 进来）。
 * 构建上下文只有 frontend/，容器里看不到 .git，所以 sha 只能由外面算好传进来；
 * 拿不到就退化为构建时刻的 UTC 时间戳——保证「只要是新构建，版本一定不同」。
 * dev server 固定为 "dev"，前端见到 dev 就不启动版本轮询。
 */
function resolveAppVersion(command) {
    if (process.env.APP_VERSION) {
        return process.env.APP_VERSION;
    }
    if (command !== "build") {
        return "dev";
    }
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return [
        now.getUTCFullYear(),
        pad(now.getUTCMonth() + 1),
        pad(now.getUTCDate()),
        pad(now.getUTCHours()),
        pad(now.getUTCMinutes()),
        pad(now.getUTCSeconds()),
    ].join("");
}

/** 把同一个版本号写成 dist/version.txt，供运行中的旧页面轮询探测到「服务端换了新构建」。 */
function versionFilePlugin(version) {
    return {
        name: "x-app-version",
        apply: "build",
        writeBundle(options) {
            // 纯 ASCII、无换行、无 BOM，前端按 text/plain 直接比对
            writeFileSync(resolvePath(options.dir, "version.txt"), version, "utf8");
        },
    };
}

export default defineConfig(({ command }) => {
    const appVersion = resolveAppVersion(command);

    return {
        plugins: [vue(), versionFilePlugin(appVersion)],
        // 构建期把版本号内联进产物，dev 与 build 都生效；注入值变化会让产物内容随之变化
        define: { __APP_VERSION__: JSON.stringify(appVersion) },
        resolve: {
            alias: {
                "@": fileURLToPath(new URL("./src", import.meta.url)),
                "@components": fileURLToPath(new URL("./src/components", import.meta.url)),
            },
        },
        server: {
            port: 5173,
            proxy: {
                "/api": { target: "http://127.0.0.1:8910", changeOrigin: true },
                "/health": { target: "http://127.0.0.1:8910", changeOrigin: true },
            },
        },
    };
});
