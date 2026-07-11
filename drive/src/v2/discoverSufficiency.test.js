import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  SUFFICIENCY,
  assessLocalSufficiency,
  applySufficiencyToActions,
  buildSufficiencyAskContext,
  candidateComparableSignals,
} from "./discoverSufficiency.js";

const LAB_GDELT = {
  dataset_id: "gdelt_asia_daily_country_panel",
  name: "Asia daily news-risk panel",
  source_system: "GDELT news graph",
  grain: "country_day",
  join_keys: ["date", "country_iso3"],
  coverage: "2018–2024",
  analysis_readiness: "instant",
  local_ready: true,
};

const LAB_ISSUER = {
  dataset_id: "issuer_weekly_panel",
  name: "Issuer weekly fundamentals",
  source_system: "MOPS",
  grain: "issuer_week",
  join_keys: ["issuer_id", "week"],
  analysis_readiness: "instant",
};

describe("discoverSufficiency", () => {
  it("exact canonical identity → Exact local match", () => {
    const out = assessLocalSufficiency(
      { dataset_id: "gdelt_asia_daily_country_panel", title: "Anything", candidate_key: "dataset:gdelt_asia_daily_country_panel" },
      [LAB_GDELT],
    );
    assert.equal(out.state, SUFFICIENCY.EXACT_LOCAL);
    assert.match(out.browseLine, /Exact local match/);
    assert.equal(out.bestLocal.dataset_id, "gdelt_asia_daily_country_panel");
    assert.equal(out.primaryActionHint.id, "open_local");
  });

  it("same/similar title alone → not Exact", () => {
    const out = assessLocalSufficiency(
      {
        title: "Asia daily news-risk panel",
        url: "https://example.com/other",
        candidate_key: "url:https://example.com/other",
      },
      [LAB_GDELT],
    );
    assert.notEqual(out.state, SUFFICIENCY.EXACT_LOCAL);
  });

  it("lexical/search score alone → not Likely equivalent", () => {
    const out = assessLocalSufficiency(
      {
        title: "News risk Asia",
        score: 0.97,
        score_pct: 97,
        candidate_key: "url:https://example.com/news",
        url: "https://example.com/news",
      },
      [LAB_GDELT],
    );
    assert.notEqual(out.state, SUFFICIENCY.LIKELY_EQUIVALENT);
    assert.notEqual(out.state, SUFFICIENCY.EXACT_LOCAL);
  });

  it("does not invent Likely equivalent without explicit backend equivalence", () => {
    const out = assessLocalSufficiency(
      {
        title: "GDELT Asia panel mirror",
        source_system: "GDELT news graph",
        grain: "country_day",
        coverage: "2018–2024",
        join_keys: ["date", "country_iso3"],
        candidate_key: "url:https://example.com/gdelt-mirror",
        url: "https://example.com/gdelt-mirror",
      },
      [LAB_GDELT],
    );
    assert.notEqual(out.state, SUFFICIENCY.LIKELY_EQUIVALENT);
    // Same source + same grain/coverage with no named gap → related, not equivalent
    assert.equal(out.state, SUFFICIENCY.RELATED_LOCAL);
  });

  it("explicit equivalent relation from backend → Likely equivalent only with evidence", () => {
    const out = assessLocalSufficiency(
      {
        title: "External series",
        candidate_key: "url:https://example.com/series",
        local_comparison: {
          state: "likely_equivalent",
          local_dataset_ids: ["gdelt_asia_daily_country_panel"],
          basis: [{ dimension: "canonical_series", relation: "equivalent" }],
          differences: [],
          comparison_complete: true,
        },
      },
      [LAB_GDELT],
    );
    assert.equal(out.state, SUFFICIENCY.LIKELY_EQUIVALENT);
  });

  it("partial state requires a named comparison dimension", () => {
    const out = assessLocalSufficiency(
      {
        title: "GDELT Asia extended",
        source_system: "GDELT news graph",
        grain: "country_day",
        coverage: "2015–2026",
        join_keys: ["date", "country_iso3"],
        candidate_key: "url:https://example.com/gdelt-ext",
        url: "https://example.com/gdelt-ext",
      },
      [LAB_GDELT],
    );
    assert.equal(out.state, SUFFICIENCY.PARTIAL_LOCAL);
    assert.ok(out.differences.length >= 1);
    assert.equal(out.differences[0].dimension, "temporal_coverage");
    assert.match(out.browseLine, /2018|2024|Local/);
  });

  it("partial grain mismatch surfaces local vs candidate grain", () => {
    const out = assessLocalSufficiency(
      {
        title: "MOPS daily filings",
        source: "MOPS",
        grain: "issuer_day",
        join_keys: ["issuer_id", "week"],
        candidate_key: "url:https://mops.example/daily",
        url: "https://mops.example/daily",
      },
      [LAB_ISSUER],
    );
    assert.equal(out.state, SUFFICIENCY.PARTIAL_LOCAL);
    assert.ok(out.differences.some((d) => d.dimension === "grain"));
    assert.match(out.browseLine, /week|day|grain|issuer/i);
  });

  it("related family does not become Equivalent", () => {
    const out = assessLocalSufficiency(
      {
        title: "Other MOPS table",
        source: "MOPS",
        grain: "issuer_week",
        join_keys: ["issuer_id", "week"],
        candidate_key: "url:https://mops.example/other",
        url: "https://mops.example/other",
      },
      [LAB_ISSUER],
    );
    assert.equal(out.state, SUFFICIENCY.RELATED_LOCAL);
    assert.notEqual(out.state, SUFFICIENCY.LIKELY_EQUIVALENT);
    assert.notEqual(out.state, SUFFICIENCY.EXACT_LOCAL);
  });

  it("completed comparison with zero qualifying local assets → No local alternative found", () => {
    const out = assessLocalSufficiency(
      {
        title: "MOPS financial statements",
        source: "MOPS",
        grain: "issuer_quarter",
        candidate_key: "dataset:mops_financial_statements_ext",
        url: "https://mops.twse.com.tw/example",
      },
      [LAB_GDELT],
    );
    assert.equal(out.state, SUFFICIENCY.NO_LOCAL_ALTERNATIVE);
    assert.equal(out.comparisonComplete, true);
  });

  it("failed/incomplete comparison → Comparison unknown", () => {
    const failed = assessLocalSufficiency({ title: "X", source: "MOPS" }, [LAB_GDELT], {
      comparisonFailed: true,
    });
    assert.equal(failed.state, SUFFICIENCY.COMPARISON_UNKNOWN);

    const thin = assessLocalSufficiency(
      {
        title: "Random web page",
        url: "https://example.com/page",
        candidate_key: "url:https://example.com/page",
      },
      [LAB_GDELT],
    );
    assert.equal(thin.state, SUFFICIENCY.COMPARISON_UNKNOWN);
    assert.equal(
      candidateComparableSignals({
        title: "Random web page",
        url: "https://example.com/page",
      }).includes("source_identity"),
      false,
    );
  });

  it("exact local match changes primary action to Open local dataset", () => {
    const suf = assessLocalSufficiency(
      { dataset_id: "gdelt_asia_daily_country_panel" },
      [LAB_GDELT],
    );
    const actions = applySufficiencyToActions(
      { primary: { id: "add_lab", label: "Add to lab" }, secondary: [{ id: "ask", label: "Ask" }] },
      suf,
    );
    assert.equal(actions.primary.id, "open_local");
  });

  it("partial does not automatically submit acquisition / change primary to add_lab", () => {
    const suf = assessLocalSufficiency(
      {
        title: "GDELT Asia extended",
        source_system: "GDELT news graph",
        coverage: "2015–2026",
        grain: "country_day",
        join_keys: ["date", "country_iso3"],
        url: "https://example.com/g",
      },
      [LAB_GDELT],
    );
    const actions = applySufficiencyToActions(
      { primary: { id: "probe", label: "Probe source" }, secondary: [{ id: "add_lab", label: "Add to lab" }] },
      suf,
    );
    assert.equal(actions.primary.id, "probe");
    assert.ok(actions.secondary.some((a) => a.id === "open_local"));
  });

  it("lifecycle state overrides sufficiency action", () => {
    const suf = assessLocalSufficiency(
      { dataset_id: "gdelt_asia_daily_country_panel" },
      [LAB_GDELT],
    );
    const actions = applySufficiencyToActions(
      { primary: { id: "track_resources", label: "Track in Resources" }, secondary: [] },
      suf,
      { lifecycleOverrides: true },
    );
    assert.equal(actions.primary.id, "track_resources");
  });

  it("Ask receives structured comparison context", () => {
    const candidate = {
      title: "GDELT Asia extended",
      source_system: "GDELT news graph",
      coverage: "2015–2026",
      grain: "country_day",
      join_keys: ["date", "country_iso3"],
      candidate_key: "url:https://example.com/g",
    };
    const suf = assessLocalSufficiency(candidate, [LAB_GDELT]);
    const ctx = buildSufficiencyAskContext(suf, candidate);
    assert.equal(ctx.sufficiency_state, SUFFICIENCY.PARTIAL_LOCAL);
    assert.equal(ctx.local_dataset_id, "gdelt_asia_daily_country_panel");
    assert.ok(Array.isArray(ctx.basis));
    assert.ok(Array.isArray(ctx.differences));
    assert.equal(ctx.candidate_key, candidate.candidate_key);
  });

  it("does not treat empty catalog as no-local-alternative", () => {
    const out = assessLocalSufficiency({ source: "MOPS", title: "X" }, []);
    assert.equal(out.state, SUFFICIENCY.COMPARISON_UNKNOWN);
  });
});
