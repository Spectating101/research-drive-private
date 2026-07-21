import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildDiscoverEvaluation,
  evaluationActions,
  usefulForLine,
} from "./discoverEvaluation.js";
import { classifyDiscoverResult } from "./discoverTaxonomy.js";

describe("usefulForLine", () => {
  it("synthesizes from description + grain without fit language", () => {
    const line = usefulForLine({
      description: "Listed-company financial statements",
      grain: "issuer-quarter",
    });
    assert.match(line, /Listed-company financial statements/i);
    assert.match(line, /issuer-quarter/);
    assert.doesNotMatch(line, /Faculty finance fit|Strong finance/i);
  });

  it("falls back when metadata is thin", () => {
    assert.equal(usefulForLine({}), "Research use is not yet described.");
  });
});

describe("evaluationActions", () => {
  it("local query-ready primary is Open in Library", () => {
    const taxonomy = { key: "local-query-ready", label: "In lab · Query ready" };
    const actions = evaluationActions({}, taxonomy);
    assert.equal(actions.primary.id, "open_library");
    assert.equal(actions.primary.label, "Open in Library");
  });

  it("licensed/manual does not use Request this evidence as primary", () => {
    const taxonomy = { key: "licensed-manual", label: "Licensed / manual access" };
    const actions = evaluationActions({}, taxonomy, { hasProbeUrl: true });
    assert.equal(actions.primary.id, "review_access");
    assert.ok(!actions.secondary.some((a) => a.id === "add_lab"));
  });

  it("external discoverable with URL probes first; Request this evidence is secondary", () => {
    const taxonomy = { key: "external-discoverable", label: "External · Available to inspect" };
    const actions = evaluationActions({}, taxonomy, { hasProbeUrl: true });
    assert.equal(actions.primary.id, "probe");
    assert.ok(actions.secondary.some((a) => a.id === "add_lab" && a.label === "Request this evidence"));
  });

  it("external acquirable primary is Request this evidence", () => {
    const taxonomy = { key: "external-acquirable", label: "External · Acquisition available" };
    const actions = evaluationActions({}, taxonomy, { hasProbeUrl: true, probed: false });
    assert.equal(actions.primary.id, "add_lab");
    assert.equal(actions.primary.label, "Request this evidence");
  });

  it("external-probed primary is Preview, not Ask-as-review", () => {
    const taxonomy = { key: "external-probed", label: "External · Probed" };
    const actions = evaluationActions({}, taxonomy, { hasProbeUrl: true, probed: true });
    assert.equal(actions.primary.id, "preview");
    assert.equal(actions.primary.label, "Preview source");
    assert.ok(actions.secondary.some((a) => a.id === "ask" && a.label === "Ask about this source"));
    assert.equal(actions.secondary.some((a) => /Review evidence/i.test(a.label)), false);
  });
});

describe("buildDiscoverEvaluation", () => {
  it("pre-probe candidate does not display verified probe claims", () => {
    const row = {
      candidate_key: "url:https://example.com/index.csv",
      title: "Bare public CSV index",
      source: "Web",
      url: "https://example.com/index.csv",
      description: "Public index",
    };
    const evaluation = buildDiscoverEvaluation(row, new Set(), {
      loading: false,
      result: null,
    });
    assert.equal(evaluation.hasProbe, false);
    assert.deepEqual(evaluation.verified, []);
    assert.ok(evaluation.unknowns.some((u) => /not probed/i.test(u)));
    assert.equal(evaluation.actions.primary.id, "probe");
    assert.match(evaluation.decision.headline, /Available to inspect/i);
  });

  it("matching probe surfaces verified facts and demotes connector to technical", () => {
    const row = {
      candidate_key: "url:https://example.com/index.csv",
      title: "Bare public CSV index",
      source: "Web",
      url: "https://example.com/index.csv",
    };
    const evaluation = buildDiscoverEvaluation(row, new Set(), {
      loading: false,
      candidateKey: row.candidate_key,
      result: {
        candidate_key: row.candidate_key,
        resolved_url: "https://example.com/index.csv",
        http_status: 200,
        summary: "direct_file source",
        connector: {
          connector_id: "example_com_data",
          spec: { access_mode: "direct_file", content_type: "text/csv", discovered_files: ["a"] },
        },
      },
    });
    assert.equal(evaluation.hasProbe, true);
    assert.ok(evaluation.verified.length >= 2);
    assert.ok(evaluation.inferred.some((l) => /direct file|machine-readable/i.test(l)));
    assert.ok(evaluation.technical.some((f) => f.label === "Connector ID"));
    assert.equal(evaluation.taxonomyKey, "external-probed");
    assert.doesNotMatch(evaluation.verified.join(" "), /legal|open license|acquirable/i);
  });

  it("mismatched probe is ignored", () => {
    const row = {
      candidate_key: "url:https://example.com/a",
      title: "A",
      url: "https://example.com/a",
    };
    const evaluation = buildDiscoverEvaluation(row, new Set(), {
      loading: false,
      result: {
        candidate_key: "url:https://example.com/b",
        http_status: 200,
        connector: { spec: { content_type: "text/csv" } },
      },
    });
    assert.equal(evaluation.hasProbe, false);
    assert.deepEqual(evaluation.verified, []);
  });

  it("local query-ready decision and action", () => {
    const row = {
      dataset_id: "gdelt_asia_daily_country_panel",
      title: "Asia daily news-risk panel",
      analysis_readiness: "instant",
      local_root: "research_panels/gdelt",
    };
    const labIds = new Set(["gdelt_asia_daily_country_panel"]);
    const taxonomy = classifyDiscoverResult(row, labIds);
    assert.equal(taxonomy.key, "local-query-ready");
    const evaluation = buildDiscoverEvaluation(row, labIds, null);
    assert.equal(evaluation.actions.primary.label, "Open in Library");
    assert.match(evaluation.decision.headline, /Query ready/i);
  });
});
