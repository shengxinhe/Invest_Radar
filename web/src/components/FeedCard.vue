<template>
  <div class="feed-card" :data-level="item.level" @click="$emit('open', item.id)">
    <div class="fc-body">
      <div class="fc-title">{{ item.title }}</div>
      <div class="fc-meta">
        <span class="fc-name">{{ item.name || item.code }}</span>
        <span>{{ typeLabel }}</span>
        <span>{{ item.date }}</span>
        <span v-if="item.level === 'risk'" class="fc-flag risk">风险</span>
        <span v-else-if="item.level === 'positive'" class="fc-flag good">利好</span>
      </div>
      <div class="fc-actions">
        <button class="fc-btn" @click.stop="askAI">AI解读</button>
        <a v-if="item.url" class="fc-btn" :href="item.url" target="_blank" rel="noopener" @click.stop>原文</a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ item: Object });
const emit = defineEmits(["open", "ai"]);

const typeLabel = computed(() => ({
  notice: "公告", news: "新闻", qa: "互动", report: "研报", market: "快讯",
}[props.item.type] || ""));

function askAI() {
  emit("ai", props.item);
}
</script>

<style scoped>
.feed-card{
  position:relative; margin:0 0 12px; padding:13px 14px 13px 20px;
  border-radius:16px; background:var(--card-bg);
  border:1px solid var(--card-border);
  transition:transform .2s, background .2s;
  cursor:pointer;
}
.feed-card:active{ transform:scale(.985); background:rgba(255,255,255,.06); }
.feed-card::before{
  content:""; position:absolute; left:8px; top:13px; bottom:13px;
  width:3px; border-radius:2px; background:var(--accent);
}
.feed-card[data-level="risk"]::before{ background:var(--down); box-shadow:0 0 8px var(--down); }
.feed-card[data-level="positive"]::before{ background:var(--up); box-shadow:0 0 8px var(--up); }
.fc-title{font-size:13.5px;line-height:1.5;word-break:break-word}
.fc-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px;color:var(--text-2);font-size:11px;align-items:center}
.fc-name{color:var(--text)}
.fc-flag{padding:0 6px;border-radius:4px;font-size:10px}
.fc-flag.risk{background:rgba(255,92,122,.16);color:var(--down)}
.fc-flag.good{background:rgba(61,220,151,.16);color:var(--up)}
.fc-actions{display:flex;gap:8px;margin-top:9px}
.fc-btn{
  font-size:11.5px;padding:4px 11px;border-radius:8px;
  background:rgba(94,234,212,.10);color:var(--accent);
  border:1px solid rgba(94,234,212,.28);
  display:inline-flex;align-items:center;
}
.fc-btn:active{opacity:.6}
</style>
