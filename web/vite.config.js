import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

export default defineConfig({
  plugins: [vue()],
  // public/ 里的文件原样拷贝到 dist 根，不参与 hash
  publicDir: "public",
  build: {
    outDir: resolve(__dirname, "../web_build"),
    emptyOutDir: true,
    assetsInlineLimit: 200 * 1024,
  },
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
