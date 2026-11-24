<template>
  <div class="sk" :style="{ height: h, width: w }"></div>
</template>

<script setup>
defineProps({
  h: { type: String, default: "16px" },
  w: { type: String, default: "100%" },
});
</script>

<style scoped>
.sk {
  border-radius: var(--r-sm);
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.04) 25%,
    rgba(255, 255, 255, 0.08) 37%,
    rgba(255, 255, 255, 0.04) 63%
  );
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}
@keyframes shimmer {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}
@media (prefers-reduced-motion: reduce) {
  .sk { animation: none; }
}
</style>
