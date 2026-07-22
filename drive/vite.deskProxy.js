/**
 * Local preview/dev proxy helpers for Research Drive desk auth.
 *
 * Injects Authorization from the host token file into proxied desk requests so
 * the browser never needs a pasted token. Production deploys do not use this.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function deskTokenFilePath() {
  return (
    process.env.YZU_DESK_TOKEN_FILE ||
    path.join(os.homedir(), ".config/research-drive/front-door.desk-token")
  );
}

export function readLocalDeskToken() {
  try {
    return fs.readFileSync(deskTokenFilePath(), "utf8").trim();
  } catch {
    return "";
  }
}

/** Desk API binds Tailscale on this host — prefer that over 127.0.0.1. */
export function defaultDeskApiTarget() {
  return process.env.YZU_API_URL || "http://100.127.141.44:8765";
}

/**
 * Keep Host as the preview origin (changeOrigin: false), and always inject
 * Bearer from the local token file when the browser omitted credentials.
 * Desk session bootstrap now requires the desk token (Origin alone is not
 * enough); this proxy supplies it without exposing the secret to JS.
 */
export function withLocalDeskAuth(proxyConfig = {}) {
  return {
    changeOrigin: false,
    ...proxyConfig,
    configure(proxy) {
      proxyConfig.configure?.(proxy);
      proxy.on("proxyReq", (proxyReq) => {
        if (proxyReq.getHeader("authorization") || proxyReq.getHeader("x-desk-token")) {
          return;
        }
        const token = readLocalDeskToken();
        if (!token) return;
        proxyReq.setHeader("Authorization", `Bearer ${token}`);
      });
    },
  };
}

export function buildDeskProxyMap(apiTarget = defaultDeskApiTarget()) {
  const apiProxy = withLocalDeskAuth({ target: apiTarget });
  return {
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
}
