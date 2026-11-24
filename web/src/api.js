// 极简 API 封装
const BASE = "";

export async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...opts,
  });
  if (res.status === 401) {
    // 认证失效：通知 App 回到登录页
    window.dispatchEvent(new CustomEvent("radar:unauthorized"));
    throw new Error("未登录");
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) msg = j.detail;
    } catch {}
    throw new Error(msg);
  }
  const j = await res.json();
  if (j && j.ok === false) throw new Error(j.msg || "请求失败");
  return j.data !== undefined ? j.data : j;
}

export const api = {
  health: () => req("/api/health"),

  watch: () => req("/api/watch"),
  addWatch: (body) =>
    req("/api/watch", { method: "POST", body: JSON.stringify(body) }),
  delWatch: (code) => req(`/api/watch/${code}`, { method: "DELETE" }),

  search: (q) => req(`/api/search?q=${encodeURIComponent(q)}`),

  stock: (code, refresh = false) =>
    req(`/api/stock/${code}${refresh ? "?refresh=true" : ""}`),
  chart: (code, days = 120) => req(`/api/stock/${code}/chart?days=${days}`),
  kline: (code, period = "day", limit = 250) =>
    req(`/api/stock/${code}/kline?period=${period}&limit=${limit}`),
  timeline: (code, days = 1) => req(`/api/stock/${code}/timeline?days=${days}`),
  entries: (code, type = "", days = 30, level = "") => {
    const p = new URLSearchParams({ days });
    if (type) p.set("type", type);
    if (level) p.set("level", level);
    return req(`/api/stock/${code}/entries?${p}`);
  },
  extras: (code) => req(`/api/stock/${code}/extras`),
  reports: (code) => req(`/api/stock/${code}/reports`),
  market: () => req("/api/market"),

  entry: (id) => req(`/api/entry/${id}`),
  setEntryState: (id, patch) =>
    req(`/api/entry/${id}/state`, { method: "POST", body: JSON.stringify(patch) }),
  bulkState: (ids, patch) =>
    req("/api/entries/state", { method: "POST", body: JSON.stringify({ entry_ids: ids, ...patch }) }),
  stateCounts: () => req("/api/entries/states"),
  thesisHistory: (code) => req(`/api/watch/${code}/thesis/history`),
  updateThesis: (code, patch) =>
    req(`/api/watch/${code}/thesis`, { method: "PUT", body: JSON.stringify({ code, ...patch }) }),
  // M6 研究笔记与报告
  researchList: (q = "") => req(`/api/research?q=${encodeURIComponent(q)}`),
  researchAdd: (body) => req("/api/research", { method: "POST", body: JSON.stringify(body) }),
  researchUpdate: (id, body) => req(`/api/research/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  researchDelete: (id) => req(`/api/research/${id}`, { method: "DELETE" }),
  reportList: (kind = "") => req(`/api/reports${kind ? `?kind=${kind}` : ""}`),
  reportGet: (id) => req(`/api/reports/${id}`),
  syncStock: (code) => req(`/api/stock/${code}/sync`, { method: "POST" }),
  feed: (cursor = "", limit = 25, filter) => {
    const p = new URLSearchParams({ limit });
    if (cursor) p.set("cursor", cursor);
    if (filter) p.set("filter", filter);
    return req(`/api/feed?${p}`);
  },
  pulse: () => req("/api/pulse"),
  marketOverview: () => req("/api/market/overview"),
};

// 工具
export const fmtPct = (v) =>
  v == null ? "-" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%";
export const pctCls = (v) =>
  v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat";
export const fmtMoney = (v) => {
  if (v == null) return "-";
  const a = Math.abs(v);
  if (a < 1e4) return Math.round(v);
  if (a < 1e8) return (v / 1e4).toFixed(0) + "万";
  return (v / 1e8).toFixed(2) + "亿";
};
export const fmtShares = (v) => {
  if (v == null) return "-";
  const a = Math.abs(v);
  if (a < 1e4) return Math.round(v) + "股";
  if (a < 1e8) return (v / 1e4).toFixed(0) + "万股";
  return (v / 1e8).toFixed(2) + "亿股";
};
export const tsToDate = (ts, withTime = false) => {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  const s = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  return withTime ? `${s} ${p(d.getHours())}:${p(d.getMinutes())}` : s;
};
export const levelDot = (lv) =>
  lv === "risk" ? "#ef4444" : lv === "positive" ? "#22c55e" : "#4b5563";
