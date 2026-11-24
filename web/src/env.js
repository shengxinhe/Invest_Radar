/**
 * 环境与 API 基础设施（本机版，单用户）
 *
 * 访问方式
 * --------
 * 1) 本机浏览器：  http://127.0.0.1:8000         → 同源，API_BASE = ""
 * 2) 本机浏览器(Tailscale 域名)：
 *                   → 同源，API_BASE = ""
 * 3) 手机装 APK：  WebView origin 是 https://localhost（跨站）
 *                  → 需要显式 API_BASE，来源见 resolveBase()
 *
 * 关键：浏览器一律走同源，绝不要把地址写死成某个域名，
 *      否则你换 WiFi / 换 Tailscale 名就会全部 404。
 */

// ---- 运行时判定 ----
export const IS_NATIVE =
  typeof window !== "undefined" &&
  (!!window.Capacitor?.isNativePlatform?.() ||
    location.protocol === "capacitor:" ||
    (location.hostname === "localhost" && !!window.Capacitor));

// ---- APK 的 API 地址 ----
// 优先级：构建注入 > 本地存储（App 内可改）> 内置默认
function nativeBase() {
  const injected = import.meta.env?.VITE_API_BASE;
  if (injected) return String(injected).replace(/\/+$/, "");
  try {
    const saved = localStorage.getItem("radar_api_base");
    if (saved) return String(saved).replace(/\/+$/, "");
  } catch {}
  // 默认留空：在 APK 首次打开时会引导用户填自己的地址
  return "";
}

export const API_BASE = IS_NATIVE ? nativeBase() : "";

/** 允许用户在 App 内切换 API 地址（换网络时用） */
export function setApiBase(url) {
  try {
    if (url) localStorage.setItem("radar_api_base", String(url).replace(/\/+$/, ""));
    else localStorage.removeItem("radar_api_base");
  } catch {}
}

export function getApiBase() {
  return IS_NATIVE ? nativeBase() : "";
}

/** 拼完整 URL */
export function apiUrl(path) {
  return API_BASE + path;
}
