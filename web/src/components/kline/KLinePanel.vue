<template>
  <div class="kl-panel">
    <QuoteHeader :bar="cursorBar" :latest="latestBar" />
    <PeriodTabs v-model="period" />
    <div class="kl-chart" ref="chartEl"></div>
    <div v-if="loading" class="kl-loading"><div class="spinner"></div></div>
    <div class="kl-legend">
      <template v-if="!isTimeline">
        <span v-for="(n, k) in maVisible" :key="k" :style="{ color: maColors[k] }">
          {{ k }} {{ n ?? "—" }}
        </span>
      </template>
      <template v-else>
        <span style="color:#F5C542">均价 {{ avgNow ?? "—" }}</span>
        <span style="color:#8A8FA3">昨收 {{ preClose ?? "—" }}</span>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { api } from "../../api.js";
import { useKline } from "./useKline.js";

const props = defineProps({ code: String });

const chartEl = ref(null);
const period = ref("day");
const loading = ref(false);
const cursorBar = ref(null);
const latestBar = ref(null);
const preClose = ref(null);
const maVisible = ref({});
const avgNow = ref(null);

const maColors = { MA5: "#F5C542", MA10: "#5EEAD4", MA20: "#C084FC", MA60: "#60A5FA" };
const isTimeline = computed(() => period.value === "minute" || period.value === "5day");

const k = useKline(chartEl);
let resizeOb = null;
let timer = null;

async function load() {
  loading.value = true;
  cursorBar.value = null;
  try {
    if (isTimeline.value) {
      const d = await api.timeline(props.code, period.value === "minute" ? 1 : 5);
      preClose.value = d.pre_close;
      k.loadTimeline(d.bars, d.pre_close);
      // 均价展示（分时）
      const withAvg = d.bars.filter((b) => b.avg_price != null);
      avgNow.value = withAvg.length ? withAvg[withAvg.length - 1].avg_price.toFixed(2) : null;
      latestBar.value = null;
      maVisible.value = {};
    } else {
      const d = await api.kline(props.code, period.value, 250);
      k.load(d.bars);
      latestBar.value = d.bars[d.bars.length - 1] || null;
      // 用后端 MA 的末值显示
      maVisible.value = {};
      for (const [name, arr] of Object.entries(d.ma)) {
        const last = arr[arr.length - 1];
        maVisible.value[name] = last != null ? last.toFixed(2) : null;
      }
      avgNow.value = null;
      preClose.value = null;
    }
  } catch (e) {
    console.error("kline load fail", e);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await nextTick();
  k.initChart();
  k.createMA();
  k.bindCrosshair((bar) => {
    cursorBar.value = bar;
  });
  await load();
  // 盘中分时 30s 轮询
  timer = setInterval(() => {
    if (period.value === "minute" && document.visibilityState === "visible") load();
  }, 30000);
  // 横屏/尺寸自适应
  resizeOb = new ResizeObserver(() => {
    const c = k.getChart();
    if (c && chartEl.value) c.resize();
  });
  if (chartEl.value) resizeOb.observe(chartEl.value);
});

onUnmounted(() => {
  // 离页必须 dispose，防多实例泄漏
  clearInterval(timer);
  resizeOb?.disconnect();
  k.disposeChart();
});

watch(period, () => {
  k.setPeriod();
  load();
});
</script>

<style scoped>
.kl-panel{
  position:relative;
  background:var(--card-bg);border:1px solid var(--card-border);
  border-radius:16px;padding:14px 12px 8px;margin-bottom:12px;
}
.kl-chart{height:280px;width:100%}
.kl-loading{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  background:rgba(8,9,15,.4);border-radius:16px;z-index:5;
}
.kl-legend{
  display:flex;gap:14px;font-size:11px;padding:6px 4px 4px;
  flex-wrap:wrap;
}
</style>
