<template>
  <div class="drawer-mask" @click="$emit('close')"></div>
  <div class="drawer">
    <div class="drawer-head">
      <div class="drawer-title">AI 快速解读</div>
      <button class="icon-btn" @click="$emit('close')">✕</button>
    </div>
    <div class="drawer-body">
      <div class="detail-title">{{ item.title }}</div>
      <div class="detail-meta">
        <span>{{ item.name || item.code }}</span>
        <span>{{ item.date }}</span>
      </div>
      <div class="card" style="margin-top:12px">
        <div v-if="streaming" style="white-space:pre-wrap;font-size:13px;line-height:1.75">{{ text }}<span style="opacity:.5">▌</span></div>
        <div v-else-if="text" style="white-space:pre-wrap;font-size:13px;line-height:1.8">{{ text }}</div>
        <div v-else-if="error" style="color:#FF5C7A;font-size:13px">{{ error }}</div>
        <div v-else class="loading"><div class="spinner"></div>解读中…</div>
        <div class="ai-note">AI 生成，非投资建议</div>
      </div>
      <button v-if="!streaming && text" class="btn btn-primary" style="width:100%" @click="regen">
        重新生成
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";

const props = defineProps({ item: Object });
defineEmits(["close"]);

const text = ref("");
const streaming = ref(false);
const error = ref("");

async function run() {
  streaming.value = true;
  error.value = "";
  text.value = "";
  try {
    const res = await fetch(`/api/entry/${props.item.id}/ai`, { method: "POST" });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data:")) continue;
          try {
            const m = JSON.parse(line.slice(5));
            if (m.type === "chunk") text.value += m.text;
            else if (m.type === "error") error.value = m.msg;
          } catch {}
        }
      }
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    streaming.value = false;
  }
}

function regen() { run(); }
onMounted(run);
</script>

<style scoped>
.detail-title{font-size:16px;font-weight:600;line-height:1.5;margin-bottom:6px}
.detail-meta{color:var(--text-2);font-size:12px;margin-bottom:4px;display:flex;gap:10px}
.btn{padding:11px;border-radius:10px;background:rgba(94,234,212,.12);
  border:1px solid rgba(94,234,212,.35);color:var(--accent);
  font-size:13.5px;text-align:center}
.btn:active{opacity:.6}
</style>
