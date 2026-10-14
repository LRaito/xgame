"""游戏检索的文本处理：归一化、剥标签、查询构造。

与 `backend/games/paths.py` 同一种定位——被多个模块共用的**纯规则**，不碰 SQL、不碰 HTTP。
这里只有一份实现，**索引期（`search_index.py`）与查询期（`search_service.py`）必须都走它**：
两边任何一处漏调，中文子串就会搜不到（FTS5 是按 token 匹配的）。

分词选型（改之前先读完，别「优化」成 trigram 或裸 unicode61）：

- 裸 `unicode61` 会把整串中文当成**一个 token**，搜任何子串都是 0 命中；
- `trigram` 少于 3 个字的查询全废（中文名两个字、「奥」这种单字查询直接不可用）；
- 所以这里把**每个汉字拆成一个 token**（用空格隔开再交给 `unicode61`），
  查询时把整串包成**短语**（`"马 里 奥"`），语义就等于子串匹配。
"""

import re
import unicodedata

# 汉字（含扩展 A 区与兼容区）。拆字只认这三段，拉丁字母/数字保持整词。
_CJK = re.compile(r"([㐀-䶿一-鿿豈-﫿])")

# 结尾的标签组：(Japan)、(En,Ja)、(Rev A)、[!]、[a1] …… 只认半角括号——调用前已经过 NFKC。
_TAIL_TAG = re.compile(r"\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$")


def strip_tags(text: str) -> str:
    """剥掉结尾**连续的**地区/语言/版本标签，只用于进索引（展示始终是原文）。

    'FF VII (Europe) (Disc 1)' -> 'FF VII'
    '蝙蝠侠与罗宾的冒险 (美版, 欧版) (Beta)' -> '蝙蝠侠与罗宾的冒险'

    整串**全是**标签时保留原串：名录里有 38 行中文名本身就是 `[PS2]` 这样的平台标签，
    剥空等于把这一行从检索里彻底删掉，回退更安全。剥完不会返回空串。
    """
    original = text or ""
    prev = None
    while prev != text:
        prev, text = text, _TAIL_TAG.sub("", text)
    return text.strip() or original.strip()


def uni(text: str) -> str:
    """汉字逐字拆开、其余（拉丁/数字）保持整词；顺带做 NFKC 归一。

    '超级马里奥3D世界' -> '超 级 马 里 奥 3D 世 界'

    NFKC 是为了全角字母/数字（名录里有 `ＴＩＭＥ ＡＮＤ ＴＩＤＥ` 这种写法）能与半角输入互搜，
    也让全角括号在 `strip_tags` 之前变成半角。
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    return " ".join(_CJK.sub(r" \1 ", normalized).split())


def index_text(text: str) -> str:
    """进索引、以及构造查询词时**唯一**的文本入口：NFKC → 剥结尾标签 → 汉字拆字。

    区域/语言/版本标签刻意不进索引：名录里 76% 的英文名和 38% 的中文名带这种后缀，
    留着的话搜 `japan` 会命中一万多条，纯噪声。
    """
    return uni(strip_tags(unicodedata.normalize("NFKC", text or "")))


def fts_query(raw: str | None) -> str | None:
    """把用户输入转成 FTS5 的 MATCH 表达式；全是空词时返回 None（调用方走全量列表）。

    - **按空白切词，每个词各自包成短语**，词间用 AND：整句拼成一个短语会让
      `final fantasy vii` 搜不到 `Final Fantasy VII (Europe)`（词间还夹着别的 token）。
    - 词尾的 `*` 是前缀匹配（`mario*`）。对中文没有额外意义（每个汉字本来就是一个 token）。
    - `"` 必须转义成 `""`：不转义时用户输入一个引号就能构造出非法语法，MATCH 直接抛异常。
    """
    parts: list[str] = []
    for token in (raw or "").split():
        prefix = token.endswith("*")
        token = token.rstrip("*")
        if not token:
            continue
        body = index_text(token).replace('"', '""')
        if not body:
            continue
        parts.append(f'"{body}"{"*" if prefix else ""}')
    return " AND ".join(parts) or None
