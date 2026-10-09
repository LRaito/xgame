<template>
    <!-- 封面渲染：按游戏类型换外观——**只有游戏中心的卡片用**（「全部游戏」网格与
         「最近游玩」rail），详情弹框图片栏、游戏管理缩略图与表单预览都显示封面原图，
         不套这一层：
           Flash    → 实体光盘，盘面就是封面
           GB/GBC   → 整张卡带图（public/gbc-cart.png，见 constants/gameCartridges.js），
                      封面贴进它的贴纸窗
           其余类型 → 普通封面图（等比缩放到不超出限制框，没封面时摆类型图标）

         尺寸规则：卡片宽就是「正方形限制框」的边长（内部用 cqw 表达，见样式），
         封面内容一律等比缩放到长或宽触到限制框的边、水平垂直居中：
           - rail 的 aspect 传 "1 / 1"：卡片本身就是正方形，封面在框里居中（整行高低一致）；
           - 网格不传 aspect：卡片高 = 封面高（同一类型的封面形状一致，整行仍齐平）。 -->
    <div class="game-cover" :style="boxStyle">
        <div class="game-cover__screen">
            <!-- GB/GBC：整张卡带 + 封面贴进贴纸窗 -->
            <div
                v-if="cartridge"
                class="game-cover__cart"
                :style="{ aspectRatio: cartridge.image.width / cartridge.image.height }"
            >
                <img class="game-cover__cart-body" :src="cartridgeImage" alt="" />
                <img
                    v-if="coverUrl"
                    class="game-cover__cart-label"
                    :style="cartridgeLabelStyle"
                    :src="coverUrl"
                    :alt="gameName"
                />
                <!-- 没有封面时贴纸窗留空，摆一个类型图标，别让卡带看着缺一块 -->
                <span
                    v-else
                    class="game-cover__cart-label game-cover__cart-label--empty"
                    :style="cartridgeLabelStyle"
                >
                    {{ icon }}
                </span>
            </div>

            <!-- Flash：实体光盘，盘面就是封面 -->
            <div v-else-if="isFlash" class="game-cover__disc">
                <img v-if="coverUrl" class="game-cover__disc-img" :src="coverUrl" :alt="gameName" />
                <!-- 盘心那枚 Flash 标志：正好填住盘中心的孔 -->
                <img class="game-cover__disc-hub" :src="FLASH_LOGO_URL" alt="" />
                <!-- 盘面反光/边缘细节只叠在光盘上（放在标志之上，反光才盖得住它） -->
                <span class="game-cover__disc-sheen" />
            </div>

            <!-- 其余类型：普通封面 -->
            <img
                v-else-if="coverUrl"
                class="game-cover__img"
                :src="coverUrl"
                :alt="gameName"
            />
            <span v-else class="game-cover__fallback">{{ icon }}</span>
        </div>
    </div>
</template>

<script setup>
import { computed } from "vue";
import { cartridgeFor } from "@/constants/gameCartridges";
import { gameTypeMeta } from "@/constants/gameTypes";
import { gameCoverUrl } from "@/utils/gameAssetCache";

const props = defineProps({
    // 游戏条目（列表载荷即可：需要 category / name / cover_path）
    game: { type: Object, default: null },
    // 卡片封面框「宽 / 高」比值，直接给 CSS aspect-ratio：rail 传 "1 / 1"（正方形框）；
    // 留空表示高度自适应 = 卡片高随封面高（「全部游戏」网格用）
    aspect: { type: String, default: "" },
});

// 盘心那枚 Flash 标志（public 下的普通静态文件，走 nginx 的 location /）
const FLASH_LOGO_URL = "/flash-logo.png";

const gameName = computed(() => props.game?.name || "");
const coverUrl = computed(() => (props.game?.cover_path ? gameCoverUrl(props.game) : ""));
const meta = computed(() => gameTypeMeta(props.game?.category));
const icon = computed(() => meta.value?.icon || "🎮");

// 类型决定外观：Flash 是光盘，GB/GBC 是卡带，其余是普通封面
const isFlash = computed(() => meta.value?.kind === "flash");
const cartridge = computed(() => cartridgeFor(props.game?.category));
// 卡带底图：每个类型固定一张（见 constants/gameCartridges.js）
const cartridgeImage = computed(() => cartridge.value?.url || "");

// 有没有可画的内容（光盘 / 卡带 / 封面图）：没有就只剩类型图标，得给个方形框，
// 否则卡片会塌成一行图标的高度
const hasContent = computed(() => isFlash.value || Boolean(cartridge.value) || Boolean(coverUrl.value));

// 卡片封面框的内联样式：给了比值就用它（rail 的正方形框）；
// 没给且没有内容时兜底成正方形；其余情况不设比例，高度由内容撑出来
const boxStyle = computed(() => {
    const ratio = props.aspect || (hasContent.value ? "" : "1 / 1");
    return ratio ? { aspectRatio: ratio } : null;
});

// 贴纸窗按整图百分比定位：卡带图缩到多大，窗都跟着走
const cartridgeLabelStyle = computed(() => {
    const cart = cartridge.value;
    if (!cart) {
        return null;
    }
    const { image, label } = cart;
    return {
        left: `${(label.x / image.width) * 100}%`,
        top: `${(label.y / image.height) * 100}%`,
        width: `${(label.width / image.width) * 100}%`,
        height: `${(label.height / image.height) * 100}%`,
    };
});
</script>

