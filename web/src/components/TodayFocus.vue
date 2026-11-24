<template>
  <div class="tf-card">
    <div class="tf-head">
      <span class="tf-title">今日研究建议</span>
      <button v-if="!text && !streaming" class="tf-btn" @click="gen">生成</button>
      <button v-else-if="text && !streaming" class="tf-btn" @click="gen">重生成</button>
      <span v-else class="tf-loading">生成中…</span>
    </div>

    <div v-if="!text && !streaming && !unavailable" class="tf-hint">
      AI 会从近 24h 的信息里挑出最值得深挖的事项
    </div>
    <div v-else-if="unavailable" class="tf-hint">{{ unavailable }}</div>
    <div v-else class="tf-body">{{ text }}<span v-if="streaming" class="tf-cursor">▌</span></div>
    <div v-if="error" class="tf-err">{{ error }}</div>
    <div v-if="text" class="ai-note">AI 生成，仅供研究参考</div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { postSSE } from "../sse.js";

const text = ref("");
const streaming = ref(false);
const error = ref("");
const unavailable = ref("");

async function gen() {
  streaming.value = true;
  text.value = "";
  error.value = "";
  unavailable.value = "";
  await postSSE("/api/ai/today-focus", null, {
    onChunk: (t) => { text.value += t; },
    onError: (m) => {
      if (m.msg && m.msg.includes("不足")) {
        unavailable.value = m.msg;
      } else {
        error.value = m.msg;
      }
    },
    onDone: () => {},
  }, { timeoutMs: 180000 });
  streaming.value = false;
}
</script>

<style scoped>
.tf-card {
  background: rgba(94, 234, 212, 0.04);
  border: 1px solid rgba(94, 234, 212, 0.16);
  border-radius: var(--r-lg); padding: 14px; margin-bottom: var(--sp-3);
}
.tf-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.tf-title { font-size: var(--fs-sm); font-weight: 600; color: var(--accent); }
.tf-btn {
  font-size: 11px; padding: 3px 12px; border-radius: var(--r-full);
  background: var(--accent-dim); border: 1px solid var(--accent-border);
  color: var(--accent); min-height: 28px;
}
.tf-btn:active { opacity: 0.6; }
.tf-loading { font-size: 11px; color: var(--text-3); }
.tf-hint { font-size: var(--fs-sm); color: var(--text-3); line-height: 1.7; }
.tf-body {
  white-space: pre-wrap; font-size: 13px; line-height: 1.8;
  color: var(--text);
}
.tf-cursor { opacity: 0.5; }
.tf-err { color: var(--risk); font-size: var(--fs-sm); margin-top: 6px; }
</style>
