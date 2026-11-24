<template>
  <div class="drawer-mask" @click="$emit('close')"></div>
  <div class="drawer">
    <div class="drawer-head">
      <div class="drawer-title">{{ typeLabel }}</div>
      <button class="icon-btn" @click="$emit('close')">✕</button>
    </div>

    <div class="drawer-body">
      <div v-if="loading" class="loading"><div class="spinner"></div>加载中…</div>

      <template v-else-if="d">
        <div class="detail-title">{{ d.title }}</div>
        <div class="detail-meta">
          <span>{{ d.date }}</span>
          <span v-if="d.watch?.name">{{ d.watch.name }}</span>
          <span :class="'tag ' + levelCls(d.level)">{{ levelLabel(d.level) }}</span>
        </div>

        <div v-if="d.content" class="detail-content">{{ d.content }}</div>
        <div v-else class="empty" style="padding: 20px">
          这条没有正文<br />
          <span style="font-size: 12px">点下面「看原文」打开源站</span>
        </div>

        <!-- AI 区域 -->
        <div class="card" style="margin-top: 0">
          <div class="card-title" style="display:flex;justify-content:space-between;align-items:center">
            <span>AI 解读</span>
            <button v-if="aiDone && !aiStreaming" class="btn btn-sm" @click="genAI(true)">
              重新生成
            </button>
          </div>

          <!-- 流式原文 -->
          <div v-if="aiStreaming || aiRaw" style="white-space:pre-wrap;font-size:13px;line-height:1.75">{{ aiRaw }}</div>
          <div v-if="aiStreaming" class="loading" style="padding:12px">
            <div class="spinner" style="width:14px;height:14px;margin:0"></div>
          </div>
          <div v-else-if="aiError" style="color:#f87171;font-size:12.5px;padding:8px 0">{{ aiError }}</div>

          <!-- 结构化四段 -->
          <div v-else-if="aiSegs.length" style="font-size: 13px; line-height: 1.75">
            <div v-for="(seg, i) in aiSegs" :key="i" style="margin-bottom: 12px">
              <div style="color: var(--dim); font-size: 11px; margin-bottom: 3px">{{ seg.label }}</div>
              <div>{{ seg.text }}</div>
            </div>
            <div v-if="aiCached" class="tag t-note" style="margin-top:4px">已解读过（缓存）</div>
          </div>

          <!-- 未解读 -->
          <div v-else-if="!aiStreaming && !aiRaw && !aiError" style="color: var(--dim); font-size: 12.5px; line-height: 1.7">
            <button class="btn btn-primary btn-sm" style="width:100%" @click="genAI(false)">
              ⚡ AI 解读这条
            </button>
            <div class="ai-note">输出四段：这是什么 / 为什么重要 / 跟你的 thesis 什么关系 / 原文重点</div>
          </div>
        </div>

        <!-- 深度论证（多空辩论） -->
        <div class="card" style="margin-top:12px">
          <div class="card-title" style="display:flex;justify-content:space-between;align-items:center">
            <span>多空辩论</span>
            <button v-if="debateDone" class="btn btn-sm" @click="runDebate">重跑</button>
          </div>
          <button v-if="!debateDone && !debateStreaming" class="btn btn-sm"
                  style="width:100%" @click="runDebate">⚖ 三视角深度论证（看多 vs 看空 → 裁决）</button>
          <div v-if="debateStreaming" style="font-size:13px;line-height:1.75">
            <div v-for="seg in debateSegs" :key="seg.key" style="margin-bottom:12px">
              <div style="font-size:11px;margin-bottom:4px"
                   :style="{color: seg.key==='bull' ? 'var(--up)' : seg.key==='bear' ? 'var(--down)' : 'var(--accent)'}">
                {{ seg.label }} {{ seg.streaming ? "…" : "" }}
              </div>
              <div style="white-space:pre-wrap">{{ seg.text }}<span v-if="seg.streaming" style="opacity:.5">▌</span></div>
            </div>
          </div>
          <div v-else-if="debateDone" style="font-size:13px;line-height:1.75">
            <div v-for="seg in debateSegs" :key="seg.key" style="margin-bottom:12px">
              <div style="font-size:11px;margin-bottom:4px"
                   :style="{color: seg.key==='bull' ? 'var(--up)' : seg.key==='bear' ? 'var(--down)' : 'var(--accent)'}">
                {{ seg.label }}
              </div>
              <div style="white-space:pre-wrap">{{ seg.text }}</div>
            </div>
          </div>
          <div v-if="debateError" style="color:#FF5C7A;font-size:12.5px">{{ debateError }}</div>
          <div class="ai-note">三视角仅供参考，非投资建议</div>
        </div>

        <!-- 追问 -->
        <div class="card" v-if="aiDone || aiSegs.length || d.content">
          <div class="card-title">追问</div>
          <div v-for="(m, i) in chatLog" :key="i"
               :class="m.role === 'user' ? 'chat-user' : 'chat-ai'"
               style="font-size:13px;line-height:1.7;margin-bottom:10px;white-space:pre-wrap">
            <div v-if="m.role==='user'" style="color:#93c5fd;font-size:11px;margin-bottom:2px">我</div>
            <div v-else style="color:var(--dim);font-size:11px;margin-bottom:2px">AI（{{ chatModel }}）</div>
            <div>{{ m.content }}</div>
          </div>
          <div v-if="chatStreaming" style="white-space:pre-wrap;font-size:13px;line-height:1.7">{{ chatRaw }}<span style="opacity:.5">▌</span></div>
          <div style="display:flex;gap:8px;margin-top:8px">
            <input
              v-model="chatQ"
              placeholder="针对这条内容追问…"
              style="flex:1;background:var(--panel2);border:1px solid var(--line);
                     border-radius:8px;padding:9px 11px;outline:none"
              @keyup.enter="ask"
            />
            <button class="btn btn-primary btn-sm" @click="ask" :disabled="chatStreaming || !chatQ.trim()">发送</button>
          </div>
          <div class="ai-note">追问用 deepseek-reasoner（深度模型），消耗较大</div>
        </div>

        <!-- 同公司其他 -->
        <div v-if="d.siblings?.length" class="card">
          <div class="card-title">同期其他</div>
          <div v-for="s in d.siblings" :key="s.id" class="entry" style="padding: 8px 0">
            <div class="entry-dot" :style="{ background: levelDot(s.level) }"></div>
            <div class="entry-body">
              <div class="entry-title" style="font-size: 12.5px">{{ s.title }}</div>
              <div class="entry-meta"><span>{{ s.date }}</span></div>
            </div>
          </div>
        </div>

        <div class="ai-note">
          内容来自第三方公开数据，以原始公告为准<br />
          不构成投资建议
        </div>
      </template>
    </div>

    <div class="drawer-foot">
      <a
        v-if="d?.url"
        class="btn btn-primary"
        :href="d.url"
        target="_blank"
        rel="noopener"
      >看原文</a>
      <a
        v-else
        class="btn"
        :href="searchUrl"
        target="_blank"
        rel="noopener"
      >全网搜索</a>
      <a
        v-if="d?.url"
        class="btn"
        :href="searchUrl"
        target="_blank"
        rel="noopener"
      >雪球搜索</a>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, onUnmounted } from "vue";
