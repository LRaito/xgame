<template>
    <div v-if="entry" class="intro-page">
        <nav class="intro-breadcrumb" aria-label="面包屑">
            <router-link to="/platforms">机型简史</router-link>
            <span class="intro-breadcrumb__sep" aria-hidden="true">/</span>
            <span aria-current="page">{{ labelOf(entry.id) }}</span>
        </nav>

        <header class="intro-hero" :class="{ 'intro-hero--text-only': !heroImage }">
            <div class="intro-hero__main">
                <p class="intro-hero__eyebrow">机型档案</p>
                <h1 class="intro-hero__title">{{ labelOf(entry.id) }}</h1>
                <p class="intro-hero__summary">{{ entry.summary }}</p>

                <dl class="intro-hero__meta">
                    <div class="intro-hero__meta-item">
                        <dt>发售年份</dt>
                        <dd>{{ entry.year }}</dd>
                    </div>
                    <div class="intro-hero__meta-item">
                        <dt>厂商</dt>
                        <dd>{{ entry.maker }}</dd>
                    </div>
                    <div class="intro-hero__meta-item">
                        <dt>世代</dt>
                        <dd>{{ entry.generation }}</dd>
                    </div>
                </dl>
            </div>

            <figure v-if="heroImage" class="intro-hero__media">
                <img
                    class="intro-hero__img"
                    :src="heroImage"
                    :alt="`${labelOf(entry.id)} 机型图`"
                    decoding="async"
                    fetchpriority="high"
                />
            </figure>
        </header>

        <section class="intro-section">
            <h2 class="intro-section__title">参数速览</h2>
            <dl class="spec-grid">
                <div v-for="fact in entry.facts" :key="fact.label" class="spec-card">
                    <dt>{{ fact.label }}</dt>
                    <dd>{{ fact.value }}</dd>
                </div>
            </dl>
        </section>

        <section class="intro-section">
            <h2 class="intro-section__title">历史</h2>
            <div class="intro-prose">
                <p v-for="(paragraph, index) in entry.history" :key="index">
                    {{ paragraph }}
                </p>
            </div>
        </section>

        <section v-if="consoleImages.length" class="intro-section">
            <h2 class="intro-section__title">{{ consoleTitle }}</h2>
            <intro-gallery :images="consoleImages" :label="labelOf(entry.id)" />
        </section>

        <section v-if="mediaImages.length" class="intro-section">
            <h2 class="intro-section__title">{{ mediaTitle }}</h2>
            <intro-gallery :images="mediaImages" :label="`${labelOf(entry.id)} ${entry.mediaLabel}`" />
        </section>

        <nav v-if="prevEntry || nextEntry" class="intro-pager" aria-label="按年份浏览相邻机型">
            <router-link
                v-if="prevEntry"
                class="intro-pager__link"
                :to="`/platforms/${prevEntry.id}`"
            >
                <span class="intro-pager__label">← 上一款 · {{ prevEntry.year }}</span>
                <span class="intro-pager__name">{{ labelOf(prevEntry.id) }}</span>
            </router-link>

            <router-link
                v-if="nextEntry"
                class="intro-pager__link intro-pager__link--next"
                :to="`/platforms/${nextEntry.id}`"
            >
                <span class="intro-pager__label">{{ nextEntry.year }} · 下一款 →</span>
                <span class="intro-pager__name">{{ labelOf(nextEntry.id) }}</span>
            </router-link>
        </nav>
    </div>

    <app-empty v-else description="没有这个机型的介绍" />
</template>

<script setup>
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import { PLATFORM_INTROS } from "@/constants/platformIntros";
import { PLATFORM_IMAGES } from "@/constants/platformIntros/images";
import { useGameTypesStore } from "@/store/gameTypes";
import IntroGallery from "@/components/platforms/IntroGallery.vue";

const route = useRoute();
const gameTypes = useGameTypesStore();

const entry = computed(() => PLATFORM_INTROS.find((item) => item.id === route.params.id));

function labelOf(id) {
    return gameTypes.labelOf(id);
}

const consoleImages = computed(() =>
    (entry.value?.images.consoles || []).filter((key) => Boolean(PLATFORM_IMAGES[key])),
);
const mediaImages = computed(() =>
    (entry.value?.images.media || []).filter((key) => Boolean(PLATFORM_IMAGES[key])),
);

const isEmulator = computed(() => gameTypes.metaOf(route.params.id)?.kind === "emulator");
const consoleTitle = computed(() => (isEmulator.value ? "游戏机" : "平台形象"));
const mediaTitle = computed(() => (isEmulator.value ? "卡带与载体" : "载体形式"));

// Hero 用第一张存在的游戏机图；全部缺失时 Hero 自动收成单栏。
// consoleImages 存的是图片 key（供 IntroGallery 自己解析），这里要换成实际 URL。
const heroImage = computed(() => PLATFORM_IMAGES[consoleImages.value[0]] || "");

