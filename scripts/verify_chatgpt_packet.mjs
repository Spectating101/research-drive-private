#!/usr/bin/env node
/**
 * Validate research-drive-chatgpt-packet.zip before ChatGPT upload.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const ZIP = path.join(ROOT, "research-drive-chatgpt-packet.zip");
const MIN_BYTES = 4.8 * 1024 * 1024;
const REQUIRED_SHOTS = [
  "docs/screenshots-review/desktop-discover-acquire-viewport.png",
  "docs/screenshots-review/desktop-discover-probe-viewport.png",
  "docs/screenshots-review/desktop-discover-ask-viewport.png",
];

function fail(msg) {
  console.error(`FAIL: ${msg}`);
  process.exit(1);
}

if (!fs.existsSync(ZIP)) {
  fail(`missing ${ZIP} — run npm run desk:capture:live && bash scripts/build_chatgpt_packet.sh`);
}

const stat = fs.statSync(ZIP);
if (stat.size <= MIN_BYTES) {
  fail(`zip too small: ${stat.size} bytes (need > ${MIN_BYTES})`);
}

const list = spawnSync("unzip", ["-l", ZIP], { cwd: ROOT, encoding: "utf8" });
if (list.status !== 0) fail("unzip -l failed");
const listing = list.stdout || "";

for (const entry of REQUIRED_SHOTS) {
  if (!listing.includes(entry)) {
    fail(`missing screenshot in zip: ${entry}`);
  }
}

const manifestPath = path.join(ROOT, "docs/screenshots-review/manifest.json");
if (!fs.existsSync(manifestPath)) {
  fail("missing docs/screenshots-review/manifest.json");
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
if (!manifest.acquire_query) {
  fail("manifest.json missing acquire_query");
}
if (!manifest.captured_at) {
  fail("manifest.json missing captured_at");
}

const hash = crypto.createHash("sha256");
hash.update(fs.readFileSync(ZIP));
const sha256 = hash.digest("hex");

const fileCount = (listing.match(/\.png$/gm) || []).length;

console.log("PASS: research-drive-chatgpt-packet.zip");
console.log(`  size: ${stat.size} bytes (${(stat.size / 1024 / 1024).toFixed(2)} MB)`);
console.log(`  sha256: ${sha256}`);
console.log(`  manifest.captured_at: ${manifest.captured_at}`);
console.log(`  manifest.acquire_query: ${manifest.acquire_query}`);
console.log(`  png count (zip listing): ${fileCount}`);
