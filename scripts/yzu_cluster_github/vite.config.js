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
const pagesBase = process.env.GITHUB_ACTIONS === "true" ? "/yzu-cluster/" : "/";

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