// 上一款 / 下一款按年份排，不用数据文件顺序（plus4 排在数组末尾）。
const orderedEntries = computed(() => [...PLATFORM_INTROS].sort((a, b) => a.year - b.year));
const currentIndex = computed(() =>
    orderedEntries.value.findIndex((item) => item.id === entry.value?.id),
);
const prevEntry = computed(() =>
    currentIndex.value > 0 ? orderedEntries.value[currentIndex.value - 1] : null,
);
const nextEntry = computed(() => {
    const index = currentIndex.value;
    return index >= 0 && index < orderedEntries.value.length - 1
        ? orderedEntries.value[index + 1]
        : null;
});

// 只在详情页之间切换（页尾翻页）时回到顶部；从列表进入保持原有滚动位置。
watch(
    () => route.params.id,
    () => window.scrollTo({ top: 0, behavior: "auto" }),
);
</script>

<style scoped>
.intro-page {
    max-width: 1080px;
    --intro-border-strong: #cbd5e1;
}

.intro-breadcrumb {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 20px;
    font-size: 13px;
    color: var(--text-muted);
}

.intro-breadcrumb a {
    color: var(--brand-accent);
    text-decoration: none;
}

.intro-breadcrumb a:hover {
    text-decoration: underline;
}

.intro-breadcrumb__sep {
    color: #cbd5e1;
}

.intro-hero {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 360px;
    align-items: center;
    gap: 44px;
    padding: 34px 36px;
    background: linear-gradient(135deg, #f8fbff 0%, #eef6fd 100%);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow-sm);
}

.intro-hero--text-only {
    grid-template-columns: minmax(0, 1fr);
}

.intro-hero__eyebrow {
    margin: 0 0 8px;
    font-size: 12px;
    letter-spacing: 0.12em;
    color: var(--brand-accent);
}

.intro-hero__title {
    margin: 0;
    font-size: clamp(26px, 2.6vw, 34px);
    font-weight: 600;
    line-height: 1.25;
    color: var(--brand-dark);
}

.intro-hero__summary {
    max-width: 62ch;
    margin: 14px 0 0;
    font-size: 15px;
    line-height: 1.8;
    color: var(--app-text);
}

.intro-hero__meta {
    display: flex;
    flex-wrap: wrap;
    margin: 22px 0 0;
}

.intro-hero__meta-item {
    padding: 0 20px;
    border-left: 1px solid rgba(15, 23, 42, 0.08);
}

.intro-hero__meta-item:first-child {
    padding-left: 0;
    border-left: 0;
}

.intro-hero__meta-item dt {
    font-size: 12px;
    color: var(--text-muted);
}

.intro-hero__meta-item dd {
    margin: 4px 0 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--brand-dark);
}

.intro-hero__media {
    margin: 0;
    aspect-ratio: 4 / 3;
    padding: 20px;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
}

.intro-hero__img {
    width: 100%;
    height: 100%;
    object-fit: contain;
}

.intro-section {
    margin-top: 40px;
}

.intro-section__title {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0 0 16px;
    font-size: 18px;
    font-weight: 600;
    color: var(--brand-dark);
}

.intro-section__title::before {
    content: "";
    width: 3px;
    height: 18px;
    border-radius: 2px;
    background: var(--brand-accent);
}

.spec-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin: 0;
}

.spec-card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 16px 18px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
}

.spec-card dt {
    font-size: 12px;
    color: var(--text-muted);
}

.spec-card dd {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    color: var(--brand-dark);
    overflow-wrap: anywhere;
}

.intro-prose {
    max-width: 80ch;
    padding: 24px 28px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
}

.intro-prose p {
    margin: 0 0 14px;
    font-size: 15px;
    line-height: 1.9;
    color: var(--app-text);
    text-indent: 2em;
}

.intro-prose p:last-child {
    margin-bottom: 0;
}

.intro-pager {
    display: flex;
    gap: 16px;
    margin-top: 48px;
    padding-top: 28px;
    border-top: 1px solid var(--border);
}

.intro-pager__link {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 6px;
    max-width: 48%;
    padding: 16px 18px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    text-decoration: none;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.intro-pager__link--next {
    margin-left: auto;
    text-align: right;
}

.intro-pager__label {
    font-size: 12px;
    color: var(--text-muted);
}

.intro-pager__name {
    font-size: 16px;
    font-weight: 600;
    color: var(--brand-dark);
}

.intro-pager__link:hover {
    border-color: var(--intro-border-strong);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}

.intro-pager__link:focus-visible {
    outline: 2px solid var(--app-color-primary);
    outline-offset: 2px;
}

@media (max-width: 900px) {
    .intro-hero {
        grid-template-columns: minmax(0, 1fr);
        gap: 24px;
        padding: 26px 24px;
    }

    .intro-hero__media {
        width: 100%;
        max-width: 520px;
        margin: 0 auto;
    }

    .spec-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 720px) {
    .intro-hero__meta-item {
        padding: 0 14px;
    }

    .intro-prose {
        padding: 20px;
    }
}

@media (max-width: 560px) {
    .spec-grid {
        grid-template-columns: 1fr;
    }

    .intro-pager {
        flex-direction: column;
    }

    .intro-pager__link {
        max-width: none;
    }

    .intro-pager__link--next {
        margin-left: 0;
        text-align: left;
    }
}

@media (prefers-reduced-motion: reduce) {
    .intro-pager__link {
        transition: none;
    }

    .intro-pager__link:hover {
        transform: none;
    }
}
</style>
