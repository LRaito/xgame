<template>
    <div class="login-page">
        <div class="login-card">
            <header class="login-card__header">
                <div class="login-card__mark">X</div>
                <h1 class="login-card__title">{{ isRegister ? "注册" : "登录" }}</h1>
            </header>

            <el-form
                class="login-form"
                :model="form"
                label-position="top"
                size="large"
                @submit.prevent="onSubmit"
            >
                <el-form-item label="用户名">
                    <el-input
                        v-model="form.username"
                        autocomplete="username"
                        placeholder="数字、字母、中划线、下划线"
                        :prefix-icon="User"
                        @input="clearError"
                    />
                </el-form-item>
                <el-form-item label="密码">
                    <el-input
                        v-model="form.password"
                        type="password"
                        :autocomplete="isRegister ? 'new-password' : 'current-password'"
                        placeholder="请输入密码"
                        show-password
                        :prefix-icon="Lock"
                        @input="clearError"
                    />
                </el-form-item>
                <el-form-item v-if="isRegister" label="确认密码">
                    <el-input
                        v-model="form.confirm"
                        type="password"
                        autocomplete="new-password"
                        placeholder="再输入一次密码"
                        show-password
                        :prefix-icon="Lock"
                        @input="clearError"
                    />
                </el-form-item>
                <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>
                <app-button
                    class="login-submit"
                    type="primary"
                    :loading="loading"
                    native-type="submit"
                >
                    {{ isRegister ? "注册并进入" : "登录" }}
                </app-button>
            </el-form>

            <p class="login-switch">
                <span>{{ isRegister ? "已经有账号了？" : "还没有账号？" }}</span>
                <app-button link type="primary" @click="toggleMode">
                    {{ isRegister ? "去登录" : "注册一个" }}
                </app-button>
            </p>
        </div>
    </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Lock, User } from "@element-plus/icons-vue";
import { ensureCsrf } from "@/utils/request";
import { useAuthStore } from "@/store/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const isRegister = ref(false);
const loading = ref(false);
const errorMessage = ref("");
const form = reactive({ username: "", password: "", confirm: "" });

function clearError() {
    errorMessage.value = "";
}

function toggleMode() {
    isRegister.value = !isRegister.value;
    clearError();
    form.password = "";
    form.confirm = "";
}

function afterAuth() {
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    router.push(redirect.startsWith("/") ? redirect : "/");
}

async function onSubmit() {
    if (loading.value) {
        return;
    }
    errorMessage.value = "";
    if (isRegister.value && form.password !== form.confirm) {
        errorMessage.value = "两次输入的密码不一致。";
        return;
    }
    loading.value = true;
    try {
        await ensureCsrf();
        const payload = { username: form.username, password: form.password };
        if (isRegister.value) {
            await auth.register(payload);
        } else {
            await auth.login(payload);
        }
        afterAuth();
    } catch (err) {
        errorMessage.value = err.message || (isRegister.value ? "注册失败，请稍后重试。" : "登录失败，请稍后重试。");
    } finally {
        loading.value = false;
    }
}
</script>

<style scoped>
.login-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 32px 24px;
    background: #f5f6f8;
}

.login-card {
    width: 100%;
    max-width: 420px;
    background: #fff;
    border-radius: 16px;
    padding: 40px 36px 36px;
    border: 1px solid #e5e7eb;
    box-shadow:
        0 1px 2px rgba(15, 23, 42, 0.04),
        0 12px 40px rgba(15, 23, 42, 0.08);
}

.login-card__header {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    margin-bottom: 28px;
    text-align: center;
}

.login-card__mark {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    background: #1f2a37;
    color: #fff;
    font-size: 22px;
    font-weight: 700;
}

.login-card__title {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
    color: #111827;
}

.login-form :deep(.el-form-item__label) {
    font-weight: 500;
    color: #374151;
    padding-bottom: 6px;
}

.login-form :deep(.el-input__wrapper) {
    border-radius: 10px;
    box-shadow: 0 0 0 1px #e5e7eb inset;
    transition: box-shadow 0.2s ease;
}

.login-form :deep(.el-input__wrapper:hover) {
    box-shadow: 0 0 0 1px #cbd5e1 inset;
}

.login-form :deep(.el-input__wrapper.is-focus) {
    box-shadow: 0 0 0 1px #1f2a37 inset;
}

.login-submit {
    width: 100%;
    margin-top: 8px;
    height: 44px;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 500;
}

.login-error {
    margin: 4px 0 0;
    font-size: 13px;
    line-height: 1.5;
    color: #dc2626;
}

.login-switch {
    margin: 18px 0 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    font-size: 13px;
    color: #6b7280;
}

@media (max-width: 480px) {
    .login-card {
        padding: 32px 24px 28px;
    }
}
</style>
