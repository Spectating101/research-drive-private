#!/usr/bin/env node
/**
 * Generic website scraper — any HTTPS URL.
 * Usage: node generic_url_scrape.mjs --url https://example.com [--mode page|links|datasets] [--out path.json]
 *
 * Env: PLAYWRIGHT_HEADLESS, PLAYWRIGHT_TIMEOUT_MS, SPECTATOR_STAGING
 */
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";

const FILE_EXT_RE = /\.(csv|tsv|json|jsonl|zip|gz|parquet|xlsx?|xml|pdf|txt|ndjson)(\?|$)/i;

function isBlockedHostname(hostname) {
  const h = String(hostname || "").toLowerCase().replace(/\.$/, "");
  if (!h) return true;
  if (
    h === "localhost" ||
    h === "localhost.localdomain" ||
    h === "metadata" ||
    h === "metadata.google.internal" ||
    h === "instance-data" ||
    h.endsWith(".localhost") ||
    h.endsWith(".local") ||
    h.endsWith(".internal") ||
    h.endsWith(".lan") ||
    h.endsWith(".home")
  ) {
    return true;
  }
  if (h === "::1" || h === "0:0:0:0:0:0:0:1") return true;
  // IPv4 private / loopback / link-local / metadata
  if (/^(127\.|10\.|0\.|169\.254\.|192\.168\.|192\.0\.0\.|192\.0\.2\.|198\.18\.|198\.19\.|198\.51\.100\.|203\.0\.113\.)/.test(h)) {
    return true;
  }
  // 172.16.0.0 – 172.31.255.255
  const m = h.match(/^172\.(\d+)\./);
  if (m) {
    const second = Number(m[1]);
    if (second >= 16 && second <= 31) return true;
  }
  return false;
}

function isBlockedUrl(raw) {
  try {
    const u = new URL(String(raw || ""));
    if (!["http:", "https:"].includes(u.protocol)) return true;
    return isBlockedHostname(u.hostname);
  } catch {
    return true;
  }
}

