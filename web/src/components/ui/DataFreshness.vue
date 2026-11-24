<template>
  <div class="st" :data-st="status">
    <span class="st-dot"></span>
    <span class="st-text">
      {{ label || defaultLabel }}
      <template v-if="at"> {{ at }}</template>
    </span>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, default: "unknown" }, // fresh/delayed/stale/failed/missing/unknown
  at: { type: String, default: "" },
  label: { type: String, default: "" },
});

const defaultLabel = computed(() => ({
  fresh: "实时",
  delayed: "延迟",
  stale: "已过期",
  failed: "抓取失败",
  missing: "无数据",
  unknown: "未知",
}[props.status] || "未知"));
</script>

<style scoped>
.st {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: var(--fs-xs); color: var(--text-2);
  border: 1px solid var(--border-1); border-radius: var(--r-full);
  padding: 2px 8px;
}
.st-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--text-3); }
.st[data-st="fresh"] .st-dot { background: var(--good); box-shadow: 0 0 5px var(--good); }
.st[data-st="delayed"] .st-dot { background: var(--warn); }
.st[data-st="stale"] .st-dot { background: var(--risk); }
.st[data-st="failed"] .st-dot { background: var(--risk); }
.st[data-st="missing"] .st-dot { background: var(--text-3); }
</style>
