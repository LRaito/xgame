# 封面美化与游戏机壳任务清单

盘查日期：2026-11-04。状态随代码变化，动手前先按下面的「完成标准」核对。

- 机种清单取自 [`platforms.md`](platforms.md) 的权威表 `backend/games/platforms.py`。
- 只列已收录、可上传可玩的机种（`extensions` 非空，共 34 个）。
- `sega` / `mame` 是外部名录的兜底 key，不开放上传，不在表内。
- 顺序与词表一致：按厂商分组。
- `cart` = 封面美化，`shell` = 游戏机壳；`√` 已完成，`X` 未完成。

## 完成标准

- `cart`：`frontend/src/assets/carts/<样式>-cart.png` 存在；
  在 `frontend/src/constants/coverStyles.js` 注册洞口几何；
  在 `STYLE_BY_GAME_TYPE` 与后端 `models.py` 的 `COVER_TYPES_BY_GAME_TYPE` 里成对登记。
- `shell`：`frontend/src/assets/shells/` 下有素材；
  在 `frontend/src/views/games/emulator-player.vue` 的 `SHELLS` 表注册洞与部件几何。
- 一个机种可以对应多种样式：`gb` 行含 GB / GBC 两种卡带，`nes` 行含 FC / NES 两种卡带。
- `flash` 是载体类型不是机种，已有 DISK 光盘美化，不占机种行。

## 任务清单

| 机种 | cart | shell |
|---|---|---|
| 任天堂 FC（`nes`） | √ | √ |
| 任天堂 SFC（`snes`） | X | X |
| 任天堂 N64（`n64`） | X | X |
| 任天堂 GB/GBC（`gb`） | √ | √ |
| 任天堂 GBA（`gba`） | √ | √ |
| 任天堂 NDS（`nds`） | √ | √ |
| 任天堂 Virtual Boy（`vb`） | X | X |
| 世嘉 MD（`segaMD`） | X | X |
| 世嘉 GG（`segaGG`） | X | X |
| 世嘉 SMS（`segaMS`） | X | X |
| 世嘉 CD（`segaCD`） | X | X |
| 世嘉 32X（`sega32x`） | X | X |
| 世嘉 土星（`segaSaturn`） | X | X |
| 索尼 PS1（`psx`） | X | X |
| 索尼 PSP（`psp`） | X | X |
| 日电 PCE（`pce`） | X | X |
| 日电 PC-FX（`pcfx`） | X | X |
| SNK NGPC（`ngp`） | X | X |
| 万代 WS（`ws`） | X | X |
| 雅达利 2600（`atari2600`） | X | X |
| 雅达利 5200（`atari5200`） | X | X |
| 雅达利 7800（`atari7800`） | X | X |
| 雅达利 Jaguar（`jaguar`） | X | X |
| 雅达利 Lynx（`lynx`） | X | X |
| ColecoVision（`coleco`） | X | X |
| 松下 3DO（`3do`） | X | X |
| Commodore 64（`c64`） | X | X |
| Commodore 128（`c128`） | X | X |
| Commodore PET（`pet`） | X | X |
| Commodore Plus/4（`plus4`） | X | X |
| Commodore VIC-20（`vic20`） | X | X |
| Amiga（`amiga`） | X | X |
| DOS（`dos`） | X | X |
| 街机（`arcade`） | X | X |

## 现状汇总

- 34 个机种中，`cart` 完成 4 个，共 6 种卡带样式（FC / NES / GB / GBC / GBA / NDS）。
- `shell` 完成 4 个，共 6 张素材（FC 像素完美 + 4:3、GB/GBC、GBA、NDS 上下 + 左右）。
- 其余机种两列均为 `X`。

## 相关文档

- 素材位置、洞口几何与合成规则 → [`game-assets.md`](game-assets.md)
- 机壳渲染与 NDS 多布局 → [`game-center-playback.md`](game-center-playback.md)
- 机种词表与接入步骤 → [`platforms.md`](platforms.md)
