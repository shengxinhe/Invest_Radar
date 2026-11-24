<template>
  <div class="pulse-bar">
    <span class="pulse" :class="{ risk: risk > 0 }"></span>
    <span class="pulse-label">
      今日脉搏
      <span class="dots">
        <i v-for="n in Math.min(5, risk + positive)" :key="n"
           :class="n <= risk ? 'd-risk' : 'd-good'"></i>
      </span>
      <span class="count">
        <b class="risk-n">{{ risk }}风险</b> {{ positive }}利好
      </span>
    </span>
    <span v-if="queued" class="queued">待读 {{ queued }}</span>
  </div>
</template>

<script setup>
defineProps({
  risk: { type: Number, default: 0 },
  positive: { type: Number, default: 0 },
  queued: { type: Number, default: 0 },
});
</script>

<style scoped>
.pulse-bar{
  display:flex;align-items:center;gap:10px;
  padding:10px 14px;margin-bottom:12px;
  background:var(--card-bg);border:1px solid var(--card-border);
  border-radius:14px;
}
.pulse{
  width:8px;height:8px;border-radius:50%;flex-shrink:0;
  background:var(--accent);
  box-shadow:0 0 10px var(--accent);
  animation:breathe 2.4s ease-in-out infinite;
}
.pulse.risk{
  background:var(--down);
  box-shadow:0 0 10px var(--down);
  animation-duration:1s;
}
@keyframes breathe{50%{transform:scale(.6);opacity:.5}}
.pulse-label{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--text-2)}
.dots{display:inline-flex;gap:3px}
.dots i{width:5px;height:5px;border-radius:50%;display:inline-block}
.d-risk{background:var(--down);box-shadow:0 0 4px var(--down)}
.d-good{background:var(--up);box-shadow:0 0 4px var(--up)}
.count{margin-left:auto}
.risk-n{color:var(--down);font-weight:500}
.queued{font-size:11px;color:var(--accent);border:1px solid rgba(94,234,212,.35);
  padding:1px 7px;border-radius:10px}
</style>
