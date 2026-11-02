<template>
    <!-- 卡片封面：**所有游戏类型一视同仁**，就是封面原图（等比缩放到不超出限制框，
         没封面时摆类型图标）。「Flash 画成实体光盘」「GB/GBC 贴进卡带」那两套按类型
         分支渲染的观感已经取消——想要那些观感的，去游戏管理页的编辑弹框点「美化封面」
         把外观合成进封面文件本身（见 components/games/CoverBeautifyDialog.vue）。

         只有游戏中心的卡片用这个组件（「全部游戏」网格与「最近游玩」rail）；
         详情弹框图片栏、游戏管理缩略图与表单预览都直接显示封面原图，不套这一层。

         尺寸规则：卡片宽就是「正方形限制框」的边长（内部用 cqw 表达，见样式），
         封面等比缩放到长或宽触到限制框的边、水平垂直居中：
           - rail 的 aspect 传 "1 / 1"：卡片本身就是正方形，封面在框里居中（整行高低一致）；
           - 网格不传 aspect：卡片高 = 封面高（同一类型的封面形状一致，整行仍齐平）。 -->
    <div class="game-cover" :style="boxStyle">
        <div class="game-cover__screen">
            <img v-if="coverUrl" class="game-cover__img" :src="coverUrl" :alt="gameName" />
            <span v-else class="game-cover__fallback">{{ icon }}</span>
        </div>
    </div>
</template>

<script setup>
import { computed } from "vue";
import { gameTypeMeta } from "@/constants/gameTypes";
import { gameCoverUrl } from "@/utils/gameAssetCache";

const props = defineProps({
    // 游戏条目（列表载荷即可：需要 category / name / cover_path）
    game: { type: Object, default: null },
    // 卡片封面框「宽 / 高」比值，直接给 CSS aspect-ratio：rail 传 "1 / 1"（正方形框）；
    // 留空表示高度自适应 = 卡片高随封面高（「全部游戏」网格用）
    aspect: { type: String, default: "" },
});

const gameName = computed(() => props.game?.name || "");
const coverUrl = computed(() => (props.game?.cover_path ? gameCoverUrl(props.game) : ""));
const meta = computed(() => gameTypeMeta(props.game?.category));
const icon = computed(() => meta.value?.icon || "🎮");

// 卡片封面框的内联样式：给了比值就用它（rail 的正方形框）；
// 没给且没有封面时只剩一个图标，兜个正方形框，否则卡片会塌成一行图标的高度
const boxStyle = computed(() => {
    const ratio = props.aspect || (coverUrl.value ? "" : "1 / 1");
    return ratio ? { aspectRatio: ratio } : null;
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

/* 封面：宽先铺满，高度超出正方形限制框时由 max-height 压回，父级 flex 居中。

   `object-fit: contain` 是这里的关键，不能省。max-height 生效时元素盒子被压成
   正方形，而 img 默认 `object-fit: fill` 会把画面**横向拉宽**填满盒子——竖版封面
   （GBC 那张 438×503、NES 那张 700×779）就是这么被拉变形的，横版封面（GBA 640×370、
   FC 那张 700×460）高度本来就没超框，走不到这一步，所以只有竖版看得出问题。

   **别指望 max-height 自己保持比例**：那套算法（CSS2.1 §10.4）只在 width 与 height
   **都是 auto** 时才适用；这里 width 是明确值 100%，浏览器只压 height、宽度不动。
   改成 `width: auto` 则小图不会被放大到铺满卡片，也不对。

   加了 contain 后：盒子仍是正方形，画面等比缩放到长或宽触到限制框的边，多出来的
   方向留白居中——竖版贴满高、左右留白，横版贴满宽、上下留白，正是「正方形限制框」的语义。 */
.game-cover__img {
    width: 100%;
    height: auto;
    max-height: 100cqw;
    object-fit: contain;
    display: block;
}

.game-cover__fallback {
    font-size: 36px;
    line-height: 1;
    color: #94a3b8;
}
</style>
