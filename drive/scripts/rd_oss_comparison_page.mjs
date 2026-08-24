#!/usr/bin/env node
/**
 * OSS reference captures + side-by-side comparison HTML for Research Drive.
 * Does not require Figma — uses Playwright on public pages + local desk.
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const DESK = process.env.YZU_DESK_URL || "http://127.0.0.1:8765";
const OUT = path.resolve("docs/status/generated/rd-oss-compare");
const HTML = path.resolve("docs/status/generated/research-drive-oss-comparison.html");

const REFERENCES = [
  {
    id: "hf-datasets",
    label: "Hugging Face — Datasets",
    steal: "Catalog rows, filter chips, dataset card density",
    url: "https://huggingface.co/datasets",
    wait: 4000,
    fullPage: false,
  },
  {
    id: "hf-dataset-detail",
    label: "Hugging Face — Dataset repo",
    steal: "Overview / Files / Schema tabs, README hero, Add to collection",
    url: "https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces",
    wait: 4000,
    fullPage: false,
  },
];

const RD_VIEWS = [
  { id: "rd-home", nav: null, label: "RD — Home" },
  { id: "rd-drive", nav: "Drive", label: "RD — Drive (All)" },
  { id: "rd-chat", nav: "Chat", label: "RD — Chat" },
  { id: "rd-cluster", nav: "Cluster", label: "RD — Cluster" },
  { id: "rd-discover", nav: "Discover", label: "RD — Discover" },
];

const GAPS = [
  {
    surface: "Drive list",
    oss: "HF / KohakuHub",
    have: "Flat catalog table, scope chips",
    miss: "Repo-style Browse drill-in; README preview; file tree in left facet column",
    priority: "P0",
  },
  {
    surface: "Nav rail",
    oss: "Google Drive",
    have: "Internal / Procure / Tools blocks",
    miss: "Calmer density; no duplicate job badges on Chat+Activity; collapsed admin",
    priority: "P1",
  },
  {
    surface: "Cluster",
    oss: "Cite-Agent Coverage",
    have: "Domain cards + pipeline strip",
    miss: "Topic map, domain brief, gap synthesis, timeline of promotes",
    priority: "P0",
  },
  {
    surface: "Chat",
    oss: "Cite-Agent /chat + Gemini",
    have: "Full-page procure thread",
    miss: "Workbench composition; scoped context strip; warm state when holdings exist",
    priority: "P1",
  },
  {
    surface: "Discover",
    oss: "HF hub search",
    have: "Search + source filters + result rows",
    miss: "Recommended datasets grid; transition into Browse layout",
    priority: "P1",
  },
  {
    surface: "Details rail",
    oss: "Drive inspector",
    have: "Metadata-only inspector",
    miss: "Single L2 panel; no chip swarm; star inline in row only",
    priority: "P2",
  },
];

async function captureReferences(browser) {
  const shots = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  for (const ref of REFERENCES) {
    try {
      await page.goto(ref.url, { waitUntil: "domcontentloaded", timeout: 60_000 });
      await page.waitForTimeout(ref.wait);
      const file = `${ref.id}.png`;
      await page.screenshot({ path: path.join(OUT, file), fullPage: ref.fullPage });
      shots.push({ ...ref, file, ok: true });
    } catch (err) {
      shots.push({ ...ref, file: null, ok: false, error: err.message });
    }
  }
  await page.close();
  return shots;
}

async function captureDesk(browser) {
  const shots = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(DESK, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: /Lab data library/i }).waitFor({ timeout: 30_000 }).catch(() => {});

  for (const view of RD_VIEWS) {
    try {
      if (view.id !== "rd-home") {
        await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${view.nav}`) }).click();
        await page.waitForTimeout(700);
      }
      const file = `${view.id}.png`;
      await page.screenshot({ path: path.join(OUT, file), fullPage: false });
      shots.push({ ...view, file, ok: true });
    } catch (err) {
      shots.push({ ...view, file: null, ok: false, error: err.message });
    }
  }
  await page.close();
  return shots;
}

function buildHtml(refs, rd, meta) {
  const refCards = refs
    .map(
      (r) => `
      <article class="card ref">
        <header>
          <span class="tag oss">OSS</span>
          <h3>${r.label}</h3>
          <p class="steal">${r.steal}</p>
          ${r.ok ? "" : `<p class="err">Capture failed: ${r.error}</p>`}
        </header>
        ${r.file ? `<img src="rd-oss-compare/${r.file}" alt="${r.id}" loading="lazy" />` : `<div class="placeholder">No capture</div>`}
      </article>`,
    )
    .join("");

  const rdCards = rd
    .map(
      (r) => `
      <article class="card rd">
        <header>
          <span class="tag rd-tag">Current</span>
          <h3>${r.label}</h3>
        </header>
        ${r.file ? `<img src="rd-oss-compare/${r.file}" alt="${r.id}" loading="lazy" />` : `<div class="placeholder">No capture</div>`}
      </article>`,
    )
    .join("");

  const gapRows = GAPS.map(
    (g) => `
    <tr>
      <td><strong>${g.surface}</strong></td>
      <td>${g.oss}</td>
      <td class="have">${g.have}</td>
      <td class="miss">${g.miss}</td>
      <td><span class="pri ${g.priority.toLowerCase()}">${g.priority}</span></td>
    </tr>`,
  ).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Research Drive — OSS comparison</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,600;0,9..40,700;1,9..40,400&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #0a0e12;
      --panel: #111820;
      --line: #243040;
      --text: #e8eef4;
      --muted: #8fa3b8;
      --oss: #c9a227;
      --rd: #4d9fff;
      --good: #6bcf8e;
      --warn: #e6b84d;
      --bad: #f07178;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "DM Sans", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background:
        radial-gradient(ellipse 80% 50% at 10% -10%, rgba(77, 159, 255, 0.08), transparent),
        radial-gradient(ellipse 60% 40% at 90% 0%, rgba(201, 162, 39, 0.06), transparent);
      pointer-events: none;
      z-index: 0;
    }
    .wrap { position: relative; z-index: 1; max-width: 1480px; margin: 0 auto; padding: 32px 24px 64px; }
    h1 { font-size: clamp(1.6rem, 3vw, 2.2rem); margin: 0 0 8px; letter-spacing: -0.02em; }
    .lead { color: var(--muted); max-width: 72ch; margin: 0 0 28px; }
    .mono { font-family: "IBM Plex Mono", monospace; font-size: 0.82rem; }
    .banner {
      display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 32px;
      padding: 14px 18px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel);
    }
    .banner a { color: var(--rd); }
    section { margin-bottom: 48px; }
    section h2 {
      font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--muted); margin: 0 0 16px;
    }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 16px; }
    .card {
      border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: var(--panel);
    }
    .card header { padding: 14px 16px; border-bottom: 1px solid var(--line); }
    .card h3 { margin: 6px 0 4px; font-size: 1rem; }
    .steal { margin: 0; font-size: 0.88rem; color: var(--muted); }
    .card img { display: block; width: 100%; height: auto; }
    .tag {
      display: inline-block; font-family: "IBM Plex Mono", monospace; font-size: 0.68rem;
      letter-spacing: 0.08em; text-transform: uppercase; padding: 3px 8px; border-radius: 6px;
    }
    .tag.oss { background: rgba(201, 162, 39, 0.15); color: var(--oss); }
    .tag.rd-tag { background: rgba(77, 159, 255, 0.12); color: var(--rd); }
    .placeholder { padding: 80px 16px; text-align: center; color: var(--muted); }
    .err { color: var(--bad); font-size: 0.85rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }
    .have { color: var(--good); }
    .miss { color: var(--warn); }
    .pri { font-family: "IBM Plex Mono", monospace; font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; }
    .pri.p0 { background: rgba(240, 113, 120, 0.15); color: var(--bad); }
    .pri.p1 { background: rgba(230, 184, 77, 0.15); color: var(--warn); }
    .pri.p2 { background: rgba(143, 163, 184, 0.15); color: var(--muted); }
    .verdict {
      padding: 20px 22px; border-left: 3px solid var(--warn); background: rgba(230, 184, 77, 0.06);
      border-radius: 0 12px 12px 0; margin-top: 8px;
    }
    .verdict strong { color: var(--warn); }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Research Drive × OSS reference board</h1>
    <p class="lead">
      Honest comparison: live captures from Hugging Face (public) vs current Research Drive at
      <span class="mono">${DESK}</span>. Generated ${meta.at}. Phase A passes tests; product finish is not signed off.
    </p>
    <div class="banner">
      <span>Live desk: <a href="${DESK}" target="_blank">${DESK}</a></span>
      <span>·</span>
      <span>Prior check page: <a href="research-drive-check.html">research-drive-check.html</a></span>
      <span>·</span>
      <span class="mono">Figma: approve MCP auth → generate frames from this board</span>
    </div>

    <div class="verdict">
      <strong>Verdict:</strong> IA direction is right (Drive fork + procure block + Chat peer). Visual and workflow parity with HF Browse and Cite-Agent Coverage is <em>not</em> there yet. Build Browse + Cluster v2 before more CSS polish.
    </div>

    <section>
      <h2>OSS references — what to steal</h2>
      <div class="grid">${refCards}</div>
    </section>

    <section>
      <h2>Research Drive — current build</h2>
      <div class="grid">${rdCards}</div>
    </section>

    <section>
      <h2>Gap matrix</h2>
      <table>
        <thead>
          <tr><th>Surface</th><th>OSS anchor</th><th>We have</th><th>Missing</th><th></th></tr>
        </thead>
        <tbody>${gapRows}</tbody>
      </table>
    </section>
  </div>
</body>
</html>`;
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox"],
  });
  const [refs, rd] = await Promise.all([captureReferences(browser), captureDesk(browser)]);
  await browser.close();
  const meta = { at: new Date().toISOString(), desk: DESK };
  fs.writeFileSync(HTML, buildHtml(refs, rd, meta));
  fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify({ meta, refs, rd, gaps: GAPS }, null, 2));
  console.log(HTML);
  console.log(`file://${HTML}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
