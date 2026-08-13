import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildDeskIntegrationChips,
  buildObjectEstateCrumb,
  normalizeActivityStep,
} from "./deskIntegration.js";

describe("deskIntegration", () => {
  it("builds degraded desk chips from live health", () => {
    const chips = buildDeskIntegrationChips({
      status: "degraded",
      desk: {
        brain: "cursor_composer",
        mcp_tools: { total: 71 },
        gdrive: { ok: true },
        storage_tiers: {
          canonical: { label: "Google Drive vault" },
          hot: { headroom_ok: false, used_pct: 89 },
          cache: { mounted: true, label: "Transcend bulk cache" },
        },
        jobs: {
          pending_approval: 20,
          actionable: { pending_oldest_age_days: 22 },
        },
      },
    });
    const labels = chips.map((c) => c.label).join(" | ");
    assert.match(labels, /Desk degraded|Google Drive|NVMe|agent tools|pending/i);
    assert.ok(chips.length <= 5);
  });

  it("explains a composer-runtime-unverified cause of degraded status", () => {
    // Regression: /health can flip to "degraded" purely because
    // composer_runtime is configured-but-unverified (checked_at: null), with
    // no NVMe/cache/vault issue at all. Before this chip existed, "Desk
    // degraded" showed with no visible reason for that specific cause.
    const chips = buildDeskIntegrationChips({
      status: "degraded",
      desk: {
        composer_configured: true,
        composer_model: "composer-2.5",
        composer_runtime: {
          status: "unverified",
          configured: true,
          verified: false,
          checked_at: null,
        },
        gdrive: { ok: true },
        storage_tiers: { hot: { headroom_ok: true }, cache: { mounted: true } },
        jobs: { pending_approval: 0 },
      },
    });
    const labels = chips.map((c) => c.label);
    assert.ok(labels.includes("Assistant unverified"), labels.join(" | "));
  });

  it("does not explain a composer cause once the runtime is actually ready", () => {
    const chips = buildDeskIntegrationChips({
      status: "ok",
      desk: {
        composer_configured: true,
        composer_runtime: { status: "ready", configured: true, verified: true },
        gdrive: { ok: true },
        storage_tiers: { hot: { headroom_ok: true }, cache: { mounted: true } },
        jobs: { pending_approval: 0 },
      },
    });
    assert.ok(!chips.some((c) => c.id === "composer"));
  });

  it("explains a degraded (failed-probe) composer cause, not a false Ready", () => {
    // Regression (caught in review): verified: true is also set on a failed
    // probe (record_composer_failure) — it must not be read as healthy, and
    // it must not be silently absorbed into the generic "unverified" label.
    const chips = buildDeskIntegrationChips({
      status: "degraded",
      desk: {
        composer_configured: true,
        composer_runtime: { status: "degraded", configured: true, verified: true, error_category: "timeout" },
        gdrive: { ok: true },
        storage_tiers: { hot: { headroom_ok: true }, cache: { mounted: true } },
        jobs: { pending_approval: 0 },
      },
    });
    const labels = chips.map((c) => c.label);
    assert.ok(labels.includes("Assistant degraded"), labels.join(" | "));
  });

  it("explains a stale composer observation distinctly from never-probed", () => {
    const chips = buildDeskIntegrationChips({
      status: "degraded",
      desk: {
        composer_configured: true,
        composer_runtime: { status: "stale", configured: true, verified: false, age_seconds: 999 },
        gdrive: { ok: true },
        storage_tiers: { hot: { headroom_ok: true }, cache: { mounted: true } },
        jobs: { pending_approval: 0 },
      },
    });
    const labels = chips.map((c) => c.label);
    assert.ok(labels.includes("Assistant needs recheck"), labels.join(" | "));
  });

  it("does not chip an unconfigured (unavailable) composer — that's a normal, expected state", () => {
    const chips = buildDeskIntegrationChips({
      status: "ok",
      desk: {
        composer_configured: false,
        composer_runtime: { status: "unavailable", configured: false, verified: false },
        gdrive: { ok: true },
        storage_tiers: { hot: { headroom_ok: true }, cache: { mounted: true } },
        jobs: { pending_approval: 0 },
      },
    });
    assert.ok(!chips.some((c) => c.id === "composer"));
  });

  it("builds object estate crumb for discover source", () => {
    const crumb = buildObjectEstateCrumb(
      {
        title: "TWSE Open API",
        source_id: "twse_official",
        provider: "Taiwan Stock Exchange",
        endpoint: "openapi.twse.com.tw",
        external: true,
        search_meta: { search_mode: "catalog" },
      },
      { searchMeta: { search_mode: "catalog" } },
    );
    assert.match(String(crumb.location), /Remote|Provider/);
    assert.match(String(crumb.freshness), /Catalog/);
    assert.match(String(crumb.authority), /Source registry/);
  });

  it("accumulates distinct activity phases", () => {
    let log = [];
    log = normalizeActivityStep({ phase: "planning", text: "Understanding…" }, log);
    log = normalizeActivityStep({ phase: "composing", text: "Composer…" }, log);
    log = normalizeActivityStep({ phase: "composing", text: "Composer…" }, log);
    log = normalizeActivityStep("Searching the vault…", log);
    assert.equal(log.length, 3);
    assert.equal(log[0].phase, "planning");
    assert.equal(log[2].text, "Searching the vault…");
  });
});
