import { createApp } from "vue";
import App from "./App.vue";
// M3 样式分层：tokens（变量） → theme（元素/布局） → components（组件）
import "./styles/tokens.css";
import "./styles/theme.css";
import "./styles/components.css";

createApp(App).mount("#app");

// 注册 Service Worker（仅在 https 或 localhost 下生效）
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* 忽略：非 https 环境注册失败是正常的 */
    });
  });
}
