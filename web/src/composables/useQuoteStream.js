/**
 * M5 · useQuoteStream —— SSE 行情连接生命周期管理
 * 保存实例 / 卸载关闭 / 后台暂停 / 重连退避 / 防重复连接
 */
import { ref, onMounted, onUnmounted } from "vue";

export function useQuoteStream(onQuote) {
  const status = ref("idle");      // idle / connecting / open / retrying / closed
  const lastAt = ref(0);
  let es = null;
  let retry = 0;
  let retryTimer = null;
  let closedByUser = false;

  function connect() {
    if (es || closedByUser) return;
    status.value = "connecting";
    try {
      es = new EventSource("/api/stream/quotes");
    } catch {
      status.value = "closed";
      return;
    }

    es.onopen = () => {
      status.value = "open";
      retry = 0;
    };

    es.onmessage = (ev) => {
      let m;
      try {
        m = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (m.type === "quote") {
        lastAt.value = m.ts || 0;
        onQuote?.(m);
      } else if (m.type === "heartbeat") {
        lastAt.value = m.ts || Date.now() / 1000;
      }
    };

    es.onerror = () => {
      close();
      if (closedByUser) return;
      status.value = "retrying";
      // 指数退避：2s → 4s → 8s → 最多 30s
      const delay = Math.min(30000, 2000 * Math.pow(2, retry));
      retry += 1;
      retryTimer = setTimeout(() => {
        retryTimer = null;
        connect();
      }, delay);
    };
  }

  function close() {
    if (es) {
      try { es.close(); } catch {}
      es = null;
    }
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  }

  function disconnect() {
    closedByUser = true;
    close();
    status.value = "closed";
  }

  function reconnect() {
    closedByUser = false;
    retry = 0;
    close();
    connect();
  }

  // 页面进入后台时断开，回前台重连（省电省上游）
  function onVisibility() {
    if (document.visibilityState === "hidden") {
      close();
      status.value = "idle";
    } else if (!closedByUser) {
      connect();
    }
  }

  onMounted(() => {
    connect();
    document.addEventListener("visibilitychange", onVisibility);
  });

  onUnmounted(() => {
    closedByUser = true;
    close();
    document.removeEventListener("visibilitychange", onVisibility);
  });

  return { status, lastAt, reconnect, disconnect };
}
