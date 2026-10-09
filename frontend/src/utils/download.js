/**
 * 触发同源流式下载。文件字节由后端从存储目录代理出来（浏览器不直连磁盘）。
 * 同源 GET 自动携带 session cookie；文件名由后端 Content-Disposition 决定。
 */
export function downloadViaPath(path) {
    const link = document.createElement("a");
    link.href = path;
    link.rel = "noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
}
