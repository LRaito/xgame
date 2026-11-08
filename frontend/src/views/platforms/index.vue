<template>
    <div class="chronicle-page">
        <header class="chronicle-hero">
            <div class="chronicle-hero__main">
                <p class="chronicle-hero__eyebrow">游戏平台档案 · {{ yearRange }}</p>
                <p class="page-lead">
                    从街机厅到掌机，再到浏览器——按年代梳理
                    {{ entries.length }} 个游戏平台的来路。
                </p>
            </div>
            <dl class="chronicle-stats">
                <div class="chronicle-stat">
                    <dt>收录机型</dt>
                    <dd>{{ entries.length }}</dd>
                </div>
                <div class="chronicle-stat">
                    <dt>时代分段</dt>
                    <dd>{{ eras.length }}</dd>
                </div>
                <div class="chronicle-stat">
                    <dt>厂商</dt>
                    <dd>{{ makerCount }}</dd>
                </div>
                <div class="chronicle-stat">
                    <dt>历史跨度</dt>
                    <dd>{{ yearRange }}</dd>
                </div>
            </dl>
        </header>

        <div class="chronicle-timeline">
            <section v-for="(era, index) in eras" :key="era.id" class="era">
                <div class="era__rail">
                    <span class="era__dot" aria-hidden="true"></span>
                    <div class="era__rail-inner">
                        <span class="era__index" aria-hidden="true">
                            {{ String(index + 1).padStart(2, "0") }}
                        </span>
                        <span class="era__range">{{ era.range }}</span>
                        <h2 class="era__title">{{ era.title }}</h2>
                        <span class="era__count">{{ era.count }} 款机型</span>
                    </div>
                </div>

                <div class="era__body">
                    <p class="era__desc">{{ era.description }}</p>
                    <div class="era__grid">
                        <router-link
                            v-for="entry in era.entries"
                            :key="entry.id"
                            class="platform-card"
                            :to="`/platforms/${entry.id}`"
                        >
                            <div class="platform-card__media">
                                <img
                                    v-if="imageOf(entry)"
                                    class="platform-card__img"
                                    :src="imageOf(entry)"
                                    :alt="`${labelOf(entry.id)} ${entry.year} 年机型图`"
                                    loading="lazy"
                                    decoding="async"
                                />
                                <span v-else class="platform-card__icon" aria-hidden="true">
                                    {{ iconOf(entry.id) }}
                                </span>
                            </div>
                            <div class="platform-card__body">
                                <div class="platform-card__meta">
                                    <time :datetime="String(entry.year)">{{ entry.year }}</time>
                                    <span class="platform-card__maker" :title="entry.maker">
                                        {{ entry.maker }}
                                    </span>
                                </div>
                                <h3 class="platform-card__name" :title="labelOf(entry.id)">
                                    {{ labelOf(entry.id) }}
                                </h3>
                                <span class="platform-card__cta" aria-hidden="true">
                                    查看机型
                                    <span class="platform-card__arrow">→</span>
                                </span>
                            </div>
                        </router-link>
                    </div>
                </div>
            </section>
        </div>
    </div>
</template>

<script setup>
import { computed } from "vue";
import { PLATFORM_INTROS } from "@/constants/platformIntros";
import { PLATFORM_IMAGES } from "@/constants/platformIntros/images";
import { useGameTypesStore } from "@/store/gameTypes";

// 时代分段只维护结束年份，条目按 year 自动归档；最后一段兜住所有更晚的机型。
const ERAS = [
    {
        until: 1982,
        title: "街机与家用机的黎明",
        description: "投币街机走向大众，可换卡带的家用机与早期家用电脑相继登场。",
    },
    {
        until: 1986,
        title: "8 位时代",
        description: "画面与音效第一次形成标准，家用机市场完成新一轮洗牌。",
    },
    {
        until: 1992,
        title: "16 位时代",
        description: "色彩与音源明显提升，掌机与光盘载体开始进入主流视野。",
    },
    {
        until: 1999,
        title: "3D 与光盘时代",
        description: "多边形与光盘改写软硬件规则，掌上游戏并行成长。",
    },
    {
        until: Infinity,
        title: "掌机与网页平台",
        description: "双屏与宽屏掌机成熟，浏览器成为不依赖插件的游戏平台。",
    },
];

const gameTypes = useGameTypesStore();

// 静态数据里 plus4（1984）排在数组末尾，必须显式按年份排序。
const entries = computed(() => [...PLATFORM_INTROS].sort((a, b) => a.year - b.year));

const makerCount = computed(() => new Set(entries.value.map((entry) => entry.maker)).size);

const yearRange = computed(() => rangeOf(entries.value));

const eras = computed(() => {
    const buckets = ERAS.map((era, index) => ({
        id: `era-${index + 1}`,
        title: era.title,
        description: era.description,
        until: era.until,
        entries: [],
    }));

    for (const entry of entries.value) {
        const bucket =
            buckets.find((era) => entry.year <= era.until) || buckets[buckets.length - 1];
        bucket.entries.push(entry);
    }

    return buckets
        .filter((era) => era.entries.length)
        .map((era) => ({
            ...era,
            range: rangeOf(era.entries),
            count: era.entries.length,
        }));
});

function rangeOf(items) {
    if (!items.length) {
        return "";
    }
    const first = items[0].year;
    const last = items[items.length - 1].year;
    return first === last ? String(first) : `${first}–${last}`;
}

function labelOf(id) {
    return gameTypes.labelOf(id);
}

