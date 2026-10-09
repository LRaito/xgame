<template>
    <router-link
        :to="game.path"
        class="game-card"
        @contextmenu.prevent="emit('contextmenu', $event)"
    >
        <!-- 封面渲染按类型走（Flash 光盘 / GB-GBC 卡带 / 普通封面），与详情图片栏、
             游戏管理缩略图共用 components/games/GameCover.vue；这里只给框比值与 hover -->
        <game-cover class="game-card__cover" :game="game" :aspect="aspect" />
        <div class="game-card__info">
            <h3 class="game-card__name">{{ game.name }}</h3>
            <!-- 进度「未开始」就整行不渲染（既没有进度标签，也不显示时长） -->
            <div v-if="showMeta" class="game-card__meta">
                <!-- 进度标签（进行中 / 已通关）与时长依次排开 -->
                <span
                    v-if="game.progress === PROGRESS_COMPLETED"
                    class="game-card__tag game-card__tag--completed"
                >
                    <span class="game-card__check">✓</span>已通关
                </span>
                <span
                    v-else-if="game.progress === PROGRESS_IN_PROGRESS"
                    class="game-card__tag game-card__tag--playing"
                >
                    <span class="game-card__dot" />进行中
                </span>
                <span v-if="playSeconds" class="game-card__playtime">
                    <span class="game-card__playtime-icon">🕒</span>
                    {{ formatPlayHours(playSeconds) }}
                </span>
            </div>
        </div>
    </router-link>
</template>

<script setup>
import { computed } from "vue";
import {
    PROGRESS_COMPLETED,
    PROGRESS_IN_PROGRESS,
    PROGRESS_NOT_STARTED,
} from "@/constants/gameProgress";
import { formatPlayHours } from "@/utils/gamePlaytime";
import GameCover from "@components/games/GameCover.vue";

// 卡片宽度由外层网格列宽决定；高度看下面的 aspect（封面框规则见 GameCover.vue）
const props = defineProps({
    game: { type: Object, required: true },
    // 卡片封面框「宽 / 高」比值：rail 传 CARD_ASPECT_RAIL（正方形框、整行高低一致）；
    // 「全部游戏」不传 = 高度自适应，卡片高随封面高（同类型封面形状一致，整行仍齐平）。
    aspect: { type: String, default: "" },
});

// 右键交回给页面（游戏中心用它弹「设置进度 / 设置时长」菜单）
const emit = defineEmits(["contextmenu"]);

const playSeconds = computed(() => Number(props.game.play_seconds) || 0);

// 进度不是「未开始」才渲染状态行：未开始既不显示进度标签，也不显示时长。
// 也就是说「有时长但没标过进度」的卡片这里什么都不显示——时长只在标了进度之后才有意义。
const showMeta = computed(
    () => (props.game.progress || PROGRESS_NOT_STARTED) !== PROGRESS_NOT_STARTED
);

</script>

<style scoped>
/* 卡片本身无边框、无底色，hover 时只把封面抬起 */
.game-card {
    display: flex;
    flex-direction: column;
    min-width: 0;
    text-decoration: none;
    color: inherit;
}

/* 封面框：比例由 GameCover 按 aspect 内联设置，这里只管 hover 抬起。
   内容怎么画（Flash 光盘 / GB-GBC 卡带 / 普通封面）都在 GameCover.vue 里，三处展示共用。 */
.game-card__cover {
    transition: transform 0.18s ease;
}

.game-card:hover .game-card__cover {
    transform: translateY(-4px);
}

/* 名称与状态行整体居中：封面下面留白，不再有边框与底色 */
.game-card__info {
    margin-top: 10px;
    text-align: center;
}

/* 标题：圆体（PingFang / 雅黑），最多两行，超出截断 */
.game-card__name {
    margin: 0 0 5px;
    font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.5px;
    line-height: 1.35;
    color: #1f2937;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    word-break: break-all;
}

/* 状态 + 时长：居中一排，两行文字同高 */
.game-card__meta {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    font-size: 11px;
    line-height: 14px;
    white-space: nowrap;
}

.game-card__playtime {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    color: #6b7280;
    font-weight: 500;
}

.game-card__playtime-icon {
    font-size: 10px;
}

.game-card__tag {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-weight: 600;
}

.game-card__tag--playing {
    gap: 4px;
    color: #2563eb;
}

.game-card__tag--completed {
    color: #16a34a;
}

.game-card__check {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #16a34a;
    color: #fff;
    font-size: 8px;
    font-weight: 900;
    flex: none;
}

.game-card__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
    flex: none;
}
</style>
