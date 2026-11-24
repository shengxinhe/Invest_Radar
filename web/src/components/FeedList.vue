<template>
  <div>
    <div class="feed-filters">
      <button
        v-for="f in filters" :key="f.key"
        class="ff-btn" :class="{ active: filter === f.key }"
        @click="setFilter(f.key)"
      >{{ f.label }}</button>
    </div>

    <template v-if="loading && !items.length">
      <div v-for="i in 3" :key="'sk'+i" style="margin-bottom:12px">
        <Skeleton h="52px" />
      </div>
    </template>

    <EmptyState
      v-else-if="error"
      kind="error"
      :text="error"
      retry
      @retry="load(true)"
    />

    <FeedCard
      v-for="it in items"
      :key="it.id"
      :item="it"
      @open="(id) => $emit('open', id)"
      @ai="(it) => $emit('ai', it)"
    />

    <div v-if="loading && items.length" class="loading">
      <div class="spinner"></div>加载中…
    </div>
    <EmptyState v-else-if="!items.length" kind="empty" text="暂无内容" />
    <div v-else-if="!hasMore" class="end">— 到底了 —</div>
    <div ref="sentinel" style="height:1px"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import FeedCard from "./FeedCard.vue";
import Skeleton from "./ui/Skeleton.vue";
import EmptyState from "./ui/EmptyState.vue";
import { api } from "../api.js";

const emit = defineEmits(["open", "ai"]);

const items = ref([]);
const loading = ref(false);
const hasMore = ref(true);
const error = ref("");
const sentinel = ref(null);
const filter = ref("");

const filters = [
  { key: "", label: "全部" },
  { key: "risk", label: "风险" },
  { key: "positive", label: "利好" },
];

let seq = 0;
let ctrl = null;

async function load(reset = false) {
  if (loading.value && !reset) return;
  if (!reset && !hasMore.value) return;

  const mySeq = ++seq;
  if (ctrl) ctrl.abort();
  ctrl = new AbortController();

  loading.value = true;
  error.value = "";
  if (reset) {
    items.value = [];
    hasMore.value = true;
  }

  try {
    const cursor = reset
      ? ""
      : (items.value.length ? items.value[items.value.length - 1]._cursor : "");
    const d = await api.feed(cursor, 25, filter.value || undefined);
    if (mySeq !== seq) return;            // 过期响应丢弃

    const fresh = (d.items || []).filter(
      (x) => !items.value.some((y) => y.id === x.id)   // 去重兜底
    );
    // 记录每条的游标（用最后一条的 next_cursor 作为续传点）
    if (fresh.length) {
      fresh.forEach((x) => (x._cursor = d.next_cursor || ""));
      items.value.push(...fresh);
    }
    hasMore.value = d.next_cursor != null;
    // 空页保护
    if (!fresh.length && d.next_cursor == null) hasMore.value = false;
  } catch (e) {
    if (mySeq !== seq) return;
    if (e?.name === "AbortError") return;
    error.value = e?.message || "加载失败";
  } finally {
    if (mySeq === seq) loading.value = false;
  }
}

function setFilter(k) {
  if (filter.value === k) return;
  filter.value = k;
  load(true);          // 切筛选：重置游标，取消旧请求
}

let io;
onMounted(() => {
  load(true);
  io = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && !error.value) load();
    },
    { rootMargin: "400px" }
  );
  if (sentinel.value) io.observe(sentinel.value);
});
onUnmounted(() => {
  io?.disconnect();
  if (ctrl) ctrl.abort();
});
</script>

<style scoped>
.feed-filters { display: flex; gap: 6px; margin-bottom: var(--sp-3); }
.ff-btn {
  padding: 5px 14px; border-radius: var(--r-full); font-size: var(--fs-sm);
  background: var(--surface-1); border: 1px solid var(--border-1);
  color: var(--text-2); min-height: 34px;
}
.ff-btn.active {
  background: var(--accent-dim); color: var(--accent);
  border-color: var(--accent-border);
}
.end { text-align: center; color: var(--text-2); font-size: 11px; padding: 14px; }
</style>
