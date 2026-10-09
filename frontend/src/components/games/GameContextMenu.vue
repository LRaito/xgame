<template>
    <teleport to="body">
        <ul
            v-if="visible"
            class="game-context-menu"
            :style="{ left: x + 'px', top: y + 'px' }"
            @click.stop
            @contextmenu.prevent.stop
        >
            <li @click="emit('detail')">详情</li>
            <!-- 没有攻略的游戏不出现这一项：点开只会是 404，不如不给入口 -->
            <li v-if="hasGuide" @click="emit('guide')">攻略</li>
            <li class="split" />
            <li class="game-context-menu__sub">
                <span>设置进度</span>
                <ul class="game-context-menu game-context-menu--sub">
                    <li
                        v-for="item in GAME_PROGRESS_LIST"
                        :key="item.value"
                        :class="{ 'is-current': item.value === progress }"
                        @click="emit('set-progress', item.value)"
                    >
                        {{ item.label }}
                    </li>
                </ul>
            </li>
            <li class="split" />
            <li @click="emit('set-hours')">设置时长</li>
        </ul>
    </teleport>
</template>

<script setup>
import { GAME_PROGRESS_LIST } from "@/constants/gameProgress";

defineProps({
    visible: { type: Boolean, default: false },
    x: { type: Number, default: 0 },
    y: { type: Number, default: 0 },
    // 当前进度：子菜单里把已选的那项加深
    progress: { type: String, default: "" },
    // 该游戏是否已有攻略（决定「攻略」那一项出不出现）
    hasGuide: { type: Boolean, default: false },
});

const emit = defineEmits(["detail", "guide", "set-progress", "set-hours"]);
</script>

<style scoped>
.game-context-menu {
    position: fixed;
    z-index: 4000;
    min-width: 140px;
    margin: 0;
    padding: 6px;
    list-style: none;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: var(--shadow-md);
}

.game-context-menu li {
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    color: #1e293b;
    cursor: pointer;
    white-space: nowrap;
}

.game-context-menu li:hover {
    background: #f1f5f9;
}

/* 子菜单里当前生效的那一项：底色加深 + 主色加粗，和 hover 的浅灰区分开 */
.game-context-menu li.is-current {
    background: #eff6ff;
    color: #2563eb;
    font-weight: 600;
}

.game-context-menu li.is-current:hover {
    background: #dbeafe;
}

.game-context-menu li.split {
    height: 1px;
    padding: 0;
    margin: 4px 8px;
    background: var(--border);
    cursor: default;
    pointer-events: none;
}

/* 「设置进度」与「设置卡带类型」向右滑出各自的选项。子菜单挂在 li 里，
   鼠标从触发项移过去时父 li 仍是 :hover，中间用 -2px 重叠避免掠过缝隙时收起。 */
.game-context-menu__sub {
    position: relative;
}

.game-context-menu--sub {
    display: none;
    position: absolute;
    left: calc(100% - 2px);
    top: -6px;
}

.game-context-menu__sub:hover > .game-context-menu--sub {
    display: block;
}

</style>
