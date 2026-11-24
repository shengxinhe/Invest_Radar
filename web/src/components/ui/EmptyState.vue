<template>
  <div class="es">
    <div class="es-icon">{{ icon }}</div>
    <div class="es-text">{{ text }}</div>
    <button v-if="retry" class="es-btn" @click="$emit('retry')">重试</button>
  </div>
</template>

<script setup>
const props = defineProps({
  kind: { type: String, default: "empty" }, // empty / error / offline
  text: { type: String, default: "" },
  retry: { type: Boolean, default: false },
});
defineEmits(["retry"]);

const icon = {
  empty: "—",
  error: "⚠",
  offline: "⚡",
}[props.kind] || "—";
</script>

<style scoped>
.es { text-align: center; padding: 36px var(--sp-5); color: var(--text-2); }
.es-icon { font-size: 22px; margin-bottom: var(--sp-2); opacity: 0.6; }
.es-text { font-size: var(--fs-sm); line-height: 1.8; white-space: pre-line; }
.es-btn {
  margin-top: var(--sp-3); padding: 8px 20px;
  border-radius: var(--r-sm); font-size: var(--fs-sm);
  background: var(--surface-2); border: 1px solid var(--border-1);
  color: var(--accent); min-height: 36px;
}
.es-btn:active { opacity: 0.6; }
</style>
