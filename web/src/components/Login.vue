<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="login-brand">
        <span class="dot"></span>
        <span>投资雷达</span>
      </div>

      <div v-if="!configured" class="login-tip">
        首次使用，请设置访问口令（至少 8 位）。
      </div>
      <div v-else class="login-tip">请输入访问口令</div>

      <input
        v-model="pw"
        type="password"
        :placeholder="configured ? '口令' : '设置口令'"
        class="login-input"
        @keyup.enter="submit"
        autocomplete="current-password"
      />
      <input
        v-if="!configured"
        v-model="pw2"
        type="password"
        placeholder="再输一次"
        class="login-input"
        @keyup.enter="submit"
      />

      <button class="login-btn" :disabled="busy" @click="submit">
        {{ busy ? "处理中…" : configured ? "登录" : "设置并进入" }}
      </button>

      <div v-if="err" class="login-err">{{ err }}</div>
      <div class="login-note">仅限个人使用 · 数据不出本机</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";

const emit = defineEmits(["authed"]);

const pw = ref("");
const pw2 = ref("");
const configured = ref(true);
const busy = ref(false);
const err = ref("");

async function check() {
  try {
    const r = await fetch("/api/auth/status").then((x) => x.json());
    const d = r.data || {};
    // 认证已关闭：直接进入，不显示登录页
    if (d.auth_disabled) {
      emit("authed");
      return;
    }
    configured.value = d.configured ?? true;
    if (d.authenticated) emit("authed");
  } catch {}
}

async function submit() {
  err.value = "";
  if (!pw.value) return;
  if (!configured.value && pw.value !== pw2.value) {
    err.value = "两次输入不一致";
    return;
  }
  busy.value = true;
  try {
    const path = configured.value ? "/api/auth/login" : "/api/auth/setup";
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw.value }),
    });
    const j = await r.json();
    if (j.ok) {
      emit("authed");
    } else {
      err.value = j.msg || "失败";
    }
  } catch (e) {
    err.value = "网络错误";
  } finally {
    busy.value = false;
  }
}

onMounted(check);
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--bg) var(--bg-glow) no-repeat;
}
.login-card {
  width: 100%;
  max-width: 340px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  padding: 28px 22px;
  backdrop-filter: blur(20px);
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  font-weight: 600;
  margin-bottom: 18px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
  animation: breathe 2.4s ease-in-out infinite;
}
@keyframes breathe { 50% { transform: scale(0.6); opacity: 0.5; } }
.login-tip {
  color: var(--text-2);
  font-size: 12.5px;
  margin-bottom: 14px;
  line-height: 1.6;
}
.login-input {
  width: 100%;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 12px 13px;
  outline: none;
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--text);
}
.login-input:focus { border-color: rgba(94, 234, 212, 0.5); }
.login-btn {
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  background: var(--accent);
  color: #08090f;
  font-weight: 600;
  font-size: 14px;
  margin-top: 4px;
}
.login-btn:disabled { opacity: 0.5; }
.login-err {
  color: #ff5c7a;
  font-size: 12.5px;
  margin-top: 10px;
  text-align: center;
}
.login-note {
  color: #5b6373;
  font-size: 11px;
  text-align: center;
  margin-top: 16px;
}
</style>
