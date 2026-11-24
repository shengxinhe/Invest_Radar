/**
 * M8 · useQuoteStream —— SSE 行情连接
 *
 * 从 EventSource 换成 fetch + ReadableStream，原因：
 *   EventSource 不能设置 Authorization 头，APK 跨域时无法带 Bearer token，
 *   服务端只会回 401。fetch 流式读取兼容两种凭证（Cookie / Bearer）。
 *
 * 同时补齐：断网/恢复检测、指数退避重连、页面隐藏暂停、卸载清理。
 */
import { ref, onMounted, onUnmounted } from "vue";
import { API_BASE, authHeaders } from "../env.js";

export function useQuoteStream(onQuote) {
  const status = ref("idle");      // idle / connecting / open / retrying / offline / closed
  const lastAt = ref(0);

  let ctrl = null;
  let retry = 0;
  let retryTimer = null;
  let closedByUser = false;
  let codeList = "";               // 逗号分隔，供 reconnect 复用

  async function connect(codes = "") {
    if (closedByUser || ctrl) return;
    codeList = codes || codeList;
    status.value = navigator.onLine === false ? "offline" : "connecting";
    if (navigator.onLine === false) return;

    ctrl = new AbortController();
    try {
      const url = `${API_BASE}/api/stream/quotes${codeList ? `?codes=${encodeURIComponent(codeList)}` : ""}`;
      const res = await fetch(url, {
        headers: authHeaders({ Accept: "text/event-stream" }),
        credentials: "include",
        signal: ctrl.signal,
      });

      if (res.status === 401) {
        status.value = "closed";
        window.dispatchEvent(new CustomEvent("radar:unauthorized"));
        close();
        return;
      }
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      status.value = "open";
      retry = 0;

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          for (const line of block.split("\n")) {
            const s = line.trim();
            if (!s.startsWith("data:")) continue;
            let m;
            try {
              m = JSON.parse(s.slice(5).trim());
            } catch {
              continue;
            }
            if (m.type === "quote") {
              lastAt.value = m.ts || 0;
              onQuote?.(m);
            } else if (m.type === "heartbeat") {
              lastAt.value = m.ts || Math.floor(Date.now() / 1000);
            }
          }
        }
      }
      // 服务端正常结束（极少见）：按断线处理
      close();
      scheduleRetry();
    } catch (e) {
      if (e?.name === "AbortError") return;
      close();
      status.value = navigator.onLine === false ? "offline" : "retrying";
      scheduleRetry();
    }
  }

  function scheduleRetry() {
    if (closedByUser || retryTimer) return;
    if (navigator.onLine === false) {
      status.value = "offline";
      return;
    }
    status.value = "retrying";
    // 2s → 4s → 8s → 16s → 30s 封顶
    const delay = Math.min(30000, 2000 * Math.pow(2, retry));
    retry += 1;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      connect();
    }, delay);
  }

  function close() {
    if (ctrl) {
      try { ctrl.abort(); } catch {}
      ctrl = null;
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

  function reconnect(codes = "") {
    closedByUser = false;
    retry = 0;
    close();
    connect(codes);
  }

  function onVisibility() {
    if (document.visibilityState === "hidden") {
      close();
      status.value = "idle";
    } else if (!closedByUser) {
      retry = 0;
      connect();
    }
  }

  function onOffline() {
    close();
    status.value = "offline";
  }

  function onOnline() {
    if (closedByUser) return;
    retry = 0;
    close();
    connect();
  }

  onMounted(() => {
    connect();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
  });

  onUnmounted(() => {
    closedByUser = true;
    close();
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
  });

  return { status, lastAt, reconnect, disconnect };
}
