import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const API_TARGET = "http://127.0.0.1:8765";
const apiProxy = {
  target: API_TARGET,
  changeOrigin: true,
};
const proxy = {
  "/api": {
    ...apiProxy,
    rewrite: (path) => path.replace(/^\/api/, ""),
  },
  "/datasets": apiProxy,
  "/health": apiProxy,
  "/library": apiProxy,
  "/query": apiProxy,
  "/yzu": apiProxy,
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./drive/src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5178,
    proxy,
    watch: {
      ignored: [
        "**/.venv/**",
        "**/deliverables/**",
        "**/data_lake/**",
        "**/artifacts/**",
        "**/archive/**",
        "**/archives/**",
        "**/node_modules/**",
        "**/*.png",
        "**/*.jpg",
        "**/*.jpeg",
        "**/*.webp",
        "**/scrapes/**",
        "**/backtests/**",
      ],
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4178,
    proxy,
  },
});
