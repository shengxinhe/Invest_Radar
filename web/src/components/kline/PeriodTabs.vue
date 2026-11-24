<template>
  <div class="pt-wrap">
    <div class="pt-tabs" ref="wrapEl">
      <div class="pt-glider" :style="gliderStyle"></div>
      <button
        v-for="(p, i) in periods" :key="p.k" ref="btnEls"
        class="pt-btn" :class="{ active: modelValue === p.k }"
        @click="$emit('update:modelValue', p.k)"
      >{{ p.label }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from "vue";

const props = defineProps({ modelValue: String });
defineEmits(["update:modelValue"]);

const periods = [
  { k: "minute", label: "分时" },
  { k: "5day", label: "5日" },
  { k: "day", label: "日K" },
  { k: "week", label: "周K" },
  { k: "month", label: "月K" },
  { k: "60m", label: "60分" },
];

const wrapEl = ref(null);
const btnEls = ref([]);
const gl = ref({ x: 0, w: 0 });

function update() {
  const i = periods.findIndex((p) => p.k === props.modelValue);
  const el = btnEls.value?.[i];
  if (!el || !wrapEl.value) return;
  gl.value = { x: el.offsetLeft, w: el.offsetWidth };
}

const gliderStyle = computed(() => ({
  width: gl.value.w + "px",
  transform: `translateX(${gl.value.x}px)`,
}));

onMounted(() => nextTick(update));
watch(() => props.modelValue, () => nextTick(update));
</script>

<style scoped>
.pt-wrap{padding:2px 4px 10px}
.pt-tabs{
  display:flex;position:relative;gap:0;
  background:rgba(255,255,255,.05);border-radius:12px;padding:3px;
}
.pt-glider{
  position:absolute;top:3px;bottom:3px;left:0;
  border-radius:10px;
  background:rgba(94,234,212,.16);
  border:1px solid rgba(94,234,212,.35);
  transition:transform .4s cubic-bezier(.34,1.56,.64,1), width .4s;
  z-index:1;
}
.pt-btn{
  flex:1;padding:6px 0;border-radius:10px;font-size:12px;
  color:var(--text-2);position:relative;z-index:2;text-align:center;
  transition:color .25s;
}
.pt-btn.active{color:var(--accent);font-weight:600}
</style>
