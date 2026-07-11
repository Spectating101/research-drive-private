import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  boundProbeResult,
  classifyProbeEvidence,
  deriveUnknowns,
  primaryVerifiedFacts,
  probeImpliesAcquisition,
  probeImpliesLegalClearance,
} from "./discoverProbeEvidence.js";
import { classifyDiscoverResult } from "./discoverTaxonomy.js";

const ROW = {
  candidate_key: "dataset:mops_financial_statements_ext",
  dataset_id: "mops_financial_statements_ext",
  title: "MOPS financial statements",
  source: "MOPS",
  url: "https://mops.twse.com.tw/example",
};

describe("boundProbeResult", () => {
  it("ignores mismatched candidate_key", () => {
    const probe = boundProbeResult(ROW, {
      loading: false,
      result: {
        candidate_key: "url:https://other.example",
        summary: "should ignore",
        resolved_url: "https://other.example",
      },
    });
    assert.equal(probe, null);
  });

  it("accepts matching probeState result", () => {
    const probe = boundProbeResult(ROW, {
      loading: false,
      candidateKey: ROW.candidate_key,
      result: {
        candidate_key: ROW.candidate_key,
        resolved_url: "https://mops.twse.com.tw/example",
        http_status: 200,
      },
    });
    assert.ok(probe);
    assert.equal(probe.http_status, 200);
  });

  it("does not treat loading probe as bound evidence", () => {
    const probe = boundProbeResult(ROW, {
      loading: true,
      result: { candidate_key: ROW.candidate_key, http_status: 200 },
    });
    assert.equal(probe, null);
  });
});

describe("classifyProbeEvidence", () => {
  it("marks HTTP/content facts verified and access_mode conclusions inferred", () => {
    const classified = classifyProbeEvidence(ROW, {
      candidate_key: ROW.candidate_key,
      resolved_url: "https://mops.twse.com.tw/data.csv",
      http_status: 200,
      summary: "Looks collectable and open",
      connector: {
        connector_id: "example_com_data",
        spec: {
          access_mode: "direct_file",
          content_type: "text/csv",
          discovered_files: [{ url: "https://mops.twse.com.tw/data.csv" }],
        },
      },
    });
    const verified = classified.verified.map((f) => f.label).join(" | ");
    const inferred = classified.inferred.map((f) => f.label).join(" | ");
    const model = classified.model.map((f) => f.label).join(" | ");
    assert.match(verified, /MOPS publisher|mops\.twse/i);
    assert.match(verified, /HTTP endpoint responded \(200\)/);
    assert.match(verified, /text\/csv/);
    assert.match(inferred, /direct file|machine-readable/i);
    assert.match(model, /Probe summary/);
    assert.ok(classified.technical.some((f) => f.label === "Connector ID"));
    assert.equal(
      classified.verified.some((f) => /legal|open license|acquirable|research-ready/i.test(f.label)),
      false,
    );
  });

  it("does not promote probe summary to verified", () => {
    const classified = classifyProbeEvidence(ROW, {
      candidate_key: ROW.candidate_key,
      summary: "Verified source — open and collectable",
    });
    assert.equal(
      classified.verified.some((f) => /open and collectable|Verified source/i.test(f.label + f.detail)),
      false,
    );
    assert.ok(classified.model.some((f) => f.kind === "model" && /Probe summary/i.test(f.label)));
  });
});

describe("honesty guards", () => {
  it("HTTP success never implies acquisition or legal clearance", () => {
    assert.equal(probeImpliesAcquisition({ http_status: 200 }), false);
    assert.equal(probeImpliesLegalClearance({ http_status: 200 }), false);
  });
});

describe("unknowns + primary verified", () => {
  it("surfaces unknowns before probe", () => {
    const taxonomy = classifyDiscoverResult(ROW, new Set());
    const unknowns = deriveUnknowns(ROW, taxonomy, { verified: [] }, false);
    assert.ok(unknowns.some((u) => /not probed/i.test(u)));
    assert.ok(unknowns.some((u) => /Acquisition constraints/i.test(u)));
  });

  it("caps primary verified facts", () => {
    const classified = classifyProbeEvidence(ROW, {
      candidate_key: ROW.candidate_key,
      resolved_url: "https://mops.twse.com.tw/data.csv",
      http_status: 200,
      connector: {
        spec: {
          content_type: "text/html",
          discovered_files: ["a", "b"],
          etag: "x",
          last_modified: "y",
        },
      },
    });
    const primary = primaryVerifiedFacts(classified);
    assert.ok(primary.length >= 2 && primary.length <= 5);
  });
});
