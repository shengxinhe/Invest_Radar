<template>
  <div>
    <!-- 市场概览（真实指数，无数据显示暂无） -->
    <div class="mk-card">
      <div class="mk-head">
        <span class="mk-title">大盘</span>
        <span class="mk-at" v-if="mk.available">{{ mk.at }}</span>
        <span class="mk-at" v-else>暂无数据</span>
      </div>
      <div v-if="mk.available" class="mk-idx">
        <div v-for="i in mk.indices" :key="i.code" class="mk-item">
          <div class="mk-name">{{ i.name }}</div>
          <div class="mk-price num" :class="pctCls(i.pct)">{{ i.price?.toFixed(2) }}</div>
          <div class="mk-pct num" :class="pctCls(i.pct)">{{ fmtPct(i.pct) }}</div>
        </div>
      </div>
      <div v-else class="mk-empty">指数接口暂不可用</div>
      <div class="mk-stat">
        <span>关注池</span>
        <span class="up">↑{{ mk.watch_stat?.up || 0 }}</span>
        <span class="down">↓{{ mk.watch_stat?.down || 0 }}</span>
        <span class="flat">—{{ mk.watch_stat?.flat || 0 }}</span>
      </div>
    </div>

    <!-- 今日重点（分级） -->
    <div class="section-label">
      <span>今日重点</span>
      <span class="mk-count" v-if="highlights.length">{{ highlights.length }} 条</span>
    </div>
    <div v-if="!highlights.length" class="mk-none">今天暂无需优先处理的信息</div>
    <div v-for="h in highlights" :key="h.id" class="hl-item" :data-level="h.level" @click="$emit('open', h.id)">
      <div class="hl-left">
        <div class="hl-tag" :data-level="h.level">{{ levelLabel(h.level) }}</div>
      </div>
      <div class="hl-body">
        <div class="hl-title">{{ h.title }}</div>
        <div class="hl-meta">
          <span>{{ h.name }}</span>
          <span>{{ h.date }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api, pctCls, fmtPct } from "../api.js";

defineEmits(["open"]);

const mk = ref({ available: false, indices: [], watch_stat: {}, at: "" });
const highlights = ref([]);

function levelLabel(lv) {
  return lv === "risk" ? "风险" : lv === "positive" ? "机会" : "待查";
}

onMounted(async () => {
  try {
    mk.value = await api.marketOverview();
  } catch {}
  try {
    const d = await api.feed(0, 6, "risk");
    highlights.value = (d.items || []).slice(0, 3);
  } catch {}
});
</script>

<style scoped>
.mk-card {
  background: var(--surface-1); border: 1px solid var(--border-1);
  border-radius: var(--r-lg); padding: 13px 14px; margin-bottom: var(--sp-3);
}
.mk-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.mk-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-2); }
.mk-at { font-size: var(--fs-xs); color: var(--text-3); }
.mk-idx { display: flex; gap: var(--sp-3); }
.mk-item { flex: 1; min-width: 0; }
.mk-name { font-size: 11px; color: var(--text-2); margin-bottom: 2px; }
.mk-price { font-size: var(--fs-md); font-weight: 600; }
.mk-pct { font-size: 11px; }
.mk-empty { font-size: var(--fs-sm); color: var(--text-3); padding: 8px 0; }
.mk-stat {
  display: flex; gap: 10px; margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--border-1);
  font-size: var(--fs-xs); color: var(--text-2);
}
.mk-count { color: var(--text-3); font-size: var(--fs-xs); }
.mk-none { font-size: var(--fs-sm); color: var(--text-3); padding: 10px 0 14px; }

.hl-item {
  display: flex; gap: 10px; padding: 11px 12px; margin-bottom: var(--sp-2);
  background: var(--surface-1); border: 1px solid var(--border-1);
  border-radius: var(--r-md); min-height: var(--tap);
}
.hl-item:active { background: var(--surface-2); }
.hl-tag {
  font-size: var(--fs-xs); padding: 1px 7px; border-radius: 4px;
  background: var(--surface-3); color: var(--text-2); white-space: nowrap;
}
.hl-tag[data-level="risk"] { background: rgba(255, 92, 122, 0.16); color: var(--risk); }
.hl-tag[data-level="positive"] { background: rgba(61, 220, 151, 0.16); color: var(--good); }
.hl-body { flex: 1; min-width: 0; }
.hl-title { font-size: 13px; line-height: 1.45; }
.hl-meta { font-size: 11px; color: var(--text-2); margin-top: 3px; display: flex; gap: var(--sp-2); }
</style>
