/**
 * Unit tests for Discover candidateKey (D0a).
 * Run: node --test drive/src/v2/candidateKey.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  candidateKey,
  canonicalizeDoi,
  canonicalizeUrl,
  isCandidateQueued,
  jobMatchesCandidate,
  normalizeTitle,
} from "./candidateKey.js";

describe("canonicalizeDoi", () => {
  it("strips prefixes and lowercases", () => {
    assert.equal(canonicalizeDoi("DOI:10.5281/ZENODO.1"), "10.5281/zenodo.1");
    assert.equal(canonicalizeDoi("https://doi.org/10.5281/zenodo.1"), "10.5281/zenodo.1");
    assert.equal(canonicalizeDoi("http://dx.doi.org/10.5281/zenodo.1"), "10.5281/zenodo.1");
  });
});

describe("canonicalizeUrl", () => {
  it("lowercases host, drops fragment and default ports", () => {
    assert.equal(
      canonicalizeUrl("HTTPS://Example.COM:443/path#frag"),
      "https://example.com/path",
    );
    assert.equal(
      canonicalizeUrl("http://Example.COM:80/a?b=1"),
      "http://example.com/a?b=1",
    );
  });
});

describe("candidateKey precedence", () => {
  it("uses server candidate_key first", () => {
    assert.equal(
      candidateKey({ candidate_key: "dataset:server", dataset_id: "other", title: "T" }),
      "dataset:server",
    );
  });

  it("prefers dataset_id over title/url/doi", () => {
    assert.equal(
      candidateKey({
        dataset_id: "mops_financial_statements_ext",
        title: "MOPS financial statements",
        doi: "10.1/x",
        url: "https://mops.twse.com.tw/example",
      }),
      "dataset:mops_financial_statements_ext",
    );
  });

  it("uses DOI before URL and title", () => {
    assert.equal(
      candidateKey({
        title: "Some paper",
        doi: "https://doi.org/10.5281/ZENODO.9",
        url: "https://example.com/x",
      }),
      "doi:10.5281/zenodo.9",
    );
  });

  it("uses source external id for huggingface", () => {
    assert.equal(
      candidateKey({ kind: "huggingface", id: "org/demo", title: "Demo" }),
      "source:huggingface:org/demo",
    );
  });

  it("uses URL before title", () => {
    assert.equal(
      candidateKey({
        title: "Example open dataset",
        url: "HTTPS://Example.com/dataset#x",
        source: "web",
      }),
      "url:https://example.com/dataset",
    );
  });

  it("namespaces title fallback by provider", () => {
    const a = candidateKey({ title: "Same Title", source: "MOPS" });
    const b = candidateKey({ title: "Same Title", source: "TWSE" });
    assert.equal(a, "title:mops:same title");
    assert.equal(b, "title:twse:same title");
    assert.notEqual(a, b);
  });

  it("does not use raw title alone", () => {
    const key = candidateKey({ title: "Alone" });
    assert.match(key, /^title:/);
    assert.ok(!key.startsWith("Alone"));
  });
});

describe("identity stability across surfaces", () => {
  const row = {
    title: "MOPS financial statements (Taiwan)",
    url: "https://mops.twse.com.tw/example",
    source: "MOPS",
    doi: "",
  };

  it("same key for row / selection / rail / probe / add-to-lab", () => {
    const k = candidateKey(row);
    assert.equal(candidateKey({ ...row }), k);
    assert.equal(candidateKey({ ...row, discover_state: { key: "probe_ready" } }), k);
  });
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
