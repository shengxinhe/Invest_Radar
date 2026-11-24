<template>
  <div class="app">
    <!-- 断网横幅 -->
    <div v-if="offline" class="offline-bar" @click="onOnline">
      当前离线 · 点此重新连接
    </div>

    <!-- 玻璃顶栏 -->
    <header class="glass-header">
      <div class="gh-inner">
        <div v-if="tab === 'home'" class="gh-brand">
          <span class="pulse" :class="{ risk: pulse.risk > 0 }"></span>
          <span class="gh-title">投资雷达</span>
        </div>
        <button v-else-if="tab === 'quote' && stockCode" class="gh-back" @click="stockCode=''; quoteMode='feed'">‹</button>
        <div v-else class="gh-brand" style="gap:6px">
          <span class="pulse" :class="{ risk: pulse.risk > 0 }"></span>
          <span class="gh-title">投资雷达</span>
        </div>

        <div class="search-box" v-if="tab === 'quote' || tab === 'watch'">
          <span class="gh-icon">🔍</span>
          <input v-model="q" placeholder="代码 / 名称 / 拼音"
                 @input="onSearchInput" @focus="showDD = true" />
          <button v-if="q" class="gh-clear" @click="clearSearch">×</button>
        </div>
        <div v-else class="gh-title2">{{ pageTitle }}</div>

        <button v-if="tab === 'ai'" class="gh-refresh" @click="genDaily">✨</button>
      </div>

      <!-- 搜索下拉 -->
      <div v-if="showDD && q && results.length" class="dropdown">
        <div v-for="r in results" :key="r.code" class="dd-item"
             @click="goStock(r.code)">
          <div>
            <div class="dd-name">{{ r.name }}</div>
            <div class="dd-code num">{{ r.code }} · {{ r.industry || "—" }}</div>
          </div>
          <span style="color:var(--text-2)">›</span>
        </div>
      </div>
      <div v-else-if="showDD && q && !results.length && !searching" class="dropdown">
        <div class="dd-empty">没找到「{{ q }}」</div>
      </div>
    </header>

    <!-- ============ 首页（投资驾驶舱） ============ -->
    <main class="main" v-show="tab === 'home'">
      <PulseBar :risk="pulse.risk" :positive="pulse.positive" :queued="pulse.queued" />

      <MarketOverview @open="openEntry" />

      <div class="section-label">我的关注</div>
      <WatchStrip :list="watchList" @select="goStock" @add="tab = 'watch'" />

      <TodayFocus />

      <div class="section-label" style="display:flex;justify-content:space-between;align-items:center">
        <span>最新资讯</span>
        <button class="see-all" @click="tab = 'quote'">全部 ›</button>
      </div>
      <FeedList @open="openEntry" @ai="quickAI" />

      <div class="ai-note">AI 生成内容仅供研究参考，不构成投资建议</div>
    </main>

    <!-- ============ 行情（搜索 + feed + 详情） ============ -->
    <main class="main" v-show="tab === 'quote'" style="padding-bottom:100px">
      <template v-if="!stockCode">
        <FeedList v-if="quoteMode === 'feed'" @open="openEntry" @ai="quickAI" />
      </template>
      <StockView
        v-else
        :code="stockCode"
        :key="stockCode"
        @open-entry="openEntry"
        @add-watch="loadWatch"
        @back="stockCode = ''; quoteMode = 'feed'"
      />
    </main>

    <!-- ============ 自选 ============ -->
    <main class="main" v-show="tab === 'watch'" style="padding-bottom:100px">
      <div v-if="!watchList.length" class="empty">
        还没有关注任何股票<br />上方搜索框输入代码添加
      </div>
      <template v-else>
        <div v-for="w in watchList" :key="w.code" class="watch-item"
             @click="goStock(w.code)">
          <div class="wi-left">
            <div class="wi-name">
              {{ w.name }} <span class="wi-code num">{{ w.code }}</span>
              <span v-if="w.role" class="tag t-n">{{ w.role }}</span>
            </div>
            <div class="wi-thesis">{{ w.thesis || "未写投资逻辑" }}</div>
            <div class="wi-edit" @click.stop="editThesis(w)">✎ 改逻辑</div>
          </div>
          <div class="wi-right">
            <div class="wi-price num" :class="pctCls(w.pct)">{{ w.price ?? "—" }}</div>
            <div class="wi-pct num" :class="pctCls(w.pct)">{{ fmtPct(w.pct) }}</div>
          </div>
        </div>
      </template>
    </main>

    <!-- ============ AI ============ -->
    <main class="main" v-show="tab === 'ai'" style="padding-bottom:130px">
      <div class="card ai-hero" style="padding:12px 14px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div style="font-size:14px;font-weight:600">AI 助手 <span style="color:var(--accent);font-size:11px;margin-left:6px">RAG 已接入</span></div>
          <button class="see-all" @click="genDaily" :disabled="dailyStreaming">
            {{ dailyStreaming ? "生成中…" : "✨ 晨报" }}
          </button>
        </div>
        <div v-if="dailyText && !dailyStreaming" class="daily-box" style="margin-top:10px">{{ dailyText }}</div>
      </div>

      <GlobalAI />

      <!-- M6 研究工作台 -->
      <div class="section-label" style="margin-top:16px">研究工作台</div>
      <ResearchView />

      <div class="card" style="margin-top:16px">
        <div class="card-title">用量与成本</div>
        <div v-if="usage" class="grid" style="grid-template-columns:repeat(3,1fr)">
          <div class="metric">
            <div class="k">解读缓存</div>
            <div class="v num">{{ usage.cached_interpretations }}</div>
          </div>
          <div class="metric">
            <div class="k">对话轮次</div>
            <div class="v num">{{ usage.chat_rounds }}</div>
          </div>
          <div class="metric">
            <div class="k">本月估算</div>
            <div class="v num" style="color:var(--accent)">¥{{ usage.est_cost_cny }}</div>
          </div>
        </div>
        <div v-else class="loading" style="padding:14px"><div class="spinner"></div></div>
        <div class="ai-note" style="margin-top:8px">{{ usage?.note }}</div>
      </div>
    </main>

    <!-- ============ 我的设置 ============ -->
    <main class="main" v-show="tab === 'me'">
      <Settings />
    </main>

    <!-- 词条详情抽屉 -->
    <Drawer v-if="entryId" :entry-id="entryId" @close="entryId = null" />
    <!-- 快速 AI 结果抽屉 -->
    <QuickAI v-if="quickAIItem" :item="quickAIItem" @close="quickAIItem = null" />

    <!-- 液态玻璃导航 -->
    <GlassNav v-model="tab" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import GlassNav from "./components/GlassNav.vue";
