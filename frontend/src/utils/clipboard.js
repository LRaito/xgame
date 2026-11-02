/**
 * 写剪贴板（CopyButton 与游戏榜单的卡带ID共用这一份）。
 *
 * `navigator.clipboard` 只在安全上下文里有（HTTPS 或 localhost）：Windows「解压即用」包
 * 在局域网里是 http://<IP>:8910，手机和别的电脑打开时这个对象根本不存在。所以留一条老办法
 * 兜底——用隐藏的 textarea + execCommand，它在 http 下仍可用。
 *
 * 返回是否成功；提示文案由调用方决定（各处要说的不一样）。
 */
export async function writeClipboard(value) {
    if (navigator.clipboard?.writeText) {
        try {
            await navigator.clipboard.writeText(value);
            return true;
        } catch {
            // 落到下面的兜底（用户拒绝授权、或文档不在焦点上时会走这里）
        }
    }
    const holder = document.createElement("textarea");
    holder.value = value;
    holder.setAttribute("readonly", "");
    holder.style.position = "fixed";
    holder.style.opacity = "0";
    document.body.appendChild(holder);
    try {
        holder.select();
        return document.execCommand("copy");
    } catch {
        return false;
    } finally {
        document.body.removeChild(holder);
    }
}
