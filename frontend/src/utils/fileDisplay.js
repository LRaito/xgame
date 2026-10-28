const VIEW_MODE_KEY = "x_files_view_mode";

const IMAGE_EXT = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico", "heic"];
const VIDEO_EXT = ["mp4", "mkv", "mov", "avi", "wmv", "flv", "webm", "m4v"];
const AUDIO_EXT = ["mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"];
const ARCHIVE_EXT = ["zip", "rar", "7z", "tar", "gz", "tgz", "bz2"];
const PDF_EXT = ["pdf"];
const DOC_EXT = ["doc", "docx", "rtf", "odt", "pages"];
const SHEET_EXT = ["xls", "xlsx", "csv", "ods", "numbers"];
const SLIDE_EXT = ["ppt", "pptx", "odp", "key"];
const CODE_EXT = [
    "js", "ts", "vue", "py", "go", "rs", "java", "c", "cpp", "h", "json", "yml", "yaml",
    "xml", "html", "css", "sh", "sql", "md", "toml",
];
const TEXT_EXT = ["txt", "log", "ini", "conf"];

export function getViewMode() {
    return sessionStorage.getItem(VIEW_MODE_KEY) === "grid" ? "grid" : "list";
}

export function setViewMode(mode) {
    sessionStorage.setItem(VIEW_MODE_KEY, mode === "grid" ? "grid" : "list");
}

export function formatBytes(value) {
    if (value == null || value === "") {
        return "—";
    }
    const num = Number(value);
    if (Number.isNaN(num) || num < 0) {
        return "—";
    }
    if (num < 1024) {
        return `${num} B`;
    }
    const units = ["KB", "MB", "GB", "TB"];
    let size = num / 1024;
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024;
        unit += 1;
    }
    const digits = size >= 100 || unit === 0 ? 0 : size >= 10 ? 1 : 2;
    return `${size.toFixed(digits)} ${units[unit]}`;
}

/**
 * 解析后端返回的 datetime。
 *
 * 库里存的是 UTC（`created_at` 等用 `datetime.now(timezone.utc)` 生成），但 SQLite 不保留
 * tzinfo，接口序列化出来就是没有时区后缀的 `2026-10-28T13:35:23.455203`。这种字符串浏览器
 * 会按**本地时间**解析，在北京时区下显示就整整差 8 小时；这里统一按 UTC 解析，再由调用方
 * 按浏览器本地时区展示。已经带 `Z` / `+08:00` 之类后缀的、以及时间戳数字则原样交给 Date。
 */
export function parseApiDate(value) {
    if (typeof value !== "string") {
        return new Date(value);
    }
    const text = value.trim();
    const naive =
        /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(text) &&
        !/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(text);
    return new Date(naive ? `${text.replace(" ", "T")}Z` : text);
}

function pad2(n) {
    return String(n).padStart(2, "0");
}

export function formatDateTime(iso) {
    if (!iso) {
        return "—";
    }
    const date = parseApiDate(iso);
    if (Number.isNaN(date.getTime())) {
        return iso;
    }
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

/** 同 formatDateTime，但精确到秒（游戏管理的更新时间列按 19 个字宽排版）。 */
export function formatDateTimeSeconds(iso) {
    if (!iso) {
        return "—";
    }
    const date = parseApiDate(iso);
    if (Number.isNaN(date.getTime())) {
        return iso;
    }
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

export function extensionOf(name) {
    const base = (name || "").split("/").pop() || "";
    const dot = base.lastIndexOf(".");
    if (dot <= 0) {
        return "";
    }
    return base.slice(dot + 1).toLowerCase();
}

export function fileKind(name, mime) {
    const ext = extensionOf(name);
    const type = (mime || "").toLowerCase();
    if (type.startsWith("image/") || IMAGE_EXT.includes(ext)) {
        return "image";
    }
    if (type.startsWith("video/") || VIDEO_EXT.includes(ext)) {
        return "video";
    }
    if (type.startsWith("audio/") || AUDIO_EXT.includes(ext)) {
        return "audio";
    }
    if (ARCHIVE_EXT.includes(ext)) {
        return "archive";
    }
    if (type === "application/pdf" || PDF_EXT.includes(ext)) {
        return "pdf";
    }
    if (DOC_EXT.includes(ext)) {
        return "doc";
    }
    if (SHEET_EXT.includes(ext)) {
        return "sheet";
    }
    if (SLIDE_EXT.includes(ext)) {
        return "slide";
    }
    if (CODE_EXT.includes(ext)) {
        return "code";
    }
    if (type.startsWith("text/") || TEXT_EXT.includes(ext)) {
        return "text";
    }
    return "file";
}

export { VIEW_MODE_KEY };