import PulseBar from "./components/PulseBar.vue";
import WatchStrip from "./components/WatchStrip.vue";
import FeedList from "./components/FeedList.vue";
import FeedCard from "./components/FeedCard.vue";
import StockView from "./components/StockView.vue";
import Drawer from "./components/Drawer.vue";
import QuickAI from "./components/QuickAI.vue";
import GlobalAI from "./components/GlobalAI.vue";
import ResearchView from "./components/ResearchView.vue";
import MarketOverview from "./components/MarketOverview.vue";
import TodayFocus from "./components/TodayFocus.vue";
import Settings from "./components/Settings.vue";
import { api, req as rawReq, pctCls, fmtPct } from "./api.js";
import { API_BASE, IS_NATIVE } from "./env.js";
import { useSearch } from "./composables/useSearch.js";
import { useQuoteStream } from "./composables/useQuoteStream.js";

const offline = ref(false);

// M5: 共享行情流（生命周期由 composable 管理）
const { status: streamStatus } = useQuoteStream((m) => {
  const w = watchList.value.find((x) => x.code === m.code);
  if (w) {
    w.price = m.price;
    w.pct = m.pct;
    w.pe = m.pe;
    w.pb = m.pb;
  }
});

// M3: 搜索竞态保护
const {
  q, results, searching, error: searchError, onInput: onSearchInput, reset: resetSearch,
} = useSearch((kw, signal) =>
  fetch(`${API_BASE}/api/search?q=${encodeURIComponent(kw)}`, {
    credentials: "include", signal,
  }).then((r) => (r.ok ? r.json() : { data: [] })).then((j) => j.data || [])
);

