#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST_PATH = path.join(ROOT, "release", "research-drive-rc2.json");
const ARTIFACT_DIR = path.join(ROOT, "artifacts");
const ATTESTATION_PATH = path.join(ARTIFACT_DIR, "rc2-release-verification.json");
const REQUIRED_FILES = [
  "README.md",
  "docs/releases/RESEARCH_DRIVE_RC2.md",
  "docs/releases/RC2_OPERATOR_QUICKSTART.md",
  "e2e/rc2-release-journey.spec.js",
  ".github/workflows/rc2-release.yml",
  ".github/workflows/rc2-publish.yml",
  "scripts/package_rc2_release.sh",
];
const ALLOWED_RELEASE_CHANGES = [
  /^README\.md$/,
  /^package\.json$/,
  /^\.gitignore$/,
  /^release\//,
  /^docs\/releases\//,
  /^scripts\/verify_rc2_release\.mjs$/,
  /^scripts\/package_rc2_release\.sh$/,
  /^e2e\/rc2-release-journey\.spec\.js$/,
  /^\.github\/workflows\/rc2-release\.yml$/,
  /^\.github\/workflows\/rc2-publish\.yml$/,
];
const SHA_RE = /^[0-9a-f]{40}$/;
const failures = [];
const notes = [];

function assert(condition, message) {
  if (!condition) failures.push(message);
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function git(args, { allowFailure = false } = {}) {
  const result = spawnSync("git", args, { cwd: ROOT, encoding: "utf8" });
  if (result.status !== 0 && !allowFailure) {
    failures.push(`git ${args.join(" ")} failed: ${(result.stderr || result.stdout || "unknown error").trim()}`);
  }
  return result;
}

function currentHead() {
  const result = git(["rev-parse", "HEAD"], { allowFailure: true });
  return result.status === 0 ? result.stdout.trim() : "";
}

function exitWithResult() {
  if (failures.length) {
    console.error("Research Drive RC2 release verification failed:\n");
    for (const failure of failures) console.error(`- ${failure}`);
    if (notes.length) {
      console.error("\nNotes:");
      for (const note of notes) console.error(`- ${note}`);
    }
    process.exit(1);
  }
  console.log("Research Drive RC2 release verification passed.");
  for (const note of notes) console.log(`- ${note}`);
}

assert(fs.existsSync(MANIFEST_PATH), "release manifest is missing");
let manifest = null;
try {
  manifest = readJson(MANIFEST_PATH);
} catch (error) {
  failures.push(`release manifest is not valid JSON: ${error.message}`);
}

if (process.argv.includes("--attestation-only")) {
  assert(fs.existsSync(ATTESTATION_PATH), "release verification attestation is missing");
  let attestation = null;
  try {
    attestation = readJson(ATTESTATION_PATH);
  } catch (error) {
    failures.push(`release verification attestation is invalid: ${error.message}`);
  }
  const head = currentHead();
  assert(SHA_RE.test(head), "current git HEAD is unavailable");
  if (attestation && manifest) {
    assert(attestation.release_id === manifest.release_id, "attestation release identity does not match manifest");
    assert(attestation.head_sha === head, "checkout HEAD changed after release verification");
    assert(attestation.public_product_sha === manifest.pins?.public_product_sha, "attested public product SHA does not match manifest");
    assert(attestation.private_runtime_sha === manifest.pins?.private_runtime_sha, "attested private runtime SHA does not match manifest");
    assert(attestation.ancestry_verified === true, "attestation does not prove accepted public ancestry");
    notes.push(`reused full-history attestation for ${head}`);
  }
  exitWithResult();
  process.exit(0);
}

for (const relative of REQUIRED_FILES) {
  assert(fs.existsSync(path.join(ROOT, relative)), `required release file is missing: ${relative}`);
}

if (manifest) {
  assert(manifest.schema_version === 1, "manifest schema_version must be 1");
  assert(manifest.release_id === "research-drive-rc2", "manifest release_id must be research-drive-rc2");
  assert(manifest.status === "live_accepted", "manifest status must remain live_accepted");
  assert(SHA_RE.test(manifest.pins?.public_product_sha || ""), "public product SHA must be a full lowercase 40-character SHA");
  assert(SHA_RE.test(manifest.pins?.private_runtime_sha || ""), "private runtime SHA must be a full lowercase 40-character SHA");
  assert(manifest.golden_asset?.dataset_id === "procured_src_b0a7ba3817a5", "golden dataset identity changed");
  assert(manifest.golden_asset?.readiness === "registered", "golden asset must remain registered");
  assert(manifest.golden_asset?.analysis_readiness === "metadata_search", "golden asset analysis readiness must remain metadata_search");
  assert(manifest.golden_asset?.query_ready === false, "golden asset must not be promoted to query_ready in RC2 metadata");
  assert(manifest.truth_constraints?.registered_is_not_query_ready === true, "registered/query-ready distinction must remain explicit");
  assert(manifest.truth_constraints?.release_verification_is_read_only === true, "RC2 verification must remain read-only");
}

const packageJson = readJson(path.join(ROOT, "package.json"));
assert(packageJson.researchDriveRelease === "rc2", "package.json must declare researchDriveRelease=rc2");
for (const script of ["release:verify", "release:test", "release:package"]) {
  assert(Boolean(packageJson.scripts?.[script]), `package.json script is missing: ${script}`);
}

let ancestryVerified = false;
let changedFileCount = 0;
const head = currentHead();
const inside = git(["rev-parse", "--is-inside-work-tree"], { allowFailure: true });
if (inside.status === 0 && manifest) {
  const accepted = manifest.pins.public_product_sha;
  const ancestry = git(["merge-base", "--is-ancestor", accepted, "HEAD"], { allowFailure: true });
  if (ancestry.status !== 0) {
    const required = process.env.YZU_REQUIRE_RELEASE_ANCESTRY === "1";
    const detail = (ancestry.stderr || ancestry.stdout || "").trim();
    const message = `accepted public SHA ${accepted} is not available as an ancestor of HEAD${detail ? `: ${detail}` : ""}`;
    if (required) failures.push(message);
    else notes.push(`${message}; rerun with a full-history checkout to enforce ancestry`);
  } else {
    ancestryVerified = true;
    const changed = git(["diff", "--name-only", `${accepted}..HEAD`], { allowFailure: true });
    if (changed.status === 0) {
      const changedFiles = changed.stdout.split(/\r?\n/).filter(Boolean);
      changedFileCount = changedFiles.length;
      const disallowed = changedFiles.filter(
        (file) => !ALLOWED_RELEASE_CHANGES.some((pattern) => pattern.test(file)),
      );
      assert(
        disallowed.length === 0,
        `release-packaging branch changed product/runtime files after the accepted SHA: ${disallowed.join(", ")}`,
      );
      const forbidden = changedFiles.filter(
        (file) => /(^|\/)(\.env|data_lake|secrets?|credentials?|tokens?)(\/|$)/i.test(file),
      );
      assert(forbidden.length === 0, `release boundary contains forbidden paths: ${forbidden.join(", ")}`);
      notes.push(`checked ${changedFiles.length} packaging change(s) against accepted public SHA`);
    }
  }
}

exitWithResult();

fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
fs.writeFileSync(
  ATTESTATION_PATH,
  `${JSON.stringify(
    {
      schema_version: 1,
      release_id: manifest.release_id,
      verified_at: new Date().toISOString(),
      head_sha: head,
      public_product_sha: manifest.pins.public_product_sha,
      private_runtime_sha: manifest.pins.private_runtime_sha,
      ancestry_verified: ancestryVerified,
      changed_files_checked: changedFileCount,
      verification_mode: "full_history",
    },
    null,
    2,
  )}\n`,
);

console.log(`- public product: ${manifest.pins.public_product_sha}`);
console.log(`- private runtime: ${manifest.pins.private_runtime_sha}`);
console.log(`- golden asset: ${manifest.golden_asset.dataset_id} (${manifest.golden_asset.readiness}, not query_ready)`);
console.log(`- attestation: ${path.relative(ROOT, ATTESTATION_PATH)}`);
