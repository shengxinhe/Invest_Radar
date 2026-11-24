<template>
  <div>
    <div v-if="loading" class="loading">
      <div class="spinner"></div>
      加载行情…
    </div>

    <template v-else>
      <!-- ===== 区1 公司概览 ===== -->
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px">
          <div style="min-width: 0">
            <div style="font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 8px">
              {{ info.name }}
              <span class="wi-code">{{ code }}</span>
              <span v-if="info.in_watch" class="tag t-n">{{ info.watch?.role || "已关注" }}</span>
            </div>
            <div style="color: var(--text-2); font-size: 11.5px; margin-top: 4px">
              {{ info.industry || "行业未收录" }} · {{ marketLabel }}
            </div>
            <!-- 数据新鲜度（含各源状态） -->
            <div v-if="info.freshness" class="fresh-tag" :data-st="info.freshness.status">
              <span class="fresh-dot"></span>
              行情 {{ info.freshness.at || "—" }}
              <span v-if="info.freshness.status === 'stale'">（已过期）</span>
              <span v-else-if="info.freshness.status === 'delayed'">（延迟）</span>
              <span v-else-if="info.freshness.status === 'missing'">（无数据）</span>
            </div>
            <div v-if="info.sources" class="src-row">
              <span v-for="(v, k) in info.sources" :key="k" class="src-item" :data-st="v">
                {{ srcLabel(k) }}<i></i>
              </span>
            </div>
          </div>
          <div style="text-align: right; flex-shrink: 0">
            <div style="font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums"
                 :class="pctCls(info.quote?.pct)">
              {{ info.quote?.price ?? "—" }}
            </div>
            <div style="font-size: 13px; font-variant-numeric: tabular-nums"
                 :class="pctCls(info.quote?.pct)">
              {{ fmtPct(info.quote?.pct) }}
            </div>
          </div>
        </div>

        <div class="grid" style="margin-top: 14px">
          <div class="metric">
            <div class="k">市值</div>
            <div class="v">{{ info.quote?.mcap_yi ? info.quote.mcap_yi.toFixed(0) + "亿" : "—" }}</div>
          </div>
          <div class="metric">
            <div class="k">PE(TTM)</div>
            <div class="v">{{ info.quote?.pe_ttm ? info.quote.pe_ttm.toFixed(1) : "—" }}</div>
          </div>
          <div class="metric">
            <div class="k">PB</div>
            <div class="v">{{ info.quote?.pb ? info.quote.pb.toFixed(2) : "—" }}</div>
          </div>
        </div>

        <div v-if="info.trend" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-1)">
          <div style="font-size: 13px; font-weight: 500; margin-bottom: 6px">
            {{ info.trend.verdict }}
          </div>
          <div style="color: var(--text-2); font-size: 12px; line-height: 1.7">
            <div v-for="(p, i) in info.trend.points" :key="i">· {{ p }}</div>
          </div>
        </div>
      </div>

      <!-- 未关注 → 添加 -->
      <div v-if="!info.in_watch" class="card">
        <div style="font-size: 13px; margin-bottom: 10px">还没关注这只票</div>
        <input
          v-model="thesis"
          placeholder="写一句投资逻辑（这票靠什么赚钱？）"
          style="width: 100%; background: var(--panel2); border: 1px solid var(--line);
                 border-radius: 8px; padding: 9px 11px; outline: none; margin-bottom: 8px"
        />
        <div style="display: flex; gap: 8px">
          <button class="btn btn-primary" @click="addWatch">加入关注池</button>
          <button class="btn" @click="sync">抓取全部数据</button>
        </div>
      </div>

      <!-- 已关注 → 刷新 -->
      <div v-else style="display: flex; gap: 8px; margin-bottom: 10px">
        <button class="btn btn-sm" @click="sync" :disabled="syncing">
          {{ syncing ? "抓取中…" : "刷新数据" }}
        </button>
        <button class="btn btn-sm" @click="removeWatch">取消关注</button>
      </div>

      <!-- Tabs -->
      <div class="tabs">
        <div
          v-for="t in tabList"
          :key="t.key"
          class="tab"
          :class="{ active: curTab === t.key }"
          @click="switchTab(t.key)"
        >
          {{ t.label }}<span v-if="t.n" style="opacity: 0.55"> {{ t.n }}</span>
        </div>
      </div>

      <!-- 走势 -->
      <div v-if="curTab === 'chart'" class="card" style="padding:12px 8px 8px">
        <KLinePanel :code="code" />
      </div>

      <!-- 概览 -->
      <div v-else-if="curTab === 'overview'" class="card">
        <div class="card-title">估值</div>
        <div style="color: var(--dim); font-size: 13px; line-height: 1.8">
          <div v-for="(v, i) in info.valuation" :key="i">· {{ v }}</div>
          <div v-if="!info.valuation?.length">暂无</div>
        </div>
      </div>

      <!-- 词条列表（含状态管理） -->
      <div v-else-if="['notice', 'news', 'qa', 'report'].includes(curTab)" class="card">
        <div style="display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap">
          <button
            v-for="f in filters"
            :key="f.key"
            class="btn btn-sm"
            :class="{ 'btn-primary': filter === f.key }"
            @click="setFilter(f.key)"
          >
            {{ f.label }}
          </button>
          <button
            v-for="s in statusFilters"
            :key="s.key"
            class="btn btn-sm"
            :class="{ 'btn-primary': statusFilter === s.key }"
            @click="setStatusFilter(s.key)"
          >
            {{ s.label }}
          </button>
        </div>

        <div v-if="entriesLoading" class="loading"><div class="spinner"></div>加载中…</div>
        <div v-else-if="!entries.length && !(curTab === 'news' && marketNews.length)" class="empty">
          {{ emptyText }}
        </div>
        <template v-else>
          <!-- 多选操作条 -->
          <div v-if="selected.length" style="display:flex;gap:8px;align-items:center;
               padding:8px 0;margin-bottom:4px;position:sticky;top:0;background:var(--panel);z-index:5">
            <span style="color:var(--dim);font-size:12px">已选 {{ selected.length }}</span>
            <button class="btn btn-primary btn-sm" @click="batchAsk" :disabled="batchStreaming">
              {{ batchStreaming ? "AI 分析中…" : "⚡ 一起问 AI" }}
            </button>
            <button class="btn btn-sm" @click="selected = []">取消</button>
          </div>
          <div v-if="batchResult" class="card" style="background:#1a2233;border-color:#2a3a55">
            <div class="card-title">AI 批量点评（{{ batchCount }} 条）</div>
            <div style="white-space:pre-wrap;font-size:13px;line-height:1.75">{{ batchResult }}</div>
            <div class="ai-note">AI 生成，非投资建议；以原始公告为准</div>
          </div>

          <div v-for="e in entries" :key="e.id" class="entry" style="gap:8px"
               :class="{ 'is-read': e.is_read }">
            <input
              type="checkbox"
              :checked="selected.includes(e.id)"
              @change="toggleSel(e.id)"
              style="width:16px;height:16px;accent-color:#5EEAD4;margin-top:5px;flex-shrink:0"
            />
            <div class="entry-dot" :style="{ background: levelDot(e.level) }"></div>
            <div class="entry-body" @click="$emit('open-entry', e.id)">
              <div class="entry-title">{{ e.title }}</div>
              <div class="entry-meta">
                <span>{{ e.date }}</span>
                <span v-if="e.type === 'report'">研报</span>
                <span v-if="e.status && e.status !== 'unread'" class="st-chip" :data-st="e.status">
                  {{ statusLabel(e.status) }}
                </span>
              </div>
            </div>
            <!-- 状态快捷切换 -->
            <button class="st-quick" @click.stop="cycleStatus(e)" :title="'当前：' + statusLabel(e.status)">
              {{ statusIcon(e.status) }}
            </button>
          </div>
        </template>

        <!-- 新闻页：补市场快讯 -->
        <template v-if="curTab === 'news'">
          <div v-if="!entries.length" style="color: var(--dim); font-size: 12px;
               padding: 10px 0 14px; line-height: 1.7; border-bottom: 1px solid var(--line)">
            该股近期没有命中个股新闻。<br />
            东财个股新闻接口已下线，现在从全市场快讯里按名称/代码过滤，命中率有限。
          </div>
          <template v-if="marketNews.length">
            <div style="color: var(--dim); font-size: 11px; margin: 14px 0 6px">
              市场快讯（大盘背景）
            </div>
            <div v-for="(m, i) in marketNews" :key="'m' + i" class="entry"
                 @click="openUrl(m.url)">
              <div class="entry-dot" style="background: #374151"></div>
              <div class="entry-body">
                <div class="entry-title">{{ m.title }}</div>
                <div class="entry-meta"><span>{{ m.date }}</span></div>
              </div>
            </div>
          </template>
        </template>
      </div>

      <!-- ===== 区5 投资逻辑 ===== -->
      <div v-else-if="curTab === 'thesis'" class="card">
        <div class="card-title">当前 Thesis（第 {{ thesisVer }} 版）</div>
        <div v-if="info.watch?.thesis" class="detail-content" style="margin-bottom:12px">
          {{ info.watch.thesis }}
        </div>
        <div v-else class="empty" style="padding:16px">尚未设定投资逻辑</div>

        <div style="display:flex;gap:8px;margin-bottom:14px">
          <button class="btn btn-primary btn-sm" @click="editThesis">编辑逻辑</button>
          <button class="btn btn-sm" @click="loadThesisHistory">刷新历史</button>
          <button class="btn btn-sm" @click="genReview" :disabled="reviewing">
            {{ reviewing ? "生成中…" : "月度复盘" }}
          </button>
        </div>

        <!-- 复盘结果 -->
        <div v-if="reviewText" class="daily-box" style="margin-bottom:14px;white-space:pre-wrap">
          {{ reviewText }}
          <div class="ai-note">已归档到 AI 报告</div>
        </div>

        <div class="card-title">历史版本</div>
        <div v-if="!thesisHistory.length" class="empty" style="padding:16px">
          暂无修改记录
        </div>
        <div v-for="h in thesisHistory" :key="h.id" class="th-item">
          <div class="th-head">
            <span>{{ fmtTs(h.changed_at) }}</span>
            <span v-if="h.reason" class="th-reason">{{ h.reason }}</span>
          </div>
          <div class="th-diff">
            <div class="th-old">− {{ h.thesis_old || "（空）" }}</div>
            <div class="th-new">+ {{ h.thesis_new || "（空）" }}</div>
          </div>
        </div>
      </div>

      <!-- 筹码 -->
      <template v-else-if="curTab === 'chip'">
        <div v-if="chipLoading" class="loading"><div class="spinner"></div>加载中…</div>
        <template v-else>
          <div v-if="chip.holders?.length" class="card">
            <div class="card-title">股东户数（筹码集中度）</div>
            <div class="grid-2">
              <div class="metric">
                <div class="k">户数</div>
                <div class="v">{{ Number(chip.holders[0].num).toLocaleString() }}</div>
              </div>
              <div class="metric">
                <div class="k">环比</div>
                <div class="v" :class="chip.holders[0].ratio > 0 ? 'up' : 'down'">
                  {{ chip.holders[0].ratio > 0 ? "+" : "" }}{{ Number(chip.holders[0].ratio).toFixed(2) }}%
                </div>
              </div>
            </div>
            <div style="color: var(--dim); font-size: 11px; margin-top: 10px">
              户数减少 = 筹码集中（偏多）；增加 = 分散
            </div>
          </div>

          <div v-if="chip.margin?.length" class="card">
            <div class="card-title">融资融券</div>
            <table style="width: 100%; font-size: 12.5px">
              <tr style="color: var(--dim); text-align: left">
                <th style="padding: 4px 0; font-weight: 400">日期</th>
                <th style="font-weight: 400">融资余额</th>
                <th style="font-weight: 400">净买入</th>
              </tr>
              <tr v-for="m in chip.margin.slice(0, 5)" :key="m.date">
                <td style="padding: 5px 0; color: var(--dim)">{{ m.date }}</td>
                <td>{{ fmtMoney(m.rzye) }}</td>
                <td :class="m.rzjme > 0 ? 'up' : 'down'">{{ fmtMoney(m.rzjme) }}</td>
              </tr>
            </table>
          </div>

          <div v-if="chip.lockup?.length" class="card">
            <div class="card-title">限售解禁</div>
            <div v-for="x in chip.lockup" :key="x.date" style="padding: 6px 0; font-size: 12.5px; display: flex; justify-content: space-between">
              <span>{{ x.date }}</span>
              <span style="color: var(--dim)">{{ fmtShares(x.shares) }} / {{ x.ratio }}%</span>
              <span v-if="x.future" class="tag t-risk">待解禁</span>
              <span v-else class="tag t-n">已过</span>
            </div>
          </div>

          <div v-if="chip.lhb?.length" class="card">
            <div class="card-title">龙虎榜</div>
            <div v-for="(x, i) in chip.lhb.slice(0, 5)" :key="i" style="padding: 6px 0; font-size: 12.5px">
              <div style="display: flex; justify-content: space-between">
                <span>{{ x.date }}</span>
                <span :class="x.net > 0 ? 'up' : 'down'">{{ fmtMoney(x.net) }}</span>
              </div>
              <div style="color: var(--dim); font-size: 11px; margin-top: 2px">{{ x.reason }}</div>
            </div>
          </div>

          <div v-if="!chip.holders?.length && !chip.margin?.length && !chip.lockup?.length" class="empty">
            暂无筹码数据
          </div>
        </template>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from "vue";
