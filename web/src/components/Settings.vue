<template>
  <div class="settings">
    <div class="sec">
      <div class="sec-title">
        我的 DeepSeek API Key
        <span v-if="key.has_key" class="badge ok">已配置</span>
        <span v-else class="badge warn">未配置</span>
      </div>

      <div v-if="key.has_key" class="row">
        <span class="k">当前</span>
        <span class="v mono">{{ key.key_hint }}</span>
      </div>

      <div class="edit-row">
        <input
          v-model="keyInput"
          class="inp mono"
          type="password"
          placeholder="sk-..."
          autocomplete="off"
          spellcheck="false"
        />
        <button class="btn" :disabled="!keyInput.trim() || saving" @click="save">
          {{ saving ? "…" : key.has_key ? "更换" : "保存" }}
        </button>
      </div>

      <div class="btn-row">
        <button class="btn ghost" :disabled="!key.has_key || testing" @click="test">
          {{ testing ? "测试中…" : "测试连接" }}
        </button>
        <button class="btn danger" :disabled="!key.has_key || deleting" @click="del">
          {{ deleting ? "…" : "删除" }}
        </button>
      </div>

      <div v-if="testResult" class="result" :class="testResult.ok ? 'ok' : 'bad'">
        {{ testResult.ok ? `连接正常：${testResult.reply || "OK"}` : testResult.msg }}
      </div>
      <div v-if="msg" class="result" :class="msgOk ? 'ok' : 'bad'">{{ msg }}</div>

      <div class="hint">
        Key 加密保存在本机，只有你能用；不会出现在安装包里，也不会写进日志。
        留空不填则 AI 功能不可用，其他功能照常。
      </div>
    </div>

    <div class="sec">
      <div class="sec-title">AI 模型</div>
      <div class="edit-row">
        <input v-model="mCheap" class="inp" placeholder="快捷模型" />
        <input v-model="mStrong" class="inp" placeholder="深度模型" />
      </div>
      <div class="btn-row">
        <button class="btn ghost" @click="saveModels">保存模型设置</button>
      </div>
      <div class="hint">默认 deepseek-chat（快、便宜）/ deepseek-reasoner（深度推理）。</div>
    </div>

    <div class="sec">
      <div class="sec-title">我的用量</div>
      <div class="grid">
        <div class="metric"><div class="k">解读缓存</div><div class="v">{{ usage?.cached_interpretations ?? "-" }}</div></div>
        <div class="metric"><div class="k">对话轮次</div><div class="v">{{ usage?.chat_rounds ?? "-" }}</div></div>
        <div class="metric"><div class="k">本月估算</div><div class="v accent">¥{{ usage?.est_cost_cny ?? "-" }}</div></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api, req } from "../api.js";

const key = ref({ has_key: false, key_hint: "" });
const usage = ref(null);

const keyInput = ref("");
const mCheap = ref("deepseek-chat");
const mStrong = ref("deepseek-reasoner");

const saving = ref(false);
const deleting = ref(false);
const testing = ref(false);
const msg = ref("");
const msgOk = ref(false);
const testResult = ref(null);

function say(text, ok = false) {
  msg.value = text;
  msgOk.value = ok;
  setTimeout(() => { msg.value = ""; }, 4000);
}

async function load() {
  try { key.value = await api.myKey(); } catch {}
  try { usage.value = await req("/api/ai/usage"); } catch {}
  mCheap.value = key.value.model_cheap || "deepseek-chat";
  mStrong.value = key.value.model_strong || "deepseek-reasoner";
}

async function save() {
  saving.value = true;
  testResult.value = null;
  try {
    key.value = await api.saveKey(keyInput.value.trim());
    keyInput.value = "";
    say("已保存（加密存储）", true);
  } catch (e) {
    say(e.message);
  } finally {
    saving.value = false;
  }
}

async function test() {
  testing.value = true;
  testResult.value = null;
  try {
    const r = await api.testKey();
    testResult.value = r.ok ? { ok: true, reply: r.reply } : { ok: false, msg: r.msg };
  } catch (e) {
    testResult.value = { ok: false, msg: e.message };
  } finally {
    testing.value = false;
  }
}

async function del() {
  if (!confirm("删除后 AI 功能将不可用，确定？")) return;
  deleting.value = true;
  try {
    key.value = await api.delKey();
    say("已删除", true);
  } catch (e) {
    say(e.message);
  } finally {
    deleting.value = false;
  }
}

async function saveModels() {
  try {
    key.value = await api.saveAiSettings({
      model_cheap: mCheap.value.trim() || "deepseek-chat",
      model_strong: mStrong.value.trim() || "deepseek-reasoner",
    });
    say("模型设置已保存", true);
  } catch (e) {
    say(e.message);
  }
}

onMounted(load);
</script>

<style scoped>
.settings { padding: 12px 14px 90px; }
.sec {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 14px;
  margin-bottom: 12px;
}
.sec-title {
  font-size: 13.5px;
  font-weight: 600;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge {
  font-size: 10.5px;
  padding: 2px 7px;
  border-radius: 999px;
  font-weight: 500;
}
.badge.ok { background: rgba(34, 197, 94, 0.16); color: #4ade80; }
.badge.warn { background: rgba(245, 158, 11, 0.16); color: #fbbf24; }
.row { display: flex; justify-content: space-between; font-size: 13px; padding: 4px 0; }
.k { color: var(--text-2); }
.v { color: var(--text); }
.mono { font-family: ui-monospace, Menlo, monospace; }
.edit-row { display: flex; gap: 8px; margin-top: 8px; }
.inp {
  flex: 1;
  min-width: 0;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 9px 11px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.inp:focus { border-color: rgba(94, 234, 212, 0.5); }
.btn {
  padding: 9px 14px;
  border-radius: 8px;
  background: var(--accent);
  color: #08090f;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}
.btn:disabled { opacity: 0.4; }
.btn.ghost {
  background: rgba(255, 255, 255, 0.07);
  color: var(--text);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.btn.danger {
  background: rgba(239, 68, 68, 0.16);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}
.btn.wide { width: 100%; margin-top: 2px; }
.btn-row { display: flex; gap: 8px; margin-top: 8px; }
.hint {
  color: var(--text-2);
  font-size: 11.5px;
  line-height: 1.65;
  margin-top: 10px;
}
.result {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12.5px;
}
.result.ok { background: rgba(34, 197, 94, 0.12); color: #4ade80; }
.result.bad { background: rgba(239, 68, 68, 0.12); color: #f87171; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.metric { text-align: center; }
.metric .k { font-size: 11px; }
.metric .v { font-size: 16px; font-weight: 600; margin-top: 3px; }
.accent { color: var(--accent); }
</style>