const tab = ref("home");
const stockCode = ref("");
const quoteMode = ref("feed");
const entryId = ref(null);
const quickAIItem = ref(null);

const showDD = ref(false);
const watchList = ref([]);
const pulse = ref({ risk: 0, positive: 0, queued: 0 });

const dailyText = ref("");
const dailyStreaming = ref(false);
const usage = ref(null);

async function editThesis(w) {
  const t = prompt(`修改 ${w.name} 的投资逻辑（thesis）：`, w.thesis || "");
  if (t === null) return;
  try {
    await rawReq(`/api/watch/${w.code}/thesis`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: w.code, thesis: t }),
    });
    loadWatch();
  } catch (e) { alert("保存失败: " + e.message); }
}

async function loadUsage() {
  try { usage.value = await rawReq("/api/ai/usage"); } catch {}
}

const pageTitle = computed(() => {
  if (tab.value === "me") return "我的";
  if (tab.value === "ai") return "AI 助手";
  if (stockCode.value) return "个股详情";
  return "行情";
});

async function loadWatch() {
  try { watchList.value = await api.watch(); } catch {}
}
async function loadPulse() {
  try { pulse.value = await api.pulse(); } catch {}
}

function clearSearch() {
  resetSearch();
  showDD.value = false;
}

function goStock(code) {
  stockCode.value = code;
  tab.value = "quote";
  quoteMode.value = "stock";
  showDD.value = false;
  q.value = ""; results.value = [];
}
function goHome() {
  if (stockCode.value) { stockCode.value = ""; }
  else { tab.value = "home"; }
  loadWatch();
}
function openEntry(id) { entryId.value = id; }
function quickAI(item) { quickAIItem.value = item; }

async function genDaily() {
  if (dailyStreaming.value) return;
  dailyStreaming.value = true;
  dailyText.value = "";
  try {
    const res = await fetch(`${API_BASE}/api/ai/daily-brief`, { method: "POST" });
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
            if (m.type === "chunk") dailyText.value += m.text;
          } catch {}
        }
      }
    }
  } catch (e) {
    dailyText.value = "⚠ " + e.message;
  } finally {
    dailyStreaming.value = false;
  }
}

function onDocClick(e) {
  if (!e.target.closest(".search-box") && !e.target.closest(".dropdown")) showDD.value = false;
}

onMounted(() => {
  loadWatch();
  loadPulse();
  loadUsage();

  // 断网检测（Capacitor WebView 也支持这两个事件）
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  offline.value = typeof navigator !== "undefined" && navigator.onLine === false;

  document.addEventListener("click", onDocClick);
});
function onOffline() { offline.value = true; }
function onOnline() {
  offline.value = false;
  // 恢复网络后补一次数据
  loadWatch();
  loadPulse();
}
onUnmounted(() => {
  document.removeEventListener("click", onDocClick);
  window.removeEventListener("online", onOnline);
  window.removeEventListener("offline", onOffline);
});
</script>

<style>
/* 顶栏玻璃（全局 2 处 backdrop-filter 之一） */
.offline-bar{position:sticky;top:0;z-index:120;background:rgba(239,68,68,.92);color:#fff;font-size:12.5px;text-align:center;padding:7px 12px;cursor:pointer;}.glass-header{
  position:sticky;top:0;z-index:90;
  background:rgba(8,9,15,.72);
  -webkit-backdrop-filter:blur(24px) saturate(160%);
  backdrop-filter:blur(24px) saturate(160%);
  border-bottom:1px solid rgba(255,255,255,.08);
}
.gh-inner{display:flex;align-items:center;gap:10px;padding:calc(10px + var(--safe-top)*0) 14px 10px}
.gh-brand{display:flex;align-items:center;gap:8px;flex-shrink:0}
.gh-title{font-size:15px;font-weight:600;white-space:nowrap}
.gh-title2{flex:1;font-size:14px;font-weight:600}
.gh-back{width:30px;height:30px;border-radius:10px;font-size:18px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  background:var(--card-bg);border:1px solid var(--card-border)}
.gh-icon{color:var(--text-2);font-size:13px}
.gh-clear{width:18px;height:18px;border-radius:50%;background:rgba(255,255,255,.12);
  font-size:12px;display:flex;align-items:center;justify-content:center}
