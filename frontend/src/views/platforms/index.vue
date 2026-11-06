<template>
    <div class="chronicle-page">
        <header class="page-header">
            <h1 class="page-title">机型简史</h1>
        </header>

        <div class="chronicle-grid">
            <router-link
                v-for="entry in entries"
                :key="entry.id"
                class="chronicle-card"
                :to="`/platforms/${entry.id}`"
            >
                <div class="chronicle-card__frame">
                    <img
                        v-if="imageOf(entry)"
                        class="chronicle-card__img"
                        :src="imageOf(entry)"
                        :alt="`${labelOf(entry.id)} 图片`"
                        loading="lazy"
                    />
                    <span v-else class="chronicle-card__icon" aria-hidden="true">
                        {{ iconOf(entry.id) }}
                    </span>
                </div>
                <div class="chronicle-card__caption">
                    <span class="chronicle-card__year">{{ entry.year }}</span>
                    <span class="chronicle-card__name">{{ labelOf(entry.id) }}</span>
                </div>
            </router-link>
        </div>
    </div>
</template>

<script setup>
import { computed } from "vue";
import { PLATFORM_INTROS } from "@/constants/platformIntros";
import { PLATFORM_IMAGES } from "@/constants/platformIntros/images";
import { useGameTypesStore } from "@/store/gameTypes";

const gameTypes = useGameTypesStore();
const entries = computed(() => [...PLATFORM_INTROS].sort((a, b) => a.year - b.year));

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
}

.chronicle-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 14px;
    margin-top: 24px;
}

.chronicle-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 12px 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    text-decoration: none;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.chronicle-card:hover {
    border-color: #cbd5e1;
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}

.chronicle-card:focus-visible {
    outline: 2px solid var(--app-color-primary);
    outline-offset: 2px;
}

.chronicle-card__frame {
    position: relative;
    aspect-ratio: 4 / 3;
    min-height: 0;
    background: #fff;
    border-radius: var(--radius-md);
    overflow: hidden;
}

.chronicle-card__img {
    position: absolute;
    inset: 6px;
    width: calc(100% - 12px);
    height: calc(100% - 12px);
    object-fit: contain;
    background: #fff;
}

.chronicle-card__icon {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 42px;
    line-height: 1;
}

.chronicle-card__caption {
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
    font-size: 13px;
    color: #0f172a;
}

.chronicle-card__year {
    flex: none;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}

.chronicle-card__name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

@media (max-width: 1200px) {
    .chronicle-grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }
}

@media (max-width: 900px) {
    .chronicle-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
}

@media (max-width: 600px) {
    .chronicle-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
</style>
