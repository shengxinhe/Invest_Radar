/**
 * M2 · SSE 前端统一解析器
 * 处理：不完整数据块 / 多事件同块 / UTF-8 跨界 / 取消 / 错误上报
 */

export async function readSSE(response, handlers = {}, signal) {
  const {
    onStart, onChunk, onSegment, onProgress, onWarning, onError, onDone,
  } = handlers;

  if (!response.body) {
    onError?.({ msg: "响应无 body", kind: "no_body" });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  const dispatch = (raw) => {
    const line = raw.trim();
    if (!line || !line.startsWith("data:")) return;
    const payload = line.slice(5).trim();
    if (!payload) return;
    let m;
    try {
      m = JSON.parse(payload);
    } catch {
      // 解析失败不静默丢弃：作为 warning 上报
      onWarning?.({ msg: "事件解析失败", raw: payload.slice(0, 120) });
      return;
    }
    switch (m.type) {
      case "start": onStart?.(m); break;
      case "chunk": onChunk?.(m.text ?? "", m); break;
      case "segment": onSegment?.(m.key, m.label, m.text ?? "", m); break;
      case "progress": onProgress?.(m); break;
      case "warning": onWarning?.(m); break;
      case "error": onError?.(m); break;
      case "done": onDone?.(m); break;
      default: onWarning?.({ msg: `未知事件类型 ${m.type}`, raw: payload.slice(0, 80) });
    }
  };

  try {
    while (true) {
      if (signal?.aborted) {
        try { await reader.cancel(); } catch {}
        return;
      }
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of block.split("\n")) dispatch(line);
      }
    }
    // 收尾：冲刷剩余
    if (buf.trim()) for (const line of buf.split("\n")) dispatch(line);
  } catch (e) {
    if (e?.name === "AbortError") return;
    onError?.({ msg: e?.message || "网络中断", kind: "network" });
  } finally {
    try { reader.releaseLock(); } catch {}
  }
}

/**
 * 统一 POST-SSE 调用
 * @returns {Promise<void>}
 */
export async function postSSE(url, body, handlers = {}, opts = {}) {
  const { signal, timeoutMs = 240000 } = opts;
  const ctrl = new AbortController();
  const timer = timeoutMs ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  if (signal) signal.addEventListener("abort", () => ctrl.abort(), { once: true });

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });

    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent("radar:unauthorized"));
      handlers.onError?.({ msg: "未登录", kind: "auth" });
      return;
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        if (j.detail) msg = j.detail;
      } catch {}
      handlers.onError?.({ msg, kind: "http" });
      return;
    }
    await readSSE(res, handlers, ctrl.signal);
  } catch (e) {
    if (e?.name !== "AbortError") {
      handlers.onError?.({ msg: e?.message || "请求失败", kind: "network" });
    }
  } finally {
    if (timer) clearTimeout(timer);
  }
}