import { api, levelDot } from "../api.js";
import { postSSE } from "../sse.js";

const props = defineProps({ entryId: String });
defineEmits(["close"]);

const d = ref(null);
const loading = ref(true);

// AI 解读状态
const aiRaw = ref("");
const aiSegs = ref([]);
const aiStreaming = ref(false);
const aiDone = ref(false);
const aiError = ref("");
const aiCached = ref(false);
const aiWarn = ref("");
let aiAbort = new AbortController();
let chatAbort = new AbortController();
let debateAbort = new AbortController();

// 追问状态
const chatQ = ref("");
const chatLog = ref([]);
const chatRaw = ref("");
const chatStreaming = ref(false);
const chatModel = ref("reasoner");

// 多空辩论状态
const debateStreaming = ref(false);
const debateDone = ref(false);
const debateError = ref("");
const debateSegs = ref([]);   // [{key:'bull'|'bear'|'judge', label, text, streaming}]

const ai = computed(() => d.value?.ai || null);

const aiSegs0 = computed(() => {
  const a = ai.value;
  if (!a) return [];
  return [
    { label: "这是什么", text: a.summary },
    { label: "为什么重要", text: a.why_matters },
    { label: "跟我的 thesis", text: a.thesis_impact },
    { label: "原文重点", text: a.read_hint },
  ].filter((x) => x.text);
});

// 页面初始时如果有缓存，直接展示四段
watch(() => d.value, (v) => {
  if (v?.ai) {
    aiSegs.value = aiSegs0.value;
    aiDone.value = true;
    aiCached.value = true;
  }
}, { immediate: true });

const typeLabel = computed(() => {
  const m = { notice: "公告", news: "新闻", qa: "投资者问答", report: "研报" };
  return m[d.value?.type] || "详情";
});