<style scoped>
/* 框：只定尺寸与裁剪，不铺底色（封面没占满的地方透出页面背景）。
   container-type 让内部能用 cqw——100cqw 就是「正方形限制框」的边长（= 卡片宽），
   封面据此定尺寸，于是 rail 与网格里同一盘卡一样大 */
.game-cover {
    position: relative;
    overflow: hidden;
    min-width: 0;
    container-type: inline-size;
}

/* 内容区：吃掉框里全部空间，内容居中 */
.game-cover__screen {
    position: relative;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
}

/* 普通封面：宽先铺满，高度超出正方形限制框时由 max-height 等比压回
   （替换元素触发 max-height 会保持宽高比，不裁不拉），父级 flex 居中 */
.game-cover__img {
    width: 100%;
    height: auto;
    max-height: 100cqw;
    display: block;
}

.game-cover__fallback {
    font-size: 36px;
    line-height: 1;
    color: #94a3b8;
}

/* ---------- GB/GBC：整张卡带图，封面贴进贴纸窗 ---------- */

/* 卡带本体：高度触到正方形限制框的边（卡带图是竖长形，长触边），
   宽度按图自身比例推出、水平居中 */
.game-cover__cart {
    position: relative;
    height: 100cqw;
    max-width: 100%;
}

.game-cover__cart-body {
    display: block;
    width: 100%;
    height: 100%;
}

/* 贴纸窗里的封面：位置与尺寸由行内样式按整图百分比给（见 cartridgeLabelStyle）。
   object-fit: fill = 一律拉伸填满这扇窗（不裁切、不留黑边）；
   border-radius 跟贴纸窗的圆角走（约占窗宽 2%），方角不会啃到卡带的边框线 */
.game-cover__cart-label {
    position: absolute;
    display: block;
    object-fit: fill;
    border-radius: 2%;
}

.game-cover__cart-label--empty {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 32px;
    line-height: 1;
    color: #94a3b8;
}

/* ---------- Flash：实体光盘，盘面就是封面 ---------- */

/* 光盘直径：占「正方形限制框边长」的比例（84cqw）——两种排版里盘都一样大，
   四周留一圈空是刻意的观感（不放大到触满），盘在框里两个方向都居中 */
.game-cover {
    --disc-size: 84cqw;

    /* 盘心（填 Flash 标志的那一圈）直径，占盘直径的比例。
       盘面细节那几圈渐变用的是 closest-side（占盘半径）的百分比，半径正好是直径的一半，
       所以这一个数两处通用：盘心图片的 width 直接用它，渐变里也用它当半径。 */
    --hub: 15%;
}

/* 盘面：正方形、圆形裁切。没有封面时露出的就是这层「空白盘」的金属感渐变。
   不加落影（试过接触影 + 散影，效果不好）：盘的边缘感由 sheen 里那几圈
   弧度暗调与透明塑料边反光给，够用。 */
.game-cover__disc {
    position: relative;
    flex: none;
    width: var(--disc-size);
    aspect-ratio: 1 / 1;
    border-radius: 50%;
    overflow: hidden;
    background: linear-gradient(135deg, #f8fafc 0%, #cbd5e1 42%, #eef2f7 58%, #b6c0cc 100%);
}

/* 盘面贴封面：铺满整个圆（cover 会裁掉溢出部分，盘面不留白边） */
.game-cover__disc-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 50%;
    display: block;
}

/* 盘心：Flash 标志正好盖住盘中心那一圈（原图四周有 5% 透明边，所以红圆略小于这一格）。
   它必须在封面图之后、盘面反光之前：先盖住封面，再让反光从上面扫过去。 */
.game-cover__disc-hub {
    position: absolute;
    left: 50%;
    top: 50%;
    width: var(--hub);
    aspect-ratio: 1 / 1;
    transform: translate(-50%, -50%);
    border-radius: 50%;
}

/* 盘面细节与反光（只在 Flash 的光盘上）。径向渐变用 closest-side，
   百分比就是「占盘半径的比例」，边缘那几圈才好写：
   孔外一圈积层环 → 数据区 → 反射层边界的暗线 → 透明塑料边的反光。 */
.game-cover__disc-sheen {
    position: absolute;
    inset: 0;
    pointer-events: none;
    border-radius: 50%;
    background:
        radial-gradient(
            circle closest-side,
            rgba(255, 255, 255, 0) 0 calc(var(--hub) + 1%),
            rgba(255, 255, 255, 0.55) calc(var(--hub) + 2.5%),
            rgba(255, 255, 255, 0) calc(var(--hub) + 6%)
        ),
        radial-gradient(
            circle closest-side,
            /* 盘面外圈渐渐压暗：一点弧度感，盘就不是一张平贴的圆纸片 */
            rgba(255, 255, 255, 0) 0 74%,
            rgba(15, 23, 42, 0.18) 91% 92.5%,
            /* 透明塑料边：内侧浅、贴边一道强反光 */
            rgba(255, 255, 255, 0.2) 94% 95.5%,
            rgba(255, 255, 255, 0.62) 97.5% 99%,
            rgba(255, 255, 255, 0.35) 100%
        ),
        linear-gradient(
            118deg,
            rgba(255, 255, 255, 0.42) 0%,
            rgba(255, 255, 255, 0.06) 24%,
            rgba(255, 255, 255, 0) 30%,
            rgba(255, 255, 255, 0) 64%,
            rgba(255, 255, 255, 0.18) 80%,
            rgba(255, 255, 255, 0) 100%
        );
}
</style>
