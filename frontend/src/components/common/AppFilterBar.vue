<template>
    <div class="app-filter-bar">
        <slot />
    </div>
</template>

<script setup>
</script>

<style scoped>
.app-filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    margin-bottom: 16px;
}
</style>