const searchUrl = computed(() => {
  const nm = d.value?.watch?.name || "";
  const t = (d.value?.title || "").slice(0, 20);
  return `https://xueqiu.com/k?q=${encodeURIComponent(nm + " " + t)}`;
});

function levelCls(lv) {
  return lv === "risk" ? "t-risk" : lv === "positive" ? "t-good" : "t-n";
}
function levelLabel(lv) {
  return lv === "risk" ? "需关注" : lv === "positive" ? "利好" : "中性";
}

async function genAI(force) {
  aiStreaming.value = true;
  aiError.value = "";
  aiRaw.value = "";
  aiSegs.value = [];
  aiDone.value = false;
  aiCached.value = false;
  try {
    await postSSE(`/api/entry/${props.entryId}/ai${force ? "?force=true" : ""}`,
      null,
      {
        onStart: (m) => { if (m.cached) aiCached.value = true; },
        onChunk: (t) => { aiRaw.value += t; },
        onSegment: (k, label, text) => {
          // 用 key 去重：同一段多次推送时覆盖
          const i = aiSegs.value.findIndex((s) => s.key === k);
          if (i >= 0) aiSegs.value[i].text = text;
          else aiSegs.value.push({ key: k, label, text });
        },
        onWarning: (m) => { if (m.msg) aiWarn.value = m.msg; },
        onError: (m) => { aiError.value = m.msg; },
        onDone: () => { aiDone.value = true; aiRaw.value = ""; },
      });
  } catch (e) {
    aiError.value = e.message;
  } finally {
    aiStreaming.value = false;
  }
}

async function ask() {
  const q = chatQ.value.trim();
  if (!q || chatStreaming.value) return;
  chatQ.value = "";
  chatLog.value.push({ role: "user", content: q });
  chatStreaming.value = true;
  chatRaw.value = "";
  try {
    await postSSE(`/api/entry/${props.entryId}/chat`, { question: q }, {
      onChunk: (text) => { chatRaw.value += text; },
      onDone: () => {
        chatLog.value.push({ role: "assistant", content: chatRaw.value });
        chatRaw.value = "";
      },
      onError: (m) => {
        chatLog.value.push({ role: "assistant", content: "⚠ " + m.msg });
      },
    }, { signal: chatAbort.signal });
  } catch (e) {
    chatLog.value.push({ role: "assistant", content: "⚠ " + e.message });
  } finally {
    chatStreaming.value = false;
    // 滚到底
    requestAnimationFrame(() => {
      document.querySelector(".drawer-body")?.scrollTo(0, 1e9);
    });
  }
}

async function runDebate() {
  debateStreaming.value = true;
  debateError.value = "";
  debateDone.value = false;
  debateSegs.value = [
    { key: "bull", label: "🐂 看多研究员", text: "", streaming: true },
    { key: "bear", label: "🐻 看空研究员", text: "", streaming: false },
    { key: "judge", label: "⚖ 交易员裁决", text: "", streaming: false },
  ];
  try {
    const code = d.value.code;
    await postSSE(`/api/stock/${code}/debate`, null, {
      onProgress: (m) => {
        const order = ["bull", "bear", "judge"];
        const i = order.indexOf(m.stage);
        if (i > 0) debateSegs.value[i - 1].streaming = false;
        if (i >= 0) debateSegs.value[i].streaming = true;
      },
      onChunk: () => {},
      onDone: () => {
        debateSegs.value.forEach((s) => (s.streaming = false));
        debateDone.value = true;
      },
      onError: (m) => { debateError.value = m.msg; },
    }, { signal: debateAbort.signal });
    return;
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
            if (m.type === "stage") {
              const order = ["bull", "bear", "judge"];
              const i = order.indexOf(m.stage);
              if (i > 0) debateSegs.value[i - 1].streaming = false;
              debateSegs.value[i].streaming = true;
            } else if (m.type === "bull" || m.type === "bear" || m.type === "judge") {
              const seg = debateSegs.value.find((s) => s.key === m.type);
              if (seg) seg.text += m.text;
            } else if (m.type === "done") {
              debateSegs.value.forEach((s) => (s.streaming = false));
              debateDone.value = true;
            } else if (m.type === "error") debateError.value = m.msg;
          } catch {}
        }
      }
    }
  } catch (e) {
    debateError.value = e.message;
  } finally {
    debateStreaming.value = false;
    debateSegs.value.forEach((s) => (s.streaming = false));
  }
}

onMounted(async () => {
  try {
    d.value = await api.entry(props.entryId);
  } catch (e) {
    d.value = null;
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  // M2: 离页取消所有进行中的流式请求
  aiAbort.abort();
  chatAbort.abort();
  debateAbort.abort();
});
</script>
