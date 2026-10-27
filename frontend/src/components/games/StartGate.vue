<template>
    <div class="start-gate">
        <div class="start-gate__content">
            <button
                type="button"
                class="start-gate__start"
                aria-label="开始游戏"
                @click="$emit('start')"
            >
                <span class="start-gate__press">PRESS START</span>
                <span class="start-gate__zh">投币开始</span>
            </button>
            <span class="start-gate__coin" aria-hidden="true">INSERT COIN</span>
        </div>
    </div>
</template>

<script setup>
defineEmits(["start"]);
</script>

<style scoped>
/* 街机像素字体随前端资源一起打包，运行时不依赖外网 */
@font-face {
    font-family: "Press Start 2P";
    src: url("../../assets/fonts/press-start-2p.woff2") format("woff2");
    font-style: normal;
    font-weight: 400;
    font-display: swap;
}

/* 整块播放区都是启动画面：铺满外壳正文，扫描线与光晕只做氛围，不接事件 */
.start-gate {
    position: relative;
    width: 100%;
    align-self: stretch;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 32px 24px;
    overflow: hidden;
    box-sizing: border-box;
}

.start-gate::before {
    content: "";
    position: absolute;
    left: 50%;
    top: 50%;
    width: min(760px, 92vw);
    height: min(760px, 92vw);
    transform: translate(-50%, -50%);
    border-radius: 50%;
    background: radial-gradient(circle, rgba(0, 152, 238, 0.16), transparent 62%);
    pointer-events: none;
}

.start-gate::after {
    content: "";
    position: absolute;
    inset: 0;
    z-index: 2;
    pointer-events: none;
    background: repeating-linear-gradient(
        0deg,
        rgba(2, 6, 16, 0.3) 0 1px,
        transparent 1px 4px
    );
    opacity: 0.22;
}

.start-gate__content {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: clamp(18px, 2vw, 26px);
}

/* 按钮只承载 PRESS START 与中文提示，投币字样留在外面 */
.start-gate__start {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: clamp(8px, 1vw, 12px);
    padding: 0;
    border: 0;
    background: transparent;
    cursor: pointer;
    font: inherit;
    color: inherit;
}

.start-gate__press {
    font-family: "Press Start 2P", "Courier New", monospace;
    font-size: clamp(18px, 3vw, 34px);
    line-height: 1.25;
    color: #7cf3ff;
    text-shadow:
        0 0 6px #00e5ff,
        0 0 18px rgba(0, 229, 255, 0.7),
        0 0 36px rgba(0, 229, 255, 0.35);
    animation: start-gate-blink 1.2s steps(1, end) infinite;
}

.start-gate__zh {
    font-size: clamp(11px, 1.1vw, 14px);
    letter-spacing: 0.62em;
    padding-left: 0.62em;
    color: #ffcf5c;
    text-shadow: 0 0 12px rgba(255, 207, 92, 0.35);
}

.start-gate__coin {
    font-family: "Press Start 2P", "Courier New", monospace;
    font-size: clamp(9px, 0.9vw, 12px);
    letter-spacing: 0.34em;
    padding-left: 0.34em;
    color: #ff6b9a;
    text-shadow: 0 0 10px rgba(255, 107, 154, 0.5);
    animation: start-gate-blink 2.4s steps(1, end) infinite;
}

.start-gate__start:hover .start-gate__press {
    color: #ffffff;
    text-shadow:
        0 0 8px #ffffff,
        0 0 22px #00e5ff,
        0 0 44px rgba(0, 229, 255, 0.55);
}

.start-gate__start:focus-visible {
    outline: 2px solid #7fd4f8;
    outline-offset: 8px;
    border-radius: 4px;
}

@keyframes start-gate-blink {
    0%, 62% {
        opacity: 1;
    }
    63%, 100% {
        opacity: 0.18;
    }
}

@media (prefers-reduced-motion: reduce) {
    .start-gate__press,
    .start-gate__coin {
        animation: none;
    }
}
</style>
