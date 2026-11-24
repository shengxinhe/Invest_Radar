<template>
  <div>
    <!-- 顶部：搜索 + 新建 -->
    <div style="display:flex;gap:8px;margin-bottom:12px">
      <div class="search-box" style="flex:1">
        <span class="gh-icon">🔍</span>
        <input v-model="q" placeholder="搜笔记…" @input="load" />
      </div>
      <button class="btn btn-primary btn-sm" @click="openNew">＋ 笔记</button>
    </div>

    <!-- Tab：笔记 / 报告 -->
    <div class="tabs">
      <div class="tab" :class="{active:tab==='notes'}" @click="tab='notes';load()">研究笔记</div>
      <div class="tab" :class="{active:tab==='reports'}" @click="tab='reports';load()">AI 报告</div>
    </div>

    <!-- 笔记列表 -->
    <template v-if="tab==='notes'">
      <div v-if="loading" class="loading"><div class="spinner"></div></div>
      <EmptyState v-else-if="!items.length" kind="empty"
                  text="还没有研究笔记&#10;点「＋ 笔记」记录你的思考" />
      <div v-for="it in items" :key="it.id" class="card" style="padding:13px"
           @click="openEdit(it)">
        <div style="display:flex;justify-content:space-between;gap:8px">
          <div style="min-width:0">
            <div style="font-weight:600;font-size:14px">{{ it.title }}</div>
            <div style="color:var(--text-2);font-size:12px;margin-top:4px;line-height:1.6">
              {{ (it.content||'').slice(0,80) }}{{ (it.content||'').length>80?'…':'' }}
            </div>
            <div style="font-size:11px;color:var(--text-3);margin-top:6px;display:flex;gap:8px;flex-wrap:wrap">
              <span v-if="it.code" class="tag t-n">{{ it.code }}</span>
              <span v-for="t in (it.tags||'').split(',').filter(Boolean)" :key="t" class="tag t-n">{{ t }}</span>
              <span>{{ fmtTs(it.updated_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 报告列表 -->
    <template v-else>
      <div v-if="loading" class="loading"><div class="spinner"></div></div>
      <EmptyState v-else-if="!items.length" kind="empty"
                  text="还没有 AI 报告&#10;晨报/月度复盘/辩论会自动归档到这里" />
      <div v-for="it in items" :key="it.id" class="card" style="padding:13px"
           @click="openReport(it)">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <div style="min-width:0">
            <div style="font-weight:600;font-size:14px">{{ it.title }}</div>
            <div style="font-size:11px;color:var(--text-3);margin-top:4px">
              <span class="tag t-n">{{ kindLabel(it.kind) }}</span>
              {{ fmtTs(it.created_at) }}
            </div>
          </div>
          <a :href="`/api/reports/${it.id}/export`" @click.stop
             style="flex-shrink:0;font-size:12px;color:var(--accent)">导出</a>
        </div>
      </div>
    </template>

    <!-- 编辑弹层 -->
    <div v-if="editing" class="drawer-mask" @click="editing=false"></div>
    <div v-if="editing" class="drawer">
      <div class="drawer-head">
        <div class="drawer-title">{{ form.id ? '编辑笔记' : '新建笔记' }}</div>
        <button class="gh-back" @click="editing=false">×</button>
      </div>
      <div class="drawer-body">
        <input v-model="form.title" placeholder="标题"
               style="width:100%;background:var(--surface-2);border:1px solid var(--border-1);
                      border-radius:10px;padding:11px;outline:none;margin-bottom:10px;font-size:14px" />
        <textarea v-model="form.content" rows="10" placeholder="研究内容…"
                  style="width:100%;background:var(--surface-2);border:1px solid var(--border-1);
                         border-radius:10px;padding:11px;outline:none;margin-bottom:10px;
                         font-size:13.5px;line-height:1.7;resize:vertical"></textarea>
        <input v-model="form.tags" placeholder="标签（逗号分隔，如：估值,产能）"
               style="width:100%;background:var(--surface-2);border:1px solid var(--border-1);
                      border-radius:10px;padding:11px;outline:none;margin-bottom:10px;font-size:13px" />
        <div class="ai-note">AI 生成内容请标注来源；笔记仅存本机</div>
      </div>
      <div class="drawer-foot">
        <button v-if="form.id" class="btn" style="color:var(--risk)"
                @click="del">删除</button>
        <button class="btn btn-primary" @click="save" :disabled="saving">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>

    <!-- 报告阅读弹层 -->
    <div v-if="reading" class="drawer-mask" @click="reading=false"></div>
    <div v-if="reading" class="drawer">
      <div class="drawer-head">
        <div class="drawer-title">{{ reading.title }}</div>
        <button class="gh-back" @click="reading=false">×</button>
      </div>
      <div class="drawer-body">
        <div class="detail-content">{{ reading.content }}</div>
        <div class="ai-note">AI 生成，仅供研究参考</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../api.js";
import EmptyState from "./ui/EmptyState.vue";

const tab = ref("notes");
const items = ref([]);
const loading = ref(false);
const q = ref("");
const editing = ref(false);
const reading = ref(null);
const saving = ref(false);
const form = ref({ id: null, code: "", title: "", content: "", tags: "" });

const KIND = {
  daily_brief: "晨报", monthly_review: "月度复盘",
  today_focus: "今日重点", debate: "辩论", entry_ai: "解读",
};
function kindLabel(k) { return KIND[k] || k; }
function fmtTs(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

async function load() {
  loading.value = true;
  try {
    if (tab.value === "notes") {
      items.value = await api.researchList(q.value);
    } else {
      items.value = await api.reportList();
    }
  } catch {
    items.value = [];
  } finally {
    loading.value = false;
  }
}

function openNew() {
  form.value = { id: null, code: "", title: "", content: "", tags: "" };
  editing.value = true;
}
function openEdit(it) {
  form.value = { id: it.id, code: it.code, title: it.title,
                 content: it.content, tags: it.tags };
  editing.value = true;
}
async function save() {
  if (!form.value.title.trim()) return;
  saving.value = true;
  try {
    if (form.value.id) {
      await api.researchUpdate(form.value.id, form.value);
    } else {
      await api.researchAdd(form.value);
    }
    editing.value = false;
    await load();
  } catch (e) {
    alert("保存失败: " + e.message);
  } finally {
    saving.value = false;
  }
}
async function del() {
  if (!confirm("确定删除这条笔记？")) return;
  await api.researchDelete(form.value.id);
  editing.value = false;
  await load();
}
async function openReport(it) {
  const full = await api.reportGet(it.id);
  reading.value = full;
}

onMounted(load);
</script>
