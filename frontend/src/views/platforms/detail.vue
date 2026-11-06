<template>
    <div v-if="entry" class="intro-page">
        <nav class="intro-page__back">
            <router-link to="/platforms">← 机型简史</router-link>
        </nav>

        <header class="intro-hero">
            <h1 class="intro-hero__title">{{ labelOf(entry.id) }}</h1>
            <p class="intro-hero__meta">
                {{ entry.year }} · {{ entry.maker }} · {{ entry.generation }}
            </p>
            <p class="intro-hero__summary">{{ entry.summary }}</p>
        </header>

        <section class="intro-section">
            <h2 class="intro-section__title">参数速览</h2>
            <dl class="intro-facts">
                <div v-for="fact in entry.facts" :key="fact.label" class="intro-facts__row">
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
    </div>

    <app-empty v-else description="没有这个机型的介绍" />
</template>

<script setup>
import { computed } from "vue";
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
</script>

<style scoped>
.intro-page {
    max-width: 880px;
}

.intro-page__back {
    margin-bottom: 18px;
    font-size: 13px;
}

.intro-page__back a {
    color: var(--brand-accent);
    text-decoration: none;
}

.intro-hero__title {
    margin: 0;
    font-size: 30px;
    font-weight: 600;
    color: #0f172a;
}

.intro-hero__meta {
    margin: 8px 0 0;
    font-size: 13px;
    color: var(--text-muted);
}

.intro-hero__summary {
    margin: 14px 0 0;
    font-size: 15px;
    line-height: 1.8;
    color: #334155;
}

.intro-section {
    margin-top: 34px;
}

.intro-section__title {
    margin: 0 0 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
    font-size: 17px;
    font-weight: 600;
    color: #0f172a;
}

.intro-facts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0;
    margin: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    overflow: hidden;
}

.intro-facts__row {
    display: flex;
    gap: 12px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
}

.intro-facts__row:nth-child(odd) {
    border-right: 1px solid var(--border);
}

.intro-facts__row dt {
    flex: none;
    width: 84px;
    color: var(--text-muted);
}

.intro-facts__row dd {
    margin: 0;
    color: #0f172a;
}

.intro-prose p {
    margin: 0 0 14px;
    font-size: 15px;
    line-height: 1.9;
    color: #334155;
    text-indent: 2em;
}

.intro-prose p:last-child {
    margin-bottom: 0;
}

@media (max-width: 720px) {
    .intro-facts {
        grid-template-columns: 1fr;
    }

    .intro-facts__row:nth-child(odd) {
        border-right: none;
    }
}
</style>
