<template>
  <div class="watch-strip">
    <div class="ws-scroll">
      <div
        v-for="w in list"
        :key="w.code"
        class="ws-card"
        :class="{ active: selected === w.code }"
        @click="$emit('select', w.code)"
      >
        <div class="ws-name">{{ w.name }}</div>
        <div class="ws-price num" :class="pctCls(w.pct)">{{ w.price ?? "—" }}</div>
        <div class="ws-pct num" :class="pctCls(w.pct)">{{ fmtPct(w.pct) }}</div>
        <div class="ws-pe" v-if="w.pe">PE {{ w.pe.toFixed(1) }}</div>
      </div>
      <div class="ws-card ws-add" @click="$emit('add')">
        <div class="ws-plus">＋</div>
        <div class="ws-add-label">加自选</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { pctCls, fmtPct } from "../api.js";

defineProps({
  list: { type: Array, default: () => [] },
  selected: String,
});
defineEmits(["select", "add"]);
</script>

<style scoped>
.watch-strip{margin-bottom:14px}
.ws-scroll{
  display:flex;gap:10px;overflow-x:auto;padding:2px;
  scrollbar-width:none;
}
.ws-scroll::-webkit-scrollbar{display:none}
.ws-card{
  flex-shrink:0;width:108px;
  background:var(--card-bg);border:1px solid var(--card-border);
  border-radius:14px;padding:10px 12px;
  transition:transform .15s, border-color .15s;
}
.ws-card:active{transform:scale(.96)}
.ws-card.active{border-color:rgba(94,234,212,.5);background:rgba(94,234,212,.06)}
.ws-name{font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;margin-bottom:5px}
.ws-price{font-size:17px;font-weight:600}
.ws-pct{font-size:11px;margin-top:1px}
.ws-pe{font-size:10px;color:var(--text-2);margin-top:4px}
.ws-add{display:flex;flex-direction:column;align-items:center;justify-content:center;
  color:var(--text-2);border-style:dashed}
.ws-plus{font-size:20px;color:var(--accent)}
.ws-add-label{font-size:11px;margin-top:4px}
</style>
