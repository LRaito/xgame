import { cpSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules/@ruffle-rs/ruffle");
const dest = join(root, "public/ruffle");

mkdirSync(dest, { recursive: true });

for (const file of readdirSync(src)) {
    if (file.endsWith(".js") || file.endsWith(".wasm")) {
        cpSync(join(src, file), join(dest, file));
    }
}

console.log("已复制 Ruffle 运行时到 public/ruffle/");