.gh-refresh{width:32px;height:32px;border-radius:10px;flex-shrink:0;
  background:rgba(94,234,212,.1);border:1px solid rgba(94,234,212,.3);
  color:var(--accent);font-size:15px}
.gh-refresh:active{opacity:.6}
.pulse{
  width:8px;height:8px;border-radius:50%;
  background:var(--accent);box-shadow:0 0 10px var(--accent);
  animation:breathe 2.4s ease-in-out infinite;
}
.pulse.risk{background:var(--down);box-shadow:0 0 10px var(--down);animation-duration:1s}
@keyframes breathe{50%{transform:scale(.6);opacity:.5}}

/* 下拉 */
.dropdown{
  position:absolute;top:100%;left:14px;right:14px;margin-top:4px;
  background:#14161f;border:1px solid var(--line);border-radius:12px;
  max-height:50vh;overflow-y:auto;z-index:95;
  box-shadow:0 12px 32px rgba(0,0,0,.6);
}
.dd-item{padding:11px 13px;border-bottom:1px solid rgba(255,255,255,.05);
  display:flex;justify-content:space-between;align-items:center;gap:8px}
.dd-item:active{background:var(--panel2)}
.dd-item:last-child{border-bottom:none}
.dd-name{font-weight:500;font-size:13.5px}
.dd-code{color:var(--text-2);font-size:11px}
.dd-empty{padding:16px;text-align:center;color:var(--text-2);font-size:13px}

/* 卡片基座（半透明实底，不叠 blur） */
.card{
  background:var(--card-bg);border:1px solid var(--card-border);
  border-radius:16px;padding:16px;margin-bottom:12px;
}
.section-label{
  font-size:12px;font-weight:600;color:var(--text-2);
  letter-spacing:.5px;margin:4px 0 10px;
}
.see-all{color:var(--accent);font-size:12px}
.see-all:active{opacity:.6}

/* watch-item（沿用但换主题变量） */
.watch-item{
  display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px;
  padding:13px;background:var(--card-bg);border:1px solid var(--card-border);
  border-radius:14px;margin-bottom:10px;
}
.watch-item:active{transform:scale(.985);background:rgba(255,255,255,.06)}
.wi-left{min-width:0;overflow:hidden}
.wi-name{font-size:14.5px;font-weight:600;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.wi-code{color:var(--text-2);font-size:11px;font-weight:400}
.wi-thesis{color:var(--text-2);font-size:12px;margin-top:4px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.wi-edit{
  display:inline-block;margin-top:6px;font-size:11px;color:var(--accent);
  border:1px solid rgba(94,234,212,.3);border-radius:8px;padding:2px 8px;
  background:rgba(94,234,212,.08);
}
.wi-edit:active{opacity:.6}
.wi-right{text-align:right;white-space:nowrap}
.wi-price{font-size:17px;font-weight:600}
.wi-pct{font-size:12px}

/* AI hero */
.ai-hero{border-color:rgba(94,234,212,.22)}
.daily-box{
  background:rgba(94,234,212,.05);border:1px solid rgba(94,234,212,.18);
  border-radius:12px;padding:14px;
  white-space:pre-wrap;font-size:13px;line-height:1.8;
}

/* tag / loading / empty（全局沿用） */
.tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px}
.t-n{background:rgba(255,255,255,.08);color:var(--text-2)}
.t-risk{background:rgba(255,92,122,.16);color:var(--down)}
.t-good{background:rgba(61,220,151,.16);color:var(--up)}
.loading{text-align:center;padding:30px;color:var(--text-2);font-size:13px}
.spinner{width:18px;height:18px;border:2px solid var(--line);border-top-color:var(--accent);
  border-radius:50%;animation:spin .7s linear infinite;margin:0 auto 8px}
@keyframes spin{to{transform:rotate(360deg)}}
.empty{text-align:center;padding:36px 20px;color:var(--text-2);font-size:13px;line-height:1.8}
.ai-note{color:#5b6373;font-size:11px;margin-top:10px;text-align:center;line-height:1.6}
</style>
