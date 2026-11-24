<template>
  <div class="st-bar">
    <button
      v-for="s in options" :key="s.key"
      class="st-btn" :class="{ active: current === s.key }"
      :data-key="s.key"
      @click="set(s.key)"
    >{{ s.label }}</button>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ status: { type: String, default: "unread" } });
const emit = defineEmits(["change"]);

const options = [
  { key: "unread", label: "未读" },
  { key: "pending", label: "待核查" },
  { key: "saved", label: "稍后" },
  { key: "processed", label: "已处理" },
  { key: "ignored", label: "忽略" },
];

const current = computed(() => props.status || "unread");
function set(k) { emit("change", k); }
</script>

<style scoped>
.st-bar { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.st-btn {
  font-size: 11px; padding: 4px 12px; border-radius: var(--r-full);
  background: var(--surface-1); border: 1px solid var(--border-1);
  color: var(--text-2); min-height: 30px;
}
.st-btn:active { opacity: 0.6; }
.st-btn.active[data-key="unread"] { background: var(--surface-3); color: var(--text); border-color: var(--border-2); }
.st-btn.active[data-key="pending"] { background: rgba(245, 197, 66, 0.16); color: var(--warn); border-color: rgba(245, 197, 66, 0.4); }
.st-btn.active[data-key="saved"] { background: var(--accent-dim); color: var(--accent); border-color: var(--accent-border); }
.st-btn.active[data-key="processed"] { background: rgba(61, 220, 151, 0.16); color: var(--good); border-color: rgba(61, 220, 151, 0.4); }
.st-btn.active[data-key="ignored"] { background: rgba(138, 143, 163, 0.16); color: var(--text-3); border-color: rgba(138, 143, 163, 0.35); }
</style>