async function installNetworkGuard(pageOrContext) {
  await pageOrContext.route("**/*", async (route) => {
    const target = route.request().url();
    if (isBlockedUrl(target)) {
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
}


function parseArgs(argv) {
  const out = {
    url: "",
    mode: "page",
    out: "",
    maxPages: 64,
    maxTokens: 3500,
    pauseMs: 400,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--url" && argv[i + 1]) {
      out.url = argv[++i];
    } else if (a === "--mode" && argv[i + 1]) {
      out.mode = argv[++i];
    } else if (a === "--out" && argv[i + 1]) {
      out.out = argv[++i];
    } else if (a === "--max-pages" && argv[i + 1]) {
      out.maxPages = Number.parseInt(argv[++i], 10);
    } else if (a === "--max-tokens" && argv[i + 1]) {
      out.maxTokens = Number.parseInt(argv[++i], 10);
    } else if (a === "--pause-ms" && argv[i + 1]) {
      out.pauseMs = Number.parseInt(argv[++i], 10);
    }
  }
  if (!out.url.startsWith("http")) {
    throw new Error("--url https://... is required");
  }
  if (isBlockedUrl(out.url)) {
    throw new Error(`blocked non-public url: ${out.url}`);
  }
  return out;
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function slugFromUrl(url) {
  try {
    const u = new URL(url);
    const base = `${u.hostname}${u.pathname}`.replace(/[^a-z0-9]+/gi, "_").slice(0, 48);
    const hash = createHash("sha256").update(url).digest("hex").slice(0, 8);
    return `${base}_${hash}`;
  } catch {
    return createHash("sha256").update(url).digest("hex").slice(0, 16);
  }
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (error) {
    if (error?.code === "ERR_MODULE_NOT_FOUND" || error?.code === "MODULE_NOT_FOUND") {
      return null;
    }
    throw error;
  }
}

async function fetchFallback(url, timeoutMs) {
  if (isBlockedUrl(url)) {
    throw new Error(`blocked non-public url: ${url}`);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { "User-Agent": "YZU-GenericScraper/1.0 (+research procurement)" },
      redirect: "follow",
    });
    // fetch follows redirects; reject final URL if private.
    if (response.url && isBlockedUrl(response.url)) {
      throw new Error(`blocked non-public redirect target: ${response.url}`);
    }
    const text = await response.text();
    const titleMatch = text.match(/<title[^>]*>([^<]+)<\/title>/i);
    const links = [];
    const linkRe = /<a\s+[^>]*href=["']([^"']+)["'][^>]*>(.*?)<\/a>/gis;
    let m;
    while ((m = linkRe.exec(text)) !== null && links.length < 500) {
      const href = m[1];
      const label = normalizeText(m[2].replace(/<[^>]+>/g, ""));
      let absolute = href;
      try {
        absolute = new URL(href, url).href;
      } catch {
        continue;
      }
      links.push({ href: absolute, text: label.slice(0, 200) });
    }
    return {
      engine: "fetch",
      url,
      status: response.status,
      title: titleMatch ? normalizeText(titleMatch[1]) : "",
      links,
      dataset_links: links.filter((row) => FILE_EXT_RE.test(row.href)),
      text_sample: normalizeText(text.replace(/<[^>]+>/g, " ")).slice(0, 4000),
      extracted_at: new Date().toISOString(),
    };
  } finally {
    clearTimeout(timer);
  }
}

async function playwrightExtract(url, mode, timeoutMs) {
  const { chromium } = await loadPlaywright();
  if (!chromium) {
    return fetchFallback(url, timeoutMs);
  }
  const headless = !["0", "false", "no"].includes(String(process.env.PLAYWRIGHT_HEADLESS || "true").toLowerCase());
  let browser;
  try {
    browser = await chromium.launch({ headless });
  } catch {
    return fetchFallback(url, timeoutMs);
  }
  const context = await browser.newContext({
    userAgent: "YZU-GenericScraper/1.0 (+research procurement)",
  });
  await installNetworkGuard(context);
  const page = await context.newPage();
  page.setDefaultNavigationTimeout(timeoutMs);
  page.setDefaultTimeout(timeoutMs);
  try {
    if (isBlockedUrl(url)) {
      throw new Error(`blocked non-public url: ${url}`);
    }
    let response;
    try {
      response = await page.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });
    } catch {
      response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
      await page.waitForTimeout(2000);
    }
    if (page.url() && isBlockedUrl(page.url())) {
      throw new Error(`blocked non-public navigation target: ${page.url()}`);
    }
    const title = normalizeText(await page.title());
    const metaDescription = normalizeText(
      await page.locator('meta[name="description"]').first().getAttribute("content").catch(() => ""),
    );
    const links = await page.evaluate(() => {
      const rows = [];
      for (const a of Array.from(document.querySelectorAll("a[href]"))) {
        const href = a.href;
        const text = (a.textContent || "").replace(/\s+/g, " ").trim().slice(0, 200);
        if (href.startsWith("http")) rows.push({ href, text });
      }
      return rows.slice(0, 800);
    });
    const headings = await page.evaluate(() => ({
      h1: Array.from(document.querySelectorAll("h1")).map((el) => (el.textContent || "").trim()).filter(Boolean).slice(0, 20),
      h2: Array.from(document.querySelectorAll("h2")).map((el) => (el.textContent || "").trim()).filter(Boolean).slice(0, 30),
    }));
    const bodyText = normalizeText(await page.locator("body").innerText().catch(() => "")).slice(0, 12000);
    const tables = await page.evaluate(() => {
      const out = [];
      for (const table of Array.from(document.querySelectorAll("table")).slice(0, 5)) {
        const rows = [];
        for (const tr of Array.from(table.querySelectorAll("tr")).slice(0, 15)) {
          const cells = Array.from(tr.querySelectorAll("th,td")).map((c) => (c.textContent || "").trim());
          if (cells.length) rows.push(cells);
        }
        if (rows.length) out.push(rows);
      }
      return out;
    });
    const datasetLinks = links.filter((row) => FILE_EXT_RE.test(row.href));
    const RECORD_RE = /zenodo\.org\/records\/\d+/i;
    const DOI_RE = /doi\.org\/10\./i;
    for (const row of links) {
      if ((RECORD_RE.test(row.href) || DOI_RE.test(row.href)) && !datasetLinks.some((x) => x.href === row.href)) {
        datasetLinks.push(row);
      }
    }
    const payload = {
      engine: "playwright",
      url,
      status: response?.status() ?? 0,
      title,
      meta_description: metaDescription || null,
      headings,
      links: mode === "links" || mode === "datasets" ? links : links.slice(0, 200),
      dataset_links: datasetLinks,
      tables: mode === "page" ? tables : [],
      text_sample: mode === "page" ? bodyText : "",
      extracted_at: new Date().toISOString(),
    };
    if (mode === "datasets") {
      payload.focus = "dataset_links";
      payload.links = datasetLinks;
    }
    return payload;
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

function isEtherscanHost(url) {
  try {
    return new URL(url).hostname.includes("etherscan.io");
  } catch {
    return false;
  }
}

function resolvePlaywrightLaunch(url) {
  const etherscan = isEtherscanHost(url);
  const envHeadless = process.env.PLAYWRIGHT_HEADLESS;
  let headless = true;
  if (envHeadless != null && envHeadless !== "") {
    headless = !["0", "false", "no"].includes(String(envHeadless).toLowerCase());
  } else if (etherscan) {
    // Cloudflare Turnstile blocks bundled Chromium headless; real Chrome headed passes.
    headless = false;
  }
  const launchOpts = {
    headless,
    args: ["--disable-blink-features=AutomationControlled"],
  };
  if (["1", "true", "yes"].includes(String(process.env.PLAYWRIGHT_NO_SANDBOX || "").toLowerCase())) {
    launchOpts.args.push("--no-sandbox");
  }
  const channel = process.env.PLAYWRIGHT_CHANNEL || (etherscan ? "chrome" : "");
  if (channel) launchOpts.channel = channel;
  return launchOpts;
}

async function waitForTokenDetail(page, waitMs) {
  const deadline = Date.now() + waitMs;
  while (Date.now() < deadline) {
    const title = (await page.title()).toLowerCase();
    if (title.includes("just a moment") || title.includes("security verification")) {
      await page.waitForTimeout(2000);
      continue;
    }
    const summaryCount = await page.locator(
      "#ContentPlaceHolder1_divSummary, #ContentPlaceHolder1_tr_tokeninfo, #ContentPlaceHolder1_hdTokenName",
    ).count();
    if (summaryCount > 0) return true;
    const bodyLen = await page.evaluate(() => (document.body?.innerText || "").length);
    if (bodyLen > 900) return true;
    await page.waitForTimeout(2000);
  }
  return false;
}

async function waitForTokenListing(page, waitMs) {
  const deadline = Date.now() + waitMs;
  while (Date.now() < deadline) {
    const count = await page.locator('table tbody tr a[href*="/token/"]').count();
    if (count > 0) return count;
    await page.waitForTimeout(2000);
  }
  return page.locator('table tbody tr a[href*="/token/"]').count();
}

async function launchCatalogBrowser(chromium, startUrl) {
  const launchOpts = resolvePlaywrightLaunch(startUrl);
  const profileRoot = process.env.PLAYWRIGHT_PROFILE_DIR || path.join(process.cwd(), "data_lake/spectator_engine/.playwright");
  if (isEtherscanHost(startUrl)) {
    const profileDir = path.join(profileRoot, "etherscan_chrome_profile");
    await fs.mkdir(profileDir, { recursive: true });
    const context = await chromium.launchPersistentContext(profileDir, {
      channel: launchOpts.channel || "chrome",
      headless: launchOpts.headless,
      args: launchOpts.args,
      viewport: { width: 1280, height: 900 },
      userAgent:
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    });
    return { browser: null, context, persistent: true };
  }
  const browser = await chromium.launch(launchOpts);
  const context = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  });
  return { browser, context, persistent: false };
}

