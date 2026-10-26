<template>
    <div class="start-gate">
        <app-button
            variant="secondary"
            size="lg"
            @click="$emit('start')"
        >
            开始游戏
        </app-button>
    </div>
</template>

<script setup>
defineEmits(["start"]);
</script>

<style scoped>
.start-gate {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    box-sizing: border-box;
}

</style>
