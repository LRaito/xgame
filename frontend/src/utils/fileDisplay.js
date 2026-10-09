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

export function formatDateTime(iso) {
    if (!iso) {
        return "—";
    }
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
        return iso;
    }
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
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
