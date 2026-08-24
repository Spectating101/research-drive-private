#!/usr/bin/env node
/**
 * Live desk verification for public yzu-cluster (no Python / monorepo deps).
 * Checks API :8765, UI proxy, and optional Composer configuration.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const API = (process.env.YZU_API_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
const UI = (process.env.YZU_DESK_URL || "http://127.0.0.1:5178").replace(/\/$/, "");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "docs", "status", "desk_verify_live.json");

async function getJson(url, timeoutMs = 20_000) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ac.signal });
    const data = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data };
  } finally {
    clearTimeout(t);
  }
}

async function main() {
  const report = { checks: [], api: API, ui: UI };

  let health;
  try {
    health = await getJson(`${API}/health?live=1`);
    const h = health.data || {};
    const desk = h.desk || {};
    report.checks.push({
      name: "api_health",
      ok: health.ok && h.status === "ok",
      status: h.status,
      composer_configured: desk.composer_configured,
      brain: desk.brain,
    });
  } catch (err) {
    report.checks.push({ name: "api_health", ok: false, error: String(err) });
  }

  try {
    const ds = await getJson(`${API}/datasets`);
    const n = (ds.data?.datasets || []).length;
    report.checks.push({ name: "registry_datasets", ok: ds.ok && n >= 1, count: n });
  } catch (err) {
    report.checks.push({ name: "registry_datasets", ok: false, error: String(err) });
  }

  try {
    const via = await getJson(`${UI}/api/datasets`);
    const n = (via.data?.datasets || []).length;
    report.checks.push({ name: "ui_proxy_datasets", ok: via.ok && n >= 1, count: n, base: UI });
  } catch (err) {
    report.checks.push({
      name: "ui_proxy_datasets",
      ok: false,
      error: String(err),
      hint: "Start UI: npm run dev (and API on :8765 from Sharpe-Renaissance)",
    });
  }

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, `${JSON.stringify(report, null, 2)}\n`);

  const passed = report.checks.filter((c) => c.ok).length;
  console.log(JSON.stringify(report, null, 2));
  console.log(`\nSummary: ${passed}/${report.checks.length} passed → ${OUT}`);

  const coreOk = report.checks.every((c) => c.ok);
  process.exit(coreOk ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
