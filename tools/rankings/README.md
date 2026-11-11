# 榜单数据补全工具

`fill_data.py` 用来补全 `backend/search/rankings/*.csv` 的两列：

- **中文名**：先查 `backend/search/catalog/` 的中英名录；同机种优先，跨机种只接受
  唯一（或明显占多数）的译名。
- **卡带 ID**：只写权威 DAT 里逐字存在的编号，查不到就留空。

## 准确性与优先级

卡带 ID **宁缺毋滥**，规则与 `../../backend/search/rankings/README.md` 一致：

1. 美版 ID + 日版 ID（最多两个）；
2. 只有美版 ID；
3. 只有日版 ID；
4. 一个其他地区 ID；
5. 都没有就留空。

数据源：

- MAME `hash/*.xml` 的 `<info name="serial">`。同一标题会按地区拆成多条，
  工具会先合并再按上面的顺序选号。
- No-Intro DAT 的 `<rom serial="...">`。NDS / GBA / N64 / VB 的 4 位游戏编号
  会按官方编号规则补成 `NTR-XXXX-USA` 这类完整编号；这个规则用现有榜单里
  已填的编号验证过，命中率 99% 左右。
- 世嘉系 DAT 里有些 serial 只是完整编号的后半截（如 `4407`、`2530-50`），
  工具按现有榜单出现过的编号形状过滤，认不出的直接丢弃。

`apply` 还会再校验一次：卡带 ID 必须是 1~2 个、格式合法，并且建议里带
`verified: true` 和 `source_url`；来源域名还必须属于 Redump、No-Intro、MAME、
Wikipedia、Sega Retro、GameFAQs、厂商官网等权威站点。没有来源或来源不认的 ID
不会写入。

## 命令

```bash
# 1. 同步 MAME（jsdelivr）；No-Intro 用本地全量 zip 解出需要的几个 DAT
python tools/rankings/fill_data.py sync --no-intro-zip ~/Downloads/no-intro.zip

# 2. 试运行：看每个机种能补多少
python tools/rankings/fill_data.py fill

# 3. 真正写回 CSV
python tools/rankings/fill_data.py fill --write --report /tmp/ranking-report.json

# 4. 输出待补清单，交给人工/联网补录
python tools/rankings/fill_data.py gaps --outdir /tmp/xgame-ranking-gaps

# 5. 应用联网调研建议（只填空白）
python tools/rankings/fill_data.py apply suggestions.json --write
```

## 补 `backend/search/catalog/` 的中文名

catalog 是游戏名录，格式是两列 `中文名,英文名`。空缺的中文名可以用同一个工具补：

```bash
# 1. 从同文件其他地区版本、榜单、旧版 ranking.csv、其他 catalog 文件自动补
python tools/rankings/fill_data.py catalog-fill --write --report /tmp/catalog-report.json

# 2. 输出仍未补的清单，按 catalog 文件拆分，交给联网调研
python tools/rankings/fill_data.py catalog-gaps --outdir /tmp/xgame-catalog-gaps

# 3. 应用联网建议（每条都必须带 source_url）
python tools/rankings/fill_data.py catalog-apply suggestions.json --write
```

自动补全的优先级：同一 catalog 文件 → 同机种榜单 → 其他榜单 → 旧版五列
ranking.csv → 其他 catalog 文件。跨来源匹配要求译名唯一或明显占多数，
避免把同名不同游戏翻错。`catalog-apply` 只填空白单元格，不覆盖已有译名。

缓存目录默认 `~/.cache/xgame-ranking-dats`，可用 `--cache` 或环境变量
`XGAME_DAT_CACHE` 覆盖。缓存不进仓库。

## 联网调研建议格式

```json
[
  {
    "platform": "nds",
    "line": 123,
    "en": "Osu! Tatakae! Ouendan",
    "zh": "押忍！战斗！应援团",
    "source_url": "https://zh.moegirl.org.cn/Osu!_Tatakae!_Ouendan"
  },
  {
    "platform": "nes",
    "line": 45,
    "en": "Super Mario Bros.",
    "cartridge_id": "NES-SM-USA;HVC-SM",
    "source": "web",
    "source_url": "https://example.com/source",
    "verified": true
  }
]
```

- `line` 是 CSV 的物理行号（含表头），可直接用 `gaps` 输出的清单。
- `en` 必须与 CSV 里的英文名一致，`apply` 会按归一化标题再核对一次。
- 每条建议都必须带 `source_url`：中文名要有明确写出译名的页面，卡带 ID
  还要额外带 `verified: true`。
- 中文名会去掉 `[PS2]`、`（美版）`、`(Beta)` 这类平台/地区/版本标签。
- 卡带 ID 不填 `verified`、没有 `source_url`、或来源域名不在权威站点列表里，
  都会被拒绝。

## 注意

- 工具只填空白单元格，不覆盖已有值。已有的中文名/卡带 ID 是人工整理结果，
  优先级高于自动补全。
- 重新跑 MobyGames 抓取脚本会覆盖中文名与卡带 ID；重抓后再跑一次本工具即可。
- `catalog/` 是外部整理的名录，本身可能有错（例如把 Emerald 译成绿叶）。
  工具忠实采用名录，发现错译应直接修 `catalog/` 源文件。
