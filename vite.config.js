import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const API_TARGET = process.env.YZU_API_URL || "http://127.0.0.1:8765";
const apiProxy = {
  target: API_TARGET,
  changeOrigin: true,
  // The desk session bootstrap intentionally verifies browser same-origin.
  // In dev, Vite is that same-origin facade, so forward the upstream origin.
  configure: (proxy) => {
    proxy.on("proxyReq", (proxyReq) => {
      proxyReq.setHeader("origin", API_TARGET);
    });
  },
};
const proxy = {
  "/api": {
    ...apiProxy,
    rewrite: (p) => p.replace(/^\/api/, ""),
  },
  "/datasets": apiProxy,
  "/health": apiProxy,
  "/library": apiProxy,
  "/query": apiProxy,
  "/yzu": apiProxy,
};

// GitHub Pages: https://spectating101.github.io/yzu-cluster/
// Use YZU_PAGES=true only for Pages builds. Do not key off GITHUB_ACTIONS —
// Actions runners always set it, which would force base=/yzu-cluster/ during
// Playwright webServer startup and make http://127.0.0.1:PORT/ return 302
// (not 2xx), timing out the mock e2e job at ~120s.
const pagesBase = process.env.YZU_PAGES === "true" ? "/yzu-cluster/" : "/";

export default defineConfig({
  base: pagesBase,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./drive/src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.YZU_DESK_PORT || 5178),
    proxy,
  },
  preview: {
    host: "127.0.0.1",
    port: Number(process.env.YZU_PREVIEW_PORT || 4178),
    proxy,
  },
});
