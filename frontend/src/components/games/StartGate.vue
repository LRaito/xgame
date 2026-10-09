<template>
    <div class="start-gate">
        <button type="button" class="start-gate__btn" @click="$emit('start')">开始游戏</button>
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

.start-gate__btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 14px 38px;
    border: 0;
    border-radius: 14px;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: #fff;
    font-family: inherit;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.02em;
    cursor: pointer;
    box-shadow: 0 12px 28px rgba(37, 99, 235, 0.35);
    transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}

.start-gate__btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 34px rgba(37, 99, 235, 0.45);
    filter: brightness(1.05);
}

.start-gate__btn:active {
    transform: translateY(0);
}
</style>
