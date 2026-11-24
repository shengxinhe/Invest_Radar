<template>
  <div class="quote-header">
    <template v-if="bar">
      <div class="qh-row">
        <span class="qh-price num" :class="bar.close >= bar.open ? 'up' : 'down'">
          {{ bar.close?.toFixed(2) }}
        </span>
        <span class="qh-pct num" :class="bar.close >= bar.open ? 'up' : 'down'">
          {{ pctText }}
        </span>
      </div>
      <div class="qh-grid num">
        <span>开 <b>{{ bar.open?.toFixed(2) }}</b></span>
        <span>高 <b class="up">{{ bar.high?.toFixed(2) }}</b></span>
        <span>低 <b class="down">{{ bar.low?.toFixed(2) }}</b></span>
        <span v-if="bar.volume">量 <b>{{ fmtVol(bar.volume) }}</b></span>
        <span v-if="bar.turnover">额 <b>{{ fmtVol(bar.turnover) }}</b></span>
      </div>
    </template>
    <template v-else-if="latest">
      <div class="qh-row">
        <span class="qh-price num" :class="latest.close >= latest.open ? 'up' : 'down'">
          {{ latest.close?.toFixed(2) }}
        </span>
        <span class="qh-pct num" :class="latest.close >= latest.open ? 'up' : 'down'">
          {{ latestPct }}
        </span>
        <span class="qh-hint">长按查看历史</span>
      </div>
      <div class="qh-grid num">
        <span>开 <b>{{ latest.open?.toFixed(2) }}</b></span>
        <span>高 <b class="up">{{ latest.high?.toFixed(2) }}</b></span>
        <span>低 <b class="down">{{ latest.low?.toFixed(2) }}</b></span>
        <span v-if="latest.volume">量 <b>{{ fmtVol(latest.volume) }}</b></span>
      </div>
    </template>
    <div v-else class="qh-empty">—</div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ bar: Object, latest: Object });

const pctText = computed(() => {
  if (!props.bar?.open) return "";
  const v = ((props.bar.close - props.bar.open) / props.bar.open) * 100;
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
});
const latestPct = computed(() => {
  if (!props.latest?.open) return "";
  const v = ((props.latest.close - props.latest.open) / props.latest.open) * 100;
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
});

function fmtVol(v) {
  if (v == null) return "";
  if (v >= 1e8) return (v / 1e8).toFixed(2) + "亿";
  if (v >= 1e4) return (v / 1e4).toFixed(1) + "万";
  return Math.round(v).toString();
}
</script>

<style scoped>
.quote-header{padding:2px 4px 10px}
.qh-row{display:flex;align-items:baseline;gap:10px}
.qh-price{font-size:22px;font-weight:700}
.qh-pct{font-size:13px;font-weight:600}
.qh-hint{margin-left:auto;color:var(--text-2);font-size:10.5px}
.qh-grid{
  display:flex;gap:12px;flex-wrap:wrap;margin-top:5px;
  font-size:11.5px;color:var(--text-2);
}
.qh-grid b{color:var(--text);font-weight:500}
.qh-empty{color:var(--text-2);font-size:12px}
</style>
