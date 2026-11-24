<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="login-brand">
        <span class="dot"></span>
        <span>投资雷达</span>
      </div>

      <div class="login-tip">
        {{ isFirst ? "第一次来？输入一个名字就能开始，不用密码。" : "输入你的名字进入" }}
      </div>

      <input
        v-model="name"
        type="text"
        placeholder="你的名字（下次用同一个）"
        class="login-input"
        maxlength="24"
        autocomplete="username"
        autocapitalize="off"
        @keyup.enter="submit"
      />

      <!-- 已有人名：点一下直接进入，少打字 -->
      <div v-if="known.length" class="known">
        <span class="known-label">最近用过：</span>
        <button
          v-for="u in known"
          :key="u.name"
          class="known-chip"
          :disabled="busy"
          @click="pick(u.name)"
        >{{ u.name }}</button>
      </div>

      <button class="login-btn" :disabled="busy || !name.trim()" @click="submit">
        {{ busy ? "进入中…" : "进入" }}
      </button>

      <div v-if="err" class="login-err">{{ err }}</div>
      <div class="login-note">名字即身份 · 数据互相隔离 · 无需密码</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { API_BASE, setToken } from "../env.js";

const emit = defineEmits(["authed"]);

const name = ref("");
const busy = ref(false);
const err = ref("");
const known = ref([]);
const hasUsers = ref(false);

const isFirst = computed(() => !hasUsers.value && !known.value.length);

async function check() {
  try {
    const r = await fetch(`${API_BASE}/api/auth/status`).then((x) => x.json());
    hasUsers.value = !!r.data?.has_users;
    if (r.data?.authenticated) {
      // 已登录（Cookie 仍在），直接进
      emit("authed", { name: r.data.user });
      return;
    }
  } catch {}
  try {
    const r = await fetch(`${API_BASE}/api/auth/users`).then((x) => x.json());
    known.value = (r.data || []).slice(0, 6);
  } catch {}
}

function pick(n) {
  name.value = n;
  submit();
}

async function submit() {
  err.value = "";
  const n = name.value.trim();
  if (!n || busy.value) return;
  busy.value = true;
  try {
    const res = await fetch(`${API_BASE}/api/auth/enter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ name: n }),
    });
    const j = await res.json();
    if (j.ok) {
      // APK 走 Bearer；浏览器同时也有 Cookie
      if (j.data?.token) setToken(j.data.token);
      emit("authed", { name: j.data?.name, created: j.data?.created });
    } else {
      err.value = j.msg || "进入失败";
    }
  } catch (e) {
    err.value = "网络错误，请检查连接";
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
  font-size: 15px;
  margin-bottom: 10px;
  color: var(--text);
}
.login-input:focus { border-color: rgba(94, 234, 212, 0.5); }
.known {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 2px 0 12px;
}
.known-label { color: var(--text-2); font-size: 11.5px; }
.known-chip {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(94, 234, 212, 0.12);
  border: 1px solid rgba(94, 234, 212, 0.3);
  color: var(--accent);
  font-size: 12.5px;
}
.known-chip:disabled { opacity: 0.5; }
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
.login-btn:disabled { opacity: 0.45; }
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
