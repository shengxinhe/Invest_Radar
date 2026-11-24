// 投资雷达 PWA Service Worker
// 策略：App Shell 预缓存 + API 网络优先（离线回退缓存）
// 版本号由构建脚本自动更新（scripts/bump_sw.py），每次部署必须变化，否则客户端不更新

const VERSION = "v202611240937";
const SHELL = `shell-${VERSION}`;
const RUNTIME = `runtime-${VERSION}`;

const SHELL_FILES = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL && k !== RUNTIME)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // 只处理同源
  if (url.origin !== location.origin) return;

  // API：网络优先，失败回退缓存
  if (url.pathname.startsWith("/api/")) {
    // SSE 不能走 SW
    if (url.pathname.startsWith("/api/stream")) return;
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res.ok && e.request.method === "GET") {
            const clone = res.clone();
            caches.open(RUNTIME).then((c) => c.put(e.request, clone));
          }
          return res;
        })
        .catch(() =>
          caches.match(e.request).then(
            (r) =>
              r ||
              new Response(
                JSON.stringify({ ok: false, offline: true, msg: "离线，无缓存" }),
                { headers: { "Content-Type": "application/json" } }
              )
          )
        )
    );
    return;
  }

  // 导航请求（打开/刷新页面）：网络优先，保证拿到新 index.html → 引用新 assets
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(SHELL).then((c) => c.put("/index.html", clone));
          return res;
        })
        .catch(() => caches.match("/index.html"))
    );
    return;
  }

  // 其余静态资源：缓存优先（文件名带 hash，安全）
  e.respondWith(
    caches.match(e.request).then((cached) => {
      if (cached) return cached;
      return fetch(e.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(SHELL).then((c) => c.put(e.request, clone));
        }
        return res;
      }).catch(() => caches.match("/index.html"));
    })
  );
});
