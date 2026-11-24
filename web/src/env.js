/**
 * M8 · 环境与身份基础设施
 *
 * 为什么需要这一层
 * ----------------
 * 旧代码 `const BASE = ""` 在浏览器里没问题（同源），
 * 但 Capacitor 打包后页面 origin 是 https://localhost，
 * 相对路径会打到 WebView 本地，API 全部 404。
 * 所以：唯一出口 = 这个文件的 API_BASE。
 */

// ---- 运行时判定 ----
export const IS_NATIVE =
  typeof window !== "undefined" &&
  (!!window.Capacitor?.isNativePlatform?.() ||
    // 兜底：Capacitor 的 WebView 有这两个标记
    location.protocol === "capacitor:" ||
    (location.hostname === "localhost" && !!window.Capacitor));

// ---- API 地址（换域名只改这里）----
const DEV_FALLBACK = ""; // 浏览器开发时走 vite proxy / 同源

function resolveBase() {
  // 1) 构建时注入（推荐用于 APK：VITE_API_BASE=https://api.xxx）
  const injected = import.meta.env?.VITE_API_BASE;
  if (injected) return String(injected).replace(/\/+$/, "");

  // 2) APK 没注入时：硬编码生产地址（punycode，兼容所有 Android WebView）
  if (IS_NATIVE) return "https://api.you.xn--6or.gay";

  // 3) 浏览器：同源
  return DEV_FALLBACK;
}

export const API_BASE = resolveBase();

// ---- token（APK 用；浏览器依赖 HttpOnly Cookie）----
const TOKEN_KEY = "radar_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(t) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

export function clearToken() {
  setToken("");
}

/** 统一请求头：浏览器有 Cookie 也带 Bearer，两者后端都认 */
export function authHeaders(extra = {}) {
  const h = { ...extra };
  const t = getToken();
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

/** 拼完整 URL */
export function apiUrl(path) {
  return API_BASE + path;
}
