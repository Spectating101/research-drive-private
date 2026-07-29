import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  classifyDiscoverResult,
  exceptionalRowPill,
  hasAcquisitionRoute,
  hasBoundProbe,
  holdingIdsFromCatalog,
  isQueryReady,
  orderDiscoverResults,
  taxonomyMatchesFilter,
} from "./discoverTaxonomy.js";

describe("discover taxonomy (D1 / D1.1)", () => {
  it("classifies query-ready local holdings", () => {
    const lab = new Set(["gdelt_asia"]);
    const c = classifyDiscoverResult(
      {
        dataset_id: "gdelt_asia",
        analysis_readiness: "instant",
        local_root: "panels/gdelt",
        materialization: { query_ready: true },
      },
      lab,
    );
    assert.equal(c.key, "local-query-ready");
    assert.match(c.label, /Query ready/i);
  });

  it("does not call connected local holdings query-ready", () => {
    const lab = new Set(["vault_csv"]);
    const c = classifyDiscoverResult(
      { dataset_id: "vault_csv", local_root: "vault/csv", in_vault: true },
      lab,
    );
    assert.equal(c.key, "local-connected");
    assert.notEqual(c.key, "local-query-ready");
  });

  it("does not equate catalogue membership or declared instant access with proven query readiness", () => {
    const rows = [
      {
        dataset_id: "catalogue",
        source_access_mode: "procurement_catalog",
        local_path: "data_lake/catalogue/card.json",
      },
      {
        dataset_id: "collected",
        source_access_mode: "procurement_catalog",
        local_path: "data_lake/procured/collected",
        materialization: { query_ready: false, resolved_path: "/vault/procured/collected" },
      },
      {
        dataset_id: "held",
        source_access_mode: "materialized_instant",
        local_path: "data_lake/held/data.json",
        analysis_readiness: "instant",
        materialization: { query_ready: false },
      },
      {
        dataset_id: "proved",
        source_access_mode: "materialized_instant",
        local_path: "data_lake/proved/data.json",
        materialization: { query_ready: true },
      },
    ];
    const lab = holdingIdsFromCatalog(rows);
    assert.deepEqual([...lab], ["collected", "held", "proved"]);
    assert.equal(classifyDiscoverResult(rows[1], lab).key, "local-connected");
    assert.equal(isQueryReady(rows[2]), false);
    assert.equal(classifyDiscoverResult(rows[2], lab).key, "local-connected");
    assert.equal(classifyDiscoverResult(rows[3], lab).key, "local-query-ready");
    assert.equal(classifyDiscoverResult(rows[0], lab).key, "external-discoverable");
  });

  it("marks registry metadata-only when no connection or query path", () => {
    const lab = new Set(["meta_only"]);
    const c = classifyDiscoverResult({ dataset_id: "meta_only", title: "Card only" }, lab);
    assert.equal(c.key, "local-metadata");
  });

  it("does not treat bare URL as probed or verified", () => {
    const c = classifyDiscoverResult({
      title: "Open page",
      url: "https://example.com/data",
      source: "Web",
    });
    assert.equal(c.key, "external-discoverable");
    assert.doesNotMatch(c.label, /Verified|Probed|Faculty finance/i);
  });

  it("promotes candidate-bound probe to External · Probed", () => {
    const c = classifyDiscoverResult({
      title: "Open page",
      url: "https://example.com/data",
      candidate_key: "url:https://example.com/data",
      probe_snapshot: {
        candidate_key: "url:https://example.com/data",
        connector: { id: "x" },
      },
    });
    assert.equal(c.key, "external-probed");
  });

  it("does not treat unbound probed:true as External · Probed", () => {
    const c = classifyDiscoverResult({
      title: "Open page",
      url: "https://example.com/data",
      probed: true,
      probe_result: { ok: true },
    });
    assert.equal(c.key, "external-discoverable");
    assert.equal(hasBoundProbe({ probed: true, probe_result: { ok: true } }), false);
  });

  it("does not treat probe success alone as acquisition available", () => {
    const c = classifyDiscoverResult({
      title: "Open page",
      url: "https://example.com/data",
      candidate_key: "url:https://example.com/data",
      probe_snapshot: { candidate_key: "url:https://example.com/data", ok: true },
    });
    assert.equal(c.key, "external-probed");
    assert.notEqual(c.key, "external-acquirable");
  });

  it("uses explicit collection route for acquisition available", () => {
    const c = classifyDiscoverResult({
      title: "MOPS",
      url: "https://mops.twse.com.tw",
      collect_via: "mops_tw",
    });
    assert.equal(c.key, "external-acquirable");
  });

  it("does not treat connector_id alone as acquisition available", () => {
    assert.equal(hasAcquisitionRoute({ connector_id: "example_com_data" }), false);
    const c = classifyDiscoverResult({
      title: "Probeable",
      url: "https://example.com/data",
      connector_id: "example_com_data",
    });
    assert.notEqual(c.key, "external-acquirable");
  });

  it("does not treat probe connector alone as acquisition available", () => {
    const row = {
      title: "Probed only",
      url: "https://example.com/data",
      candidate_key: "url:https://example.com/data",
      probe_connector_id: "probe_only",
      probe_snapshot: {
        candidate_key: "url:https://example.com/data",
        connector: { id: "probe_only" },
      },
    };
    assert.equal(hasAcquisitionRoute(row), false);
    assert.equal(classifyDiscoverResult(row).key, "external-probed");
  });

  it("treats collectable:true as acquisition available", () => {
    assert.equal(hasAcquisitionRoute({ collectable: true }), true);
    assert.equal(
      classifyDiscoverResult({ title: "X", url: "https://x.example", collectable: true }).key,
      "external-acquirable",
    );
  });

  it("treats explicit collection capability as acquisition available", () => {
    const row = {
      title: "Capable",
      url: "https://example.com/data",
      connector: { id: "c1", capabilities: ["collect_manifest"] },
    };
    assert.equal(hasAcquisitionRoute(row), true);
    assert.equal(classifyDiscoverResult(row).key, "external-acquirable");
  });

  it("does not treat capabilities:['panel'] as query-ready", () => {
    const lab = new Set(["panel_only"]);
    assert.equal(isQueryReady({ dataset_id: "panel_only", capabilities: ["panel"] }), false);
    const c = classifyDiscoverResult(
      { dataset_id: "panel_only", capabilities: ["panel"], local_root: "x" },
      lab,
    );
    assert.notEqual(c.key, "local-query-ready");
  });

  it("keeps licensed/manual out of immediate acquisition", () => {
    const c = classifyDiscoverResult({
      title: "Vendor feed",
      manual_access: true,
      access_mode: "licensed",
      collect_via: "should_not_override",
    });
    assert.equal(c.key, "licensed-manual");
  });

  it("orders groups while preserving API order within each group", () => {
    const lab = new Set(["local_a", "local_a2"]);
    const rows = [
      { title: "ext-b", url: "https://b.example", source: "B" },
      { dataset_id: "local_a", analysis_readiness: "instant", title: "local-first" },
      { title: "ext-a", url: "https://a.example", source: "A" },
      { title: "licensed", manual_access: true, access_mode: "licensed" },
      { dataset_id: "local_a2", title: "local-meta", in_lab: true },
    ];
    const ordered = orderDiscoverResults(rows, lab);
    assert.equal(ordered[0].title, "local-first");
    assert.equal(ordered[1].title, "local-meta");
    assert.equal(ordered[2].title, "ext-b");
    assert.equal(ordered[3].title, "ext-a");
    assert.equal(ordered[4].title, "licensed");
  });

  it("maps filters to taxonomy membership", () => {
    const qr = classifyDiscoverResult(
      { dataset_id: "x", analysis_readiness: "instant", materialization: { query_ready: true } },
      new Set(["x"]),
    );
    assert.equal(taxonomyMatchesFilter(qr, "query_ready"), true);
    assert.equal(taxonomyMatchesFilter(qr, "in_lab"), true);
    assert.equal(taxonomyMatchesFilter(qr, "external"), false);

    const ext = classifyDiscoverResult({ title: "e", url: "https://e.example" });
    assert.equal(taxonomyMatchesFilter(ext, "external"), true);
    assert.equal(taxonomyMatchesFilter(ext, "needs_access"), false);

    const lic = classifyDiscoverResult({ title: "l", manual_access: true });
    assert.equal(taxonomyMatchesFilter(lic, "needs_access"), true);
  });

  it("exceptional pills only for queued / manual / unavailable", () => {
    assert.equal(
      exceptionalRowPill({}, { key: "local-query-ready", readiness: "Query ready" }, { key: "in_lab" }),
      null,
    );
    assert.equal(
      exceptionalRowPill({}, { key: "external-probed", readiness: "Probed", className: "ext" }, {}),
      null,
    );
    assert.equal(
      exceptionalRowPill({}, { key: "external-acquirable", readiness: "Acquisition available" }, {}),
      null,
    );
    assert.deepEqual(
      exceptionalRowPill({ queued: true }, { key: "external-discoverable" }, { key: "queued" }),
      { label: "Queued", className: "queue" },
    );
    assert.deepEqual(
      exceptionalRowPill({}, { key: "licensed-manual", className: "warn" }, {}),
      { label: "Manual access", className: "warn" },
    );
    assert.deepEqual(
      exceptionalRowPill({}, { key: "external-unavailable", className: "warn" }, {}),
      { label: "Unavailable", className: "warn" },
    );
  });
});
