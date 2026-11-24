<template>
  <nav class="glass-nav">
    <div class="nav-glider" ref="glider" :style="gliderStyle"></div>
    <button
      v-for="(t, i) in tabs"
      :key="t.key"
      ref="btns"
      class="nav-item"
      :class="{ active: modelValue === t.key }"
      @click="$emit('update:modelValue', t.key)"
    >
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path v-for="(d, j) in t.icon" :key="j" :d="d" />
      </svg>
      <span>{{ t.label }}</span>
    </button>
  </nav>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from "vue";

const props = defineProps({ modelValue: String });
const emit = defineEmits(["update:modelValue"]);

const tabs = [
  { key: "home", label: "首页", icon: ["M3 11l9-8 9 8", "M5 10v10h5v-6h4v6h5V10"] },
  { key: "quote", label: "行情", icon: ["M3 17l5-6 4 3 5-8 4 5", "M3 21h18"] },
  { key: "watch", label: "自选", icon: ["M12 2l2.9 6.1L21 9l-4.5 4.3L17.8 20 12 16.9 6.2 20l1.3-6.7L3 9l6.1-.9z"] },
  { key: "ai", label: "AI", icon: ["M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1 4 4v2a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4v-2a4 4 0 0 1 4-4V7a4 4 0 0 1 4-4z", "M9.5 12.5h.01M14.5 12.5h.01", "M9.5 16h5"] },
];

const glider = ref(null);
const btns = ref([]);
const gl = ref({ x: 0, w: 0 });

function updateGlider() {
  const i = tabs.findIndex((t) => t.key === props.modelValue);
  const el = btns.value?.[i];
  const nav = glider.value?.parentElement;
  if (!el || !nav) return;
  // 胶囊相对 nav 定位（nav 有 6px padding，item 内有独立空间）
  gl.value = { x: el.offsetLeft, w: el.offsetWidth };
}

const gliderStyle = computed(() => ({
  width: gl.value.w + "px",
  transform: `translateX(${gl.value.x}px)`,
}));

onMounted(() => {
  nextTick(updateGlider);
  window.addEventListener("resize", updateGlider);
});
onUnmounted(() => window.removeEventListener("resize", updateGlider));
watch(() => props.modelValue, () => nextTick(updateGlider));
</script>

<style scoped>
.glass-nav{
  position:fixed; left:10px; right:10px;
  bottom:calc(12px + var(--safe-bottom));
  height:64px; border-radius:32px;
  display:flex; align-items:center; padding:6px;
  background:var(--glass-bg);
  -webkit-backdrop-filter:blur(24px) saturate(180%);
  backdrop-filter:blur(24px) saturate(180%);
  border:1px solid var(--glass-border);
  box-shadow:0 10px 40px rgba(0,0,0,.55), var(--glass-hi);
  overflow:visible; z-index:100;
}
.glass-nav::before{
  content:""; position:absolute; inset:0; border-radius:inherit;
  background:linear-gradient(180deg,rgba(255,255,255,.14),transparent 42%);
  pointer-events:none; mix-blend-mode:overlay;
}
.nav-item{
  flex:1; display:flex; flex-direction:column; align-items:center; gap:2px;
  font-size:10px; color:var(--text-2); background:none; border:0;
  position:relative; z-index:2; transition:color .25s;
  height:100%; justify-content:center;
}
.nav-item.active{ color:#fff; }
.nav-item.active svg{ filter:drop-shadow(0 0 6px var(--accent)); }
.nav-glider{
  position:absolute; top:6px; bottom:6px; left:0; height:auto;
  border-radius:26px;
  background:linear-gradient(180deg,rgba(94,234,212,.28),rgba(94,234,212,.10));
  border:1px solid rgba(94,234,212,.35);
  box-shadow:0 0 20px rgba(94,234,212,.25), inset 0 1px 0 rgba(255,255,255,.35);
  transition:transform .4s cubic-bezier(.34,1.56,.64,1), width .4s;
  z-index:1;
}
</style>
