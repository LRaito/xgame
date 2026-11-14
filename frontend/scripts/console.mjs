// 前端构建脚本的控制台输出：固定状态标签 + 颜色。
// 终端带颜色，管道 / 重定向时退回纯文本。标签与颜色的唯一出处。

const TAGS = { ok: "[ OK ]", fail: "[FAIL]", warn: "[WARN]", info: "[INFO]" };
const COLORS = { ok: 32, fail: 31, warn: 33, info: 36 };

function emit(level, message = "") {
    const stream = level === "fail" ? process.stderr : process.stdout;
    const tag = TAGS[level];
    const color = COLORS[level];
    const colored = Boolean(stream.isTTY);
    for (const line of String(message).split(/\r?\n/)) {
        stream.write(
            colored
                ? `\x1b[${color}m${tag}\x1b[0m ${line}\n`
                : `${tag} ${line}\n`
        );
    }
}

export const ok = (message = "") => emit("ok", message);
export const fail = (message = "") => emit("fail", message);
export const warn = (message = "") => emit("warn", message);
export const info = (message = "") => emit("info", message);
