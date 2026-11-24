<template>
  <div>
    <!-- 对话记录 -->
    <div v-for="(m, i) in messages" :key="i" class="gm" :class="m.role">
      <div class="gm-label">{{ m.role === "user" ? "我" : "AI 助手" }}</div>
      <div class="gm-bubble">{{ m.content }}</div>
    </div>

    <div v-if="streaming" class="gm assistant">
      <div class="gm-label">AI 助手</div>
      <div class="gm-bubble">{{ streamText }}<span style="opacity:.5">▌</span></div>
    </div>

    <div v-if="!messages.length && !streaming" class="empty">
      问我任何事，比如：<br />
      「冠农最近的公告跟我的逻辑什么关系」<br />
      「两只票现在哪个估值更低」<br />
      「总结一下这周所有风险公告」
    </div>

    <!-- 输入 -->
    <div class="gai-input">
      <input v-model="q" placeholder="问点什么都行…"
             @keyup.enter="ask" :disabled="streaming" />
      <button class="gai-web" :class="{ on: webOn }" @click="webOn = !webOn"
              :title="webOn ? '联网检索：开' : '联网检索：关'">{{ webOn ? "🌐" : "🔒" }}</button>
      <button class="gai-send" @click="ask" :disabled="streaming || !q.trim()">➤</button>
    </div>
    <button v-if="messages.length" class="gai-clear" @click="clearAll">清空对话</button>
    <div class="ai-note">AI 生成，非投资建议；上下文自动带上关注池与相关词条</div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from "vue";
import { API_BASE } from "../env.js";
import { api, req as rawReq } from "../api.js";

const messages = ref([]);
const q = ref("");
const streaming = ref(false);
const streamText = ref("");
const webOn = ref(true);

async function loadHistory() {
  try {
    const h = await rawReq("/api/chat/global");
    messages.value = h.map((x) => ({ role: x.role, content: x.content }));
  } catch {}
}

async function ask() {
  const question = q.value.trim();
  if (!question || streaming.value) return;
  q.value = "";
  messages.value.push({ role: "user", content: question });
  streaming.value = true;
  streamText.value = "";
  try {
    const res = await fetch(`${API_BASE}/api/ai/global`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, web: webOn.value }),
    });
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
            if (m.type === "chunk") streamText.value += m.text;
            else if (m.type === "done") {
              messages.value.push({ role: "assistant", content: streamText.value });
              streamText.value = "";
            } else if (m.type === "error") {
              messages.value.push({ role: "assistant", content: "⚠ " + m.msg });
            }
          } catch {}
        }
      }
    }
  } catch (e) {
    messages.value.push({ role: "assistant", content: "⚠ " + e.message });
  } finally {
    streaming.value = false;
    nextTick(() => window.scrollTo(0, 1e9));
  }
}

async function clearAll() {
  try { await rawReq("/api/chat/global", { method: "DELETE" }); } catch {}
  messages.value = [];
}

onMounted(loadHistory);
</script>

<style scoped>
.gm{margin-bottom:14px}
.gm-label{font-size:10.5px;color:var(--text-2);margin-bottom:4px}
.gm.user .gm-bubble{
  background:rgba(94,234,212,.1);border:1px solid rgba(94,234,212,.25);
  border-radius:12px 12px 12px 4px;padding:10px 12px;font-size:13px;line-height:1.7;
  white-space:pre-wrap;word-break:break-word;
}
.gm.assistant .gm-bubble{
  background:var(--card-bg);border:1px solid var(--card-border);
  border-radius:12px 12px 4px 12px;padding:10px 12px;font-size:13px;line-height:1.8;
  white-space:pre-wrap;word-break:break-word;
}
.gai-input{display:flex;gap:8px;margin-top:6px;position:sticky;bottom:90px}
.gai-input input{
  flex:1;background:var(--panel2);border:1px solid var(--line);
  border-radius:12px;padding:11px 13px;outline:none;font-size:13.5px;
}
.gai-send{
  width:44px;border-radius:12px;background:var(--accent);color:#08090F;
  font-size:16px;font-weight:700;
}
.gai-send:disabled{opacity:.4}
.gai-send:active{opacity:.7}
.gai-web{
  width:44px;border-radius:12px;font-size:16px;
  background:var(--panel2);border:1px solid var(--line);
}
.gai-web.on{background:rgba(94,234,212,.14);border-color:rgba(94,234,212,.4)}
.gai-clear{
  margin:12px auto 0;display:block;font-size:11.5px;color:var(--text-2);
  padding:5px 14px;border-radius:12px;border:1px solid var(--line);
}
.gai-clear:active{opacity:.6}
</style>