import { api, pctCls, fmtPct, fmtMoney, fmtShares, levelDot } from "../api.js";
import { postSSE } from "../sse.js";
import KLinePanel from "./kline/KLinePanel.vue";

const props = defineProps({ code: String });
const emit = defineEmits(["open-entry", "add-watch", "back"]);

const info = ref({});
const loading = ref(true);
const syncing = ref(false);
const thesis = ref("");
const curTab = ref("overview");

const entries = ref([]);
const entriesLoading = ref(false);
const filter = ref("all");

const chip = ref({});
const chipLoading = ref(false);

const kline = ref([]);
const cv = ref(null);
const ma20 = ref("—");
const ma60 = ref("—");

const marketNews = ref([]);

// 多选批量
const selected = ref([]);
const batchResult = ref("");
const batchStreaming = ref(false);
const batchCount = ref(0);

function toggleSel(id) {
  const i = selected.value.indexOf(id);
  if (i >= 0) selected.value.splice(i, 1);
  else selected.value.push(id);
}

async function readSSE(res, onData) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (!line.startsWith("data:")) continue;
        try { onData(JSON.parse(line.slice(5))); } catch {}
      }
    }
  }
}

async function batchAsk() {
  if (!selected.value.length) return;
  batchStreaming.value = true;
  batchResult.value = "";
  batchCount.value = selected.value.length;
  try {
    const res = await fetch("/api/ai/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entry_ids: selected.value }),
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    await readSSE(res, (m) => {
      if (m.type === "chunk") batchResult.value += m.text;
      else if (m.type === "error") batchResult.value += "\n⚠ " + m.msg;
    });
  } catch (e) {
    batchResult.value = "⚠ " + e.message;
  } finally {
    batchStreaming.value = false;
  }
}

const counts = ref({});

const tabList = computed(() => [
  { key: "overview", label: "概览" },
  { key: "chart", label: "走势" },
  { key: "notice", label: "公告", n: counts.value.notice },
  { key: "news", label: "新闻", n: counts.value.news },
  { key: "report", label: "研报", n: counts.value.report },
  { key: "qa", label: "互动", n: counts.value.qa },
  { key: "chip", label: "筹码" },
  { key: "thesis", label: "逻辑" },
]);

const filters = [
  { key: "all", label: "全部" },
  { key: "risk", label: "风险" },
  { key: "positive", label: "利好" },
];

const statusFilters = [
  { key: "", label: "不限状态" },
  { key: "pending", label: "待核查" },
  { key: "saved", label: "稍后" },
  { key: "processed", label: "已处理" },
];
const statusFilter = ref("");

const STATUS_LABEL = {
  unread: "未读", reading: "研究中", pending: "待核查",
  processed: "已处理", ignored: "已忽略", saved: "稍后研究",
};
const STATUS_ICON = {
  unread: "○", reading: "◐", pending: "⚑",
  processed: "✓", ignored: "✕", saved: "★",
};
const CYCLE = ["unread", "pending", "saved", "processed", "ignored"];

const marketLabel = computed(() => {
  const c = props.code || "";
  return c.startsWith("6") ? "沪市" : c.startsWith(("4" || "8")) ? "北交所" : "深市";
});

function srcLabel(k) {
  return { quote: "行情", notice: "公告", news: "新闻", kline: "K线" }[k] || k;
}
function statusLabel(s) { return STATUS_LABEL[s || "unread"] || "未读"; }
function statusIcon(s) { return STATUS_ICON[s || "unread"] || "○"; }

async function cycleStatus(e) {
  const i = CYCLE.indexOf(e.status || "unread");
  const next = CYCLE[(i + 1) % CYCLE.length];
  e.status = next;
  e.is_read = next !== "unread" ? 1 : 0;
  try {
    await api.setEntryState(e.id, { status: next, is_read: next !== "unread" });
  } catch {
    /* 失败静默，UI 已乐观更新 */
  }
}

function setStatusFilter(k) {
  statusFilter.value = k;
  loadEntries();
}

const emptyText = computed(() => {
  const m = {
    notice: "近期无公告",
    news: "近期无个股新闻\n小盘股新闻少是常态，看公告和互动更有效",
    qa: "暂无投资者问答",
    report: "暂无机构研报",
  };
  return m[curTab.value] || "暂无数据";
});

async function load() {
  loading.value = true;
  try {
    info.value = await api.stock(props.code);
  } catch (e) {
    info.value = { name: props.code, quote: null };
  } finally {
    loading.value = false;
  }
  loadCounts();
}

async function loadCounts() {
  const out = {};
  for (const t of ["notice", "news", "report", "qa"]) {
    try {
      const r = await api.entries(props.code, t, t === "report" ? 3650 : 30);
      out[t] = r.length;
    } catch {
      out[t] = 0;
    }
  }
  counts.value = out;
}

async function switchTab(k) {
  curTab.value = k;
  if (k === "chart" && !kline.value.length) await loadChart();
  if (["notice", "news", "qa", "report"].includes(k)) await loadEntries();
  if (k === "news" && !marketNews.value.length) await loadMarket();
  if (k === "chart") nextTick(draw);
  if (k === "chip" && !chip.value.holders) await loadChip();
  if (k === "thesis" && !thesisHistory.value.length) await loadThesisHistory();
}

const thesisHistory = ref([]);
const thesisVer = ref(1);

async function loadThesisHistory() {
  try {
    thesisHistory.value = await api.thesisHistory(props.code);
    thesisVer.value = thesisHistory.value.length + 1;
  } catch {
    thesisHistory.value = [];
  }
}

function fmtTs(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

async function editThesis() {
  const old = info.value.watch?.thesis || "";
  const t = prompt("修改投资逻辑（thesis）：", old);
  if (t === null) return;
  const reason = prompt("修改原因（可留空）：", "") || "";
  try {
    const r = await api.updateThesis(props.code, { thesis: t, reason });
    thesisVer.value = r.thesis_version || thesisVer.value + 1;
    await load();
    await loadThesisHistory();
  } catch (e) {
    alert("保存失败: " + e.message);
  }
}

// M7: 个股月度复盘
const reviewing = ref(false);
const reviewText = ref("");

async function genReview() {
  reviewing.value = true;
  reviewText.value = "";
  const period = new Date().toISOString().slice(0, 7);
  await postSSE("/api/ai/monthly-review", { code: props.code, period }, {
    onChunk: (t) => { reviewText.value += t; },
    onError: (m) => { reviewText.value = "⚠ " + m.msg; },
  }, { timeoutMs: 240000 });
  reviewing.value = false;
}

async function loadMarket() {
  try {
    const r = await api.market();
    marketNews.value = r.slice(0, 30);
  } catch {
    marketNews.value = [];
  }
}

function openUrl(u) {
  if (u) window.open(u, "_blank", "noopener");
}

async function loadEntries() {
  entriesLoading.value = true;
  try {
    const t = curTab.value;
    const days = t === "report" ? 3650 : 30;
    const lv = filter.value === "all" ? "" : filter.value;
    const st = statusFilter.value || "";
    let rows = await api.entries(props.code, t, days, lv);
    if (st) rows = rows.filter((x) => (x.status || "unread") === st);
    entries.value = rows;
  } catch {
    entries.value = [];
  } finally {
    entriesLoading.value = false;
  }
}

function setFilter(f) {
  filter.value = f;
  loadEntries();
}

async function loadChart() {
  try {
    kline.value = await api.chart(props.code, 120);
  } catch {
    kline.value = [];
  }
}

async function loadChip() {
  chipLoading.value = true;
  try {
    chip.value = await api.extras(props.code);
  } catch {
    chip.value = {};
  } finally {
    chipLoading.value = false;
  }
}

async function sync() {
  syncing.value = true;
  try {
    await api.syncStock(props.code);
    await load();
    if (["notice", "news", "qa", "report"].includes(curTab.value)) await loadEntries();
  } catch (e) {
    alert("抓取失败: " + e.message);
  } finally {
    syncing.value = false;
  }
}

async function addWatch() {
  try {
    await api.addWatch({ code: props.code, thesis: thesis.value || "" });
    await load();
    emit("add-watch");
  } catch (e) {
    alert("添加失败: " + e.message);
  }
}

async function removeWatch() {
  if (!confirm("确定取消关注？")) return;
  try {
    await api.delWatch(props.code);
    await load();
    emit("add-watch");
  } catch (e) {
    alert("失败: " + e.message);
  }
}

/* ---------- 画图 ---------- */
function draw() {
  const c = cv.value;
  if (!c || !kline.value.length) return;
  const dpr = window.devicePixelRatio || 1;
  const W = c.clientWidth, H = c.clientHeight;
  if (!W || !H) return;
  c.width = W * dpr;
  c.height = H * dpr;
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const k = kline.value;
  const pad = { l: 6, r: 44, t: 8, b: 18 };
  const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;

  const closes = k.map((x) => x.c);
  let min = Math.min(...k.map((x) => x.l));
  let max = Math.max(...k.map((x) => x.h));
  const py = (max - min) * 0.06 || 0.1;
  min -= py;
  max += py;

  const X = (i) => pad.l + (i / (k.length - 1 || 1)) * cw;
  const Y = (v) => pad.t + (1 - (v - min) / (max - min || 1)) * ch;

  // 网格
  ctx.strokeStyle = "#232833";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = pad.t + (ch * i) / 3;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(pad.l + cw, y);
    ctx.stroke();
    const v = max - ((max - min) * i) / 3;
    ctx.fillStyle = "#6b7280";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(v.toFixed(2), pad.l + cw + 5, y + 3);
  }

  // MA
  function maLine(n, color) {
    if (k.length < n) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    let started = false;
    for (let i = n - 1; i < k.length; i++) {
      const avg = closes.slice(i - n + 1, i + 1).reduce((a, b) => a + b, 0) / n;
      const x = X(i), y = Y(avg);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  maLine(20, "rgba(251,191,36,.78)");
  maLine(60, "rgba(96,165,250,.78)");

  // 面积
  const g = ctx.createLinearGradient(0, pad.t, 0, pad.t + ch);
  g.addColorStop(0, "rgba(59,130,246,.28)");
  g.addColorStop(1, "rgba(59,130,246,0)");
  ctx.beginPath();
  ctx.moveTo(X(0), Y(closes[0]));
  for (let i = 1; i < k.length; i++) ctx.lineTo(X(i), Y(closes[i]));
  ctx.lineTo(X(k.length - 1), pad.t + ch);
  ctx.lineTo(X(0), pad.t + ch);
  ctx.closePath();
  ctx.fillStyle = g;
  ctx.fill();

  // 线
  ctx.beginPath();
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 1.6;
  ctx.moveTo(X(0), Y(closes[0]));
  for (let i = 1; i < k.length; i++) ctx.lineTo(X(i), Y(closes[i]));
  ctx.stroke();

  // 日期
  ctx.fillStyle = "#6b7280";
  ctx.font = "10px sans-serif";
  [0, Math.floor(k.length / 2), k.length - 1].forEach((i) => {
    ctx.textAlign = i === 0 ? "left" : i === k.length - 1 ? "right" : "center";
    ctx.fillText(k[i].d, X(i), H - 4);
  });

  ma20.value = (closes.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, closes.length)).toFixed(2);
  ma60.value = closes.length >= 60
    ? (closes.slice(-60).reduce((a, b) => a + b, 0) / 60).toFixed(2)
    : "—";
}

onMounted(load);
watch(() => curTab.value, (v) => { if (v === "chart") nextTick(draw); });
window.addEventListener("resize", () => { if (curTab.value === "chart") draw(); });
</script>
