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
} from "./candidateKey.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = join(__dirname, "fixtures", "candidate_key_vectors.json");
const EXPECTED_FIXTURE_SHA256 =
  "8170d7de2ba0b0d3a4cf5d71102319869b6e4337a54d025c8575ad1467358edc";
const fixtureBytes = readFileSync(FIXTURE_PATH);
const vectors = JSON.parse(fixtureBytes.toString("utf8"));

describe("shared golden fixture", () => {
  it("loads candidate_key_vectors.json with stable SHA-256", () => {
    const digest = createHash("sha256").update(fixtureBytes).digest("hex");
    assert.equal(digest, EXPECTED_FIXTURE_SHA256);
    assert.equal(vectors.version, 1);
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
