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
