/**
 * Unit tests for Discover candidateKey (D0.1 — shared golden fixture).
 * Run: node --test drive/src/v2/candidateKey.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  candidateKey,
  canonicalizeDoi,
  canonicalizeUrl,
  discoverCandidateUrl,
  isCandidateQueued,
  jobMatchesCandidate,
  normalizeTitle,
  slugifyProvider,
} from "./candidateKey.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = join(__dirname, "fixtures", "candidate_key_vectors.json");
const EXPECTED_FIXTURE_SHA256 =
  "b702dccd624a569d735f6f82ad7993eec602c1db8e490d5a7d96216227539f68";
const fixtureBytes = readFileSync(FIXTURE_PATH);
const vectors = JSON.parse(fixtureBytes.toString("utf8"));

describe("shared golden fixture", () => {
  it("loads candidate_key_vectors.json with stable SHA-256", () => {
    const digest = createHash("sha256").update(fixtureBytes).digest("hex");
    assert.equal(digest, EXPECTED_FIXTURE_SHA256);
    assert.equal(vectors.version, 2);
    assert.ok(vectors.candidate_key.length >= 8);
  });
});

describe("canonicalizeDoi (fixture)", () => {
  for (const row of vectors.canonicalize_doi) {
    it(row.input, () => {
      assert.equal(canonicalizeDoi(row.input), row.expected);
    });
  }
});

describe("canonicalizeUrl (fixture)", () => {
  for (const row of vectors.canonicalize_url) {
    it(row.input, () => {
      assert.equal(canonicalizeUrl(row.input), row.expected);
    });
  }
});

describe("slugifyProvider (fixture)", () => {
  for (const row of vectors.provider_slug || []) {
    it(JSON.stringify(row.input), () => {
      assert.equal(slugifyProvider(row.input), row.expected);
    });
  }
});

describe("candidateKey (fixture)", () => {
  for (const row of vectors.candidate_key) {
    it(row.name, () => {
      assert.equal(candidateKey(row.row), row.expected);
    });
  }

  it("different providers with identical titles do not collide", () => {
    const a = vectors.candidate_key.find((r) => r.name === "title_mops");
    const b = vectors.candidate_key.find((r) => r.name === "title_twse");
    assert.notEqual(candidateKey(a.row), candidateKey(b.row));
  });

  it("non-Latin providers with identical titles do not collide", () => {
    const a = vectors.candidate_key.find((r) => r.name === "unicode_title_provider_mops");
    const b = vectors.candidate_key.find((r) => r.name === "unicode_title_provider_twse");
    assert.notEqual(candidateKey(a.row), candidateKey(b.row));
  });

  it("identical external IDs from non-Latin providers stay namespaced", () => {
    const a = vectors.candidate_key.find((r) => r.name === "source_ext_id_nonlatin_a");
    const b = vectors.candidate_key.find((r) => r.name === "source_ext_id_nonlatin_b");
    assert.notEqual(candidateKey(a.row), candidateKey(b.row));
  });
});

describe("action URL alignment (fixture)", () => {
  for (const row of vectors.action_url) {
    it(row.name, () => {
      assert.equal(discoverCandidateUrl(row.row), row.expected_url);
      assert.equal(candidateKey(row.row), row.expected_key);
    });
  }
});

describe("queued association", () => {
  it("does not match similar titles", () => {
    const row = { title: "MOPS financial statements", url: "https://a.example/mops", source: "MOPS" };
    const job = {
      status: "pending_approval",
      plan: { title: "MOPS financial statements extended" },
      request: {},
    };
    assert.equal(jobMatchesCandidate(job, row), false);
    assert.equal(isCandidateQueued(row, [job]), false);
  });

  it("matches exact candidate_key", () => {
    const row = {
      candidate_key: "url:https://a.example/mops",
      title: "MOPS financial statements",
      url: "https://a.example/mops",
    };
    const job = {
      status: "queued",
      candidate_key: "url:https://a.example/mops",
      request: { candidate_key: "url:https://a.example/mops" },
    };
    assert.equal(isCandidateQueued(row, [job]), true);
  });

  it("matches connector_id", () => {
    const row = { title: "X", url: "https://a.example/x", connector_id: "abc123" };
    const job = { status: "running", request: { connector_id: "abc123" } };
    assert.equal(isCandidateQueued(row, [job]), true);
  });
});

describe("normalizeTitle", () => {
  it("collapses whitespace", () => {
    assert.equal(normalizeTitle("  Foo   Bar "), "foo bar");
  });
});