function iconOf(id) {
    return gameTypes.metaOf(id)?.icon || "🎮";
}

function imageOf(entry) {
    return PLATFORM_IMAGES[`${entry.id}-console-1`] || "";
}
</script>

<style scoped>
.chronicle-page {
    max-width: 1280px;
    --chronicle-border-strong: #cbd5e1;
}

.chronicle-hero {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 40px;
    margin-bottom: 8px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border);
}

.chronicle-hero__eyebrow {
    margin: 0 0 8px;
    font-size: 12px;
    letter-spacing: 0.12em;
    color: var(--text-muted);
}

.chronicle-stats {
    display: flex;
    margin: 0;
}

.chronicle-stat {
    min-width: 92px;
    padding: 0 18px;
    border-left: 1px solid var(--border);
}

.chronicle-stat:first-child {
    padding-left: 0;
    border-left: 0;
}

.chronicle-stat:last-child {
    padding-right: 0;
}

.chronicle-stat dt {
    font-size: 12px;
    color: var(--text-muted);
}

.chronicle-stat dd {
    margin: 4px 0 0;
    font-size: 20px;
    font-weight: 600;
    color: var(--brand-dark);
    font-variant-numeric: tabular-nums;
}

.chronicle-timeline {
    position: relative;
    padding-top: 32px;
}

/* 时间轴主线：从第一个节点一直拉到最后一节底部 */
.chronicle-timeline::before {
    content: "";
    position: absolute;
    top: 45px;
    bottom: 20px;
    left: 6px;
    width: 2px;
    background: var(--border);
}

.era {
    display: grid;
    grid-template-columns: 210px minmax(0, 1fr);
    gap: 40px;
    padding-bottom: 56px;
}

.era:last-child {
    padding-bottom: 0;
}

.era__rail {
    position: relative;
    padding-left: 28px;
}

.era__dot {
    position: absolute;
    top: 6px;
    left: 0;
    width: 14px;
    height: 14px;
    border: 2px solid var(--brand-accent);
    border-radius: 50%;
    background: var(--surface);
    box-shadow: 0 0 0 4px var(--brand-accent-soft);
}

.era__rail-inner {
    position: sticky;
    top: 24px;
    display: flex;
    flex-direction: column;
    gap: 5px;
}

.era__index {
    font-size: 12px;
    letter-spacing: 0.08em;
    color: var(--brand-accent);
    font-variant-numeric: tabular-nums;
}

.era__range {
    font-size: 13px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}

.era__title {
    font-size: 19px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--brand-dark);
    text-wrap: balance;
}

.era__count {
    font-size: 12px;
    color: var(--text-muted);
}

.era__desc {
    margin: 0 0 18px;
    font-size: 14px;
    line-height: 1.7;
    color: var(--text-muted);
}

.era__grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
}

.platform-card {
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    color: inherit;
    text-decoration: none;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.platform-card__media {
    position: relative;
    aspect-ratio: 4 / 3;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
}

.platform-card__img {
    position: absolute;
    inset: 12px;
    width: calc(100% - 24px);
    height: calc(100% - 24px);
    object-fit: contain;
}

.platform-card__icon {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 34px;
    line-height: 1;
}

.platform-card__body {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 6px;
    padding: 10px 12px 12px;
}

.platform-card__meta {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    min-width: 0;
    font-size: 12px;
    color: var(--text-muted);
}

.platform-card__meta time {
    flex: none;
    font-variant-numeric: tabular-nums;
}

.platform-card__maker {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.platform-card__name {
    display: -webkit-box;
    margin: 0;
    overflow: hidden;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--brand-dark);
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
}

.platform-card__cta {
    margin-top: auto;
    font-size: 12px;
    color: var(--text-muted);
    transition: color 0.18s ease;
}

.platform-card__arrow {
    display: inline-block;
    transition: transform 0.18s ease;
}

.platform-card:hover {
    border-color: var(--chronicle-border-strong);
    box-shadow: var(--shadow-md);
    transform: translateY(-3px);
}

.platform-card:hover .platform-card__cta {
    color: var(--brand-accent);
}

.platform-card:hover .platform-card__arrow {
    transform: translateX(3px);
}

.platform-card:focus-visible {
    outline: 2px solid var(--app-color-primary);
    outline-offset: 2px;
}

@media (max-width: 1200px) {
    .era__grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
}

@media (max-width: 900px) {
    .chronicle-hero {
        flex-direction: column;
        align-items: flex-start;
        gap: 24px;
    }

    .chronicle-stats {
        width: 100%;
        flex-wrap: wrap;
    }

    .chronicle-stat {
        padding: 0 16px;
    }

    .chronicle-timeline::before,
    .era__dot {
        display: none;
    }

    .era {
        grid-template-columns: minmax(0, 1fr);
        gap: 14px;
        padding-bottom: 44px;
    }

    .era__rail {
        padding-left: 0;
    }

    .era__grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .era__rail-inner {
        position: static;
        flex-direction: row;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 6px 14px;
    }

    .era__title {
        font-size: 18px;
    }
}

@media (max-width: 680px) {
    .chronicle-stats {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px 0;
    }

    .chronicle-stat {
        padding: 0;
    }

    .era__grid {
        grid-template-columns: 1fr;
    }
}

@media (prefers-reduced-motion: reduce) {
    .platform-card,
    .platform-card__cta,
    .platform-card__arrow {
        transition: none;
    }

    .platform-card:hover {
        transform: none;
    }

    .platform-card:hover .platform-card__arrow {
        transform: none;
    }
}
</style>