async function playwrightCatalog(startUrl, config, timeoutMs) {
  const { chromium } = await loadPlaywright();
  if (!chromium) {
    throw new Error("catalog mode requires Playwright");
  }
  const { browser, context, persistent } = await launchCatalogBrowser(chromium, startUrl);
  await installNetworkGuard(context);
  if (isBlockedUrl(startUrl)) {
    throw new Error(`blocked non-public url: ${startUrl}`);
  }
  const page = context.pages()[0] || (await context.newPage());
  page.setDefaultNavigationTimeout(timeoutMs);
  page.setDefaultTimeout(timeoutMs);

  const maxPages = Math.max(1, config.maxPages || 1);
  const maxTokens = Math.max(1, config.maxTokens || 50);
  const pauseMs = Math.max(0, config.pauseMs || (isEtherscanHost(startUrl) ? 1200 : 400));
  const outDir = config.out;
  const tokensDir = path.join(outDir, "tokens");
  await fs.mkdir(tokensDir, { recursive: true });

  const listingBase = new URL(startUrl);
  const listingLabel = listingBase.searchParams.get("l") || "";

  function listingPageUrl(pageNum) {
    const u = new URL(startUrl);
    u.searchParams.set("p", String(pageNum));
    if (listingLabel && !u.searchParams.get("l")) {
      u.searchParams.set("l", listingLabel);
    }
    return u.href;
  }

  const tokenMap = new Map();

  for (let pageNum = 1; pageNum <= maxPages; pageNum += 1) {
    const pageUrl = listingPageUrl(pageNum);
    await page.goto(pageUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    const rowCount = await waitForTokenListing(page, Math.min(timeoutMs, 120000));
    if (!rowCount && pageNum === 1) {
      const debugHtml = await page.content();
      await fs.writeFile(path.join(outDir, "listing_blocked.html"), debugHtml, "utf8");
      throw new Error(
        "Etherscan listing blocked (Cloudflare). Use PLAYWRIGHT_CHANNEL=chrome PLAYWRIGHT_HEADLESS=false with xvfb-run.",
      );
    }
    const batch = await page.evaluate(() => {
      const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
      const rows = [];
      for (const tr of document.querySelectorAll("table tbody tr")) {
        const a = tr.querySelector('a[href*="/token/"]');
        if (!a || !a.href) continue;
        const parts = a.href.split("/token/");
        if (parts.length < 2) continue;
        const address = parts[1].split("?")[0].split("#")[0];
        if (!address.startsWith("0x")) continue;
        const cells = [...tr.querySelectorAll("td")].map((td) => norm(td.innerText));
        const nameText = norm(a.innerText);
        let symbol = "";
        const symStart = nameText.indexOf("(");
        const symEnd = nameText.indexOf(")");
        if (symStart >= 0 && symEnd > symStart) {
          symbol = nameText.slice(symStart + 1, symEnd).trim();
        }
        rows.push({
          address,
          name: nameText,
          symbol,
          rank: cells[0] || "",
          price: cells[3] || "",
          change_pct: cells[4] || "",
          volume_24h: cells[5] || "",
          onchain_market_cap: cells[6] || "",
          circulating_market_cap: cells[7] || "",
          holders: cells[8] || "",
          href: `https://etherscan.io/token/${address}`,
        });
      }
      return rows;
    });
    if (!batch.length) break;
    for (const row of batch) {
      if (!tokenMap.has(row.address)) tokenMap.set(row.address, row);
    }
    if (tokenMap.size >= maxTokens) break;
  }

  const addresses = [...tokenMap.keys()].slice(0, maxTokens);
  const harvested = [];

  for (const address of addresses) {
    const listing = tokenMap.get(address);
    const tokenUrl = `https://etherscan.io/token/${address}`;
    let detail = null;
    let htmlPath = "";
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page.goto(tokenUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
      const ready = await waitForTokenDetail(page, Math.min(timeoutMs, 90000));
      if (!ready) {
        if (attempt < 2) {
          await page.waitForTimeout(3000 + attempt * 2000);
          continue;
        }
        break;
      }
      detail = await page.evaluate(() => {
      const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
      const root =
        document.querySelector("#ContentPlaceHolder1_divSummary") ||
        document.querySelector("#ContentPlaceHolder1") ||
        document.querySelector("#content") ||
        document.body;
      const summaryRoot = root;
      const overview = {};
      for (const row of summaryRoot.querySelectorAll(".row")) {
        const labelEl = row.querySelector(".col-md-4, .col-lg-4, .col-4");
        const valueEl = row.querySelector(".col-md-8, .col-lg-8, .col-8");
        if (!labelEl || !valueEl) continue;
        const label = norm(labelEl.innerText).toUpperCase();
        const value = norm(valueEl.innerText);
        if (!value) continue;
        if (label.includes("MAX TOTAL SUPPLY")) overview.max_total_supply = value;
        else if (label === "HOLDERS" || label.startsWith("HOLDERS ")) overview.holders = value;
        else if (label.includes("TRANSFERS TOTAL 24H")) overview.transfers_total_24h = value;
        else if (label === "PRICE" || label.startsWith("PRICE ")) overview.price = value;
        else if (label.includes("ONCHAIN MARKET CAP")) overview.onchain_market_cap = value;
        else if (label.includes("CIRCULATING SUPPLY MARKET CAP")) overview.circulating_supply_market_cap = value;
      }
      // Etherscan layout variants: dl/dt/dd and card body key-value lines
      for (const dl of summaryRoot.querySelectorAll("dl")) {
        const dts = [...dl.querySelectorAll("dt")];
        const dds = [...dl.querySelectorAll("dd")];
        for (let i = 0; i < dts.length; i += 1) {
          const label = norm(dts[i]?.innerText).toUpperCase();
          const value = norm(dds[i]?.innerText);
          if (!label || !value) continue;
          if (label.includes("HOLDERS")) overview.holders = overview.holders || value;
          if (label.includes("TRANSFERS")) overview.transfers_total_24h = overview.transfers_total_24h || value;
          if (label.includes("SUPPLY")) overview.max_total_supply = overview.max_total_supply || value;
        }
      }
      const pageText = norm(root.innerText || "");
      const pick = (re) => {
        const m = pageText.match(re);
        return m ? norm(m[1]) : "";
      };
      if (!overview.holders) overview.holders = pick(/HOLDERS\s+([\d,]+(?:\s+[\d.]+%)?)/i);
      if (!overview.transfers_total_24h) overview.transfers_total_24h = pick(/TRANSFERS\s+TOTAL\s+24H\s+([\d,]+)/i);
      if (!overview.max_total_supply) overview.max_total_supply = pick(/MAX\s+TOTAL\s+SUPPLY\s+([\d,.\sA-Z]+)/i);
      const links = {};
      for (const a of summaryRoot.querySelectorAll('a[href^="http"]')) {
        const text = norm(a.innerText).toLowerCase();
        const href = a.href;
        if (!href || href.includes("etherscan.io")) continue;
        if (text.includes("coingecko") && href.includes("/coins/")) links.coingecko = href;
        else if (text.includes("coinmarketcap") && href.includes("/currencies/")) links.coinmarketcap = href;
        else if (text.includes("twitter") || text === "x (twitter)") links.twitter = href;
        else if (text.includes("telegram")) links.telegram = href;
        else if (text.includes("whitepaper")) links.whitepaper = href;
        else if (text.includes("reddit")) links.reddit = href;
        else if (text.includes("linkedin")) links.linkedin = href;
        else if (text.includes("facebook")) links.facebook = href;
        else if (text.includes("blog")) links.blog = href;
        else if (
          !links.website &&
          !href.includes("coinmarketcap.com/") &&
          !href.includes("coingecko.com/en") &&
          !href.includes("docs.etherscan.io")
        ) {
          links.website = href;
        }
      }
      let decimals = null;
      const contractRow = [...summaryRoot.querySelectorAll(".row")].find((row) =>
        norm(row.innerText).includes("WITH") && norm(row.innerText).includes("DECIMALS"),
      );
      if (contractRow) {
        const chunk = norm(contractRow.innerText);
        const parts = chunk.split(" ");
        for (const part of parts) {
          let digitsOnly = true;
          for (const ch of part) {
            if (ch < "0" || ch > "9") {
              digitsOnly = false;
              break;
            }
          }
          if (digitsOnly && part.length > 0) {
            decimals = part;
            break;
          }
        }
      }
      return {
        title: document.title,
        overview,
        decimals,
        links,
        badges: [...document.querySelectorAll(".badge")].map((b) => norm(b.innerText)).filter(Boolean).slice(0, 20),
        page_text: pageText.slice(0, 12000),
        page_text_len: pageText.length,
      };
    });
      const blocked = (detail?.title || "").toLowerCase().includes("just a moment");
      if (!blocked && (detail?.page_text_len || 0) > 400) {
        htmlPath = path.join(tokensDir, `${address.toLowerCase()}.html`);
        try {
          const html = await page.content();
          await fs.writeFile(htmlPath, html, "utf8");
        } catch {
          /* non-fatal */
        }
        break;
      }
      detail = null;
      if (attempt < 2) {
        await page.waitForTimeout(3000 + attempt * 2000);
      }
    }
    if (!detail) {
      detail = {
        title: "",
        overview: {},
        decimals: null,
        links: {},
        badges: [],
        page_text: "",
        page_text_len: 0,
        blocked: true,
      };
    }
    const record = {
      address,
      listing,
      detail,
      html_path: htmlPath ? path.basename(htmlPath) : "",
      harvested_at: new Date().toISOString(),
      source: tokenUrl,
    };
    harvested.push(record);
    await fs.writeFile(path.join(tokensDir, `${address.toLowerCase()}.json`), JSON.stringify(record, null, 2), "utf8");
    if (pauseMs) await page.waitForTimeout(pauseMs);
  }

  await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});

  const manifest = {
    mode: "catalog",
    engine: "playwright",
    start_url: startUrl,
    listing_label: listingLabel || null,
    limits: { max_pages: maxPages, max_tokens: maxTokens, pause_ms: pauseMs },
    listing_token_count: tokenMap.size,
    harvested_count: harvested.length,
    addresses,
    harvested_at: new Date().toISOString(),
    output_dir: outDir,
  };

  const csvHeader = [
    "address",
    "symbol",
    "name",
    "price",
    "onchain_market_cap",
    "circulating_market_cap",
    "holders",
    "website",
    "coingecko",
  ];
  const csvLines = [csvHeader.join(",")];
  for (const row of harvested) {
    const esc = (v) => `"${String(v || "").replace(/"/g, '""')}"`;
    csvLines.push(
      [
        row.address,
        row.listing?.symbol,
        row.listing?.name,
        row.listing?.price || row.detail?.overview?.price,
        row.listing?.onchain_market_cap || row.detail?.overview?.onchain_market_cap,
        row.listing?.circulating_market_cap || row.detail?.overview?.circulating_supply_market_cap,
        row.listing?.holders || row.detail?.overview?.holders,
        row.detail?.links?.website,
        row.detail?.links?.coingecko,
      ]
        .map(esc)
        .join(","),
    );
  }
  await fs.writeFile(path.join(outDir, "tokens_panel.csv"), `${csvLines.join("\n")}\n`, "utf8");
  await fs.writeFile(path.join(outDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
  return manifest;
}

function parseTokenAddress(tokenUrl) {
  const parts = new URL(tokenUrl).pathname.split("/token/");
  if (parts.length < 2) {
    throw new Error(`not an Etherscan token URL: ${tokenUrl}`);
  }
  const address = parts[1].split(/[?#]/)[0].toLowerCase();
  if (!address.startsWith("0x") || address.length !== 42) {
    throw new Error(`invalid token address in URL: ${tokenUrl}`);
  }
  return address;
}

async function writeHarvestArtifacts(outDir, harvested, manifestBase) {
  const csvHeader = [
    "address",
    "symbol",
    "name",
    "price",
    "onchain_market_cap",
    "circulating_market_cap",
    "holders",
    "website",
    "coingecko",
  ];
  const csvLines = [csvHeader.join(",")];
  for (const row of harvested) {
    const esc = (v) => `"${String(v || "").replace(/"/g, '""')}"`;
    csvLines.push(
      [
        row.address,
        row.listing?.symbol,
        row.listing?.name,
        row.listing?.price || row.detail?.overview?.price,
        row.listing?.onchain_market_cap || row.detail?.overview?.onchain_market_cap,
        row.listing?.circulating_market_cap || row.detail?.overview?.circulating_supply_market_cap,
        row.listing?.holders || row.detail?.overview?.holders,
        row.detail?.links?.website,
        row.detail?.links?.coingecko,
      ]
        .map(esc)
        .join(","),
    );
  }
  await fs.writeFile(path.join(outDir, "tokens_panel.csv"), `${csvLines.join("\n")}\n`, "utf8");
  const manifest = {
    ...manifestBase,
    harvested_count: harvested.length,
    addresses: harvested.map((r) => r.address),
    harvested_at: new Date().toISOString(),
    output_dir: outDir,
  };
  await fs.writeFile(path.join(outDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
  return manifest;
}

async function harvestTokenDetail(page, address, listing, tokenUrl, tokensDir, timeoutMs) {
  let detail = null;
  let htmlPath = "";
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto(tokenUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    const ready = await waitForTokenDetail(page, Math.min(timeoutMs, 90000));
    if (!ready) {
      if (attempt < 2) {
        await page.waitForTimeout(3000 + attempt * 2000);
        continue;
      }
      break;
    }
    detail = await page.evaluate(() => {
      const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
      const root =
        document.querySelector("#ContentPlaceHolder1_divSummary") ||
        document.querySelector("#ContentPlaceHolder1") ||
        document.querySelector("#content") ||
        document.body;
      const summaryRoot = root;
      const overview = {};
      for (const row of summaryRoot.querySelectorAll(".row")) {
        const labelEl = row.querySelector(".col-md-4, .col-lg-4, .col-4");
        const valueEl = row.querySelector(".col-md-8, .col-lg-8, .col-8");
        if (!labelEl || !valueEl) continue;
        const label = norm(labelEl.innerText).toUpperCase();
        const value = norm(valueEl.innerText);
        if (!value) continue;
        if (label.includes("MAX TOTAL SUPPLY")) overview.max_total_supply = value;
        else if (label === "HOLDERS" || label.startsWith("HOLDERS ")) overview.holders = value;
        else if (label.includes("TRANSFERS TOTAL 24H")) overview.transfers_total_24h = value;
        else if (label === "PRICE" || label.startsWith("PRICE ")) overview.price = value;
        else if (label.includes("ONCHAIN MARKET CAP")) overview.onchain_market_cap = value;
        else if (label.includes("CIRCULATING SUPPLY MARKET CAP")) overview.circulating_supply_market_cap = value;
      }
      for (const dl of summaryRoot.querySelectorAll("dl")) {
        const dts = [...dl.querySelectorAll("dt")];
        const dds = [...dl.querySelectorAll("dd")];
        for (let i = 0; i < dts.length; i += 1) {
          const label = norm(dts[i]?.innerText).toUpperCase();
          const value = norm(dds[i]?.innerText);
          if (!label || !value) continue;
          if (label.includes("HOLDERS")) overview.holders = overview.holders || value;
          if (label.includes("TRANSFERS")) overview.transfers_total_24h = overview.transfers_total_24h || value;
          if (label.includes("SUPPLY")) overview.max_total_supply = overview.max_total_supply || value;
        }
      }
      const pageText = norm(root.innerText || "");
      const pick = (re) => {
        const m = pageText.match(re);
        return m ? norm(m[1]) : "";
      };
      if (!overview.holders) overview.holders = pick(/HOLDERS\s+([\d,]+(?:\s+[\d.]+%)?)/i);
      if (!overview.transfers_total_24h) overview.transfers_total_24h = pick(/TRANSFERS\s+TOTAL\s+24H\s+([\d,]+)/i);
      if (!overview.max_total_supply) overview.max_total_supply = pick(/MAX\s+TOTAL\s+SUPPLY\s+([\d,.\sA-Z]+)/i);
      const links = {};
      for (const a of summaryRoot.querySelectorAll('a[href^="http"]')) {
        const text = norm(a.innerText).toLowerCase();
        const href = a.href;
        if (!href || href.includes("etherscan.io")) continue;
        if (text.includes("coingecko") && href.includes("/coins/")) links.coingecko = href;
        else if (text.includes("coinmarketcap") && href.includes("/currencies/")) links.coinmarketcap = href;
        else if (text.includes("twitter") || text === "x (twitter)") links.twitter = href;
        else if (text.includes("telegram")) links.telegram = href;
        else if (text.includes("whitepaper")) links.whitepaper = href;
        else if (text.includes("reddit")) links.reddit = href;
        else if (text.includes("linkedin")) links.linkedin = href;
        else if (text.includes("facebook")) links.facebook = href;
        else if (text.includes("blog")) links.blog = href;
        else if (
          !links.website &&
          !href.includes("coinmarketcap.com/") &&
          !href.includes("coingecko.com/en") &&
          !href.includes("docs.etherscan.io")
        ) {
          links.website = href;
        }
      }
      let decimals = null;
      const contractRow = [...summaryRoot.querySelectorAll(".row")].find((row) =>
        norm(row.innerText).includes("WITH") && norm(row.innerText).includes("DECIMALS"),
      );
      if (contractRow) {
        const chunk = norm(contractRow.innerText);
        const parts = chunk.split(" ");
        for (const part of parts) {
          let digitsOnly = true;
          for (const ch of part) {
            if (ch < "0" || ch > "9") {
              digitsOnly = false;
              break;
            }
          }
          if (digitsOnly && part.length > 0) {
            decimals = part;
            break;
          }
        }
      }
      return {
        title: document.title,
        overview,
        decimals,
        links,
        badges: [...document.querySelectorAll(".badge")].map((b) => norm(b.innerText)).filter(Boolean).slice(0, 20),
        page_text: pageText.slice(0, 12000),
        page_text_len: pageText.length,
      };
    });
    const blocked = (detail?.title || "").toLowerCase().includes("just a moment");
    if (!blocked && (detail?.page_text_len || 0) > 400) {
      htmlPath = path.join(tokensDir, `${address.toLowerCase()}.html`);
      try {
        const html = await page.content();
        await fs.writeFile(htmlPath, html, "utf8");
      } catch {
        /* non-fatal */
      }
      break;
    }
    detail = null;
    if (attempt < 2) {
      await page.waitForTimeout(3000 + attempt * 2000);
    }
  }
  if (!detail) {
    detail = {
      title: "",
      overview: {},
      decimals: null,
      links: {},
      badges: [],
      page_text: "",
      page_text_len: 0,
      blocked: true,
    };
  }
  const record = {
    address,
    listing,
    detail,
    html_path: htmlPath ? path.basename(htmlPath) : "",
    harvested_at: new Date().toISOString(),
    source: tokenUrl,
  };
  await fs.writeFile(path.join(tokensDir, `${address.toLowerCase()}.json`), JSON.stringify(record, null, 2), "utf8");
  return record;
}

async function playwrightSingleToken(tokenUrl, outDir, timeoutMs) {
  const { chromium } = await loadPlaywright();
  if (!chromium) {
    throw new Error("token mode requires Playwright");
  }
  const address = parseTokenAddress(tokenUrl);
  const tokensDir = path.join(outDir, "tokens");
  await fs.mkdir(tokensDir, { recursive: true });
  const { browser, context, persistent } = await launchCatalogBrowser(chromium, tokenUrl);
  await installNetworkGuard(context);
  if (isBlockedUrl(tokenUrl)) {
    throw new Error(`blocked non-public url: ${tokenUrl}`);
  }
  const page = context.pages()[0] || (await context.newPage());
  page.setDefaultNavigationTimeout(timeoutMs);
  page.setDefaultTimeout(timeoutMs);
  const listing = {
    address,
    name: "",
    symbol: "",
    href: tokenUrl,
  };
  const record = await harvestTokenDetail(page, address, listing, tokenUrl, tokensDir, timeoutMs);
  if (record.detail?.title) {
    listing.name = record.detail.title.replace(/\s*\|\s*Etherscan.*$/i, "").trim();
  }
  await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  if (record.detail?.blocked || (record.detail?.page_text_len || 0) < 400) {
    throw new Error("token detail blocked or empty (Cloudflare) — use xvfb-run + PLAYWRIGHT_CHANNEL=chrome");
  }
  return writeHarvestArtifacts(outDir, [record], {
    mode: "token",
    engine: "playwright",
    start_url: tokenUrl,
    listing_token_count: 1,
  });
}

async function main() {
  const config = parseArgs(process.argv);
  const timeoutMs = Number.parseInt(process.env.PLAYWRIGHT_TIMEOUT_MS || "90000", 10);
  const staging = process.env.SPECTATOR_STAGING || process.cwd();
  const slug = slugFromUrl(config.url);

  if (config.mode === "token") {
    const outDir = config.out || path.join(staging, "scrapes", slug, "token");
    await fs.mkdir(outDir, { recursive: true });
    const manifest = await playwrightSingleToken(config.url, outDir, timeoutMs);
    console.log(
      JSON.stringify({
        ok: true,
        url: config.url,
        mode: "token",
        out: outDir,
        manifest: path.join(outDir, "manifest.json"),
        harvested: manifest.harvested_count,
      }),
    );
    return;
  }

  if (config.mode === "catalog") {
    const outDir = config.out || path.join(staging, "scrapes", slug, "catalog");
    await fs.mkdir(outDir, { recursive: true });
    const manifest = await playwrightCatalog(config.url, { ...config, out: outDir }, timeoutMs);
    if (!manifest.harvested_count) {
      throw new Error("catalog harvest produced 0 tokens — listing or detail pages likely blocked");
    }
    console.log(
      JSON.stringify({
        ok: true,
        url: config.url,
        mode: "catalog",
        out: outDir,
        manifest: path.join(outDir, "manifest.json"),
        harvested: manifest.harvested_count,
        listing_token_count: manifest.listing_token_count,
      }),
    );
    return;
  }

  const outPath = config.out || path.join(staging, "scrapes", slug, "extract.json");

  await fs.mkdir(path.dirname(outPath), { recursive: true });
  const payload = await playwrightExtract(config.url, config.mode, timeoutMs);
  payload.mode = config.mode;
  payload.output_path = outPath;
  await fs.writeFile(outPath, JSON.stringify(payload, null, 2), "utf8");
  console.log(JSON.stringify({ ok: true, url: config.url, out: outPath, links: payload.links?.length || 0 }));
}

main().catch((err) => {
  console.error(JSON.stringify({ ok: false, error: err instanceof Error ? err.message : String(err) }));
  process.exit(1);
});
