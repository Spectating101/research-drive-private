import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  identifyProviderMarkId,
  NAMED_PROVIDER_MARK_IDS,
  PROVIDER_MARK_FILES,
} from "./providerMarkIds.js";
import { groupSourceCapabilities } from "./resourcesCapacity.js";

const providersDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "assets/providers");

describe("provider mark mapping", () => {
  it("maps named providers to real mark ids (not generic initials)", () => {
    const cases = [
      [{ key: "source-lseg_edp", label: "LSEG Workspace / EDP (YZU seat)" }, "lseg"],
      [{ key: "source-wrds", label: "WRDS (CRSP · Compustat · CCM)" }, "wrds"],
      [{ key: "source-crsp_moveit", label: "CRSP MOVEit Cloud" }, "moveit"],
      [{ key: "source-capital_iq", label: "S&P Capital IQ / Compustat" }, "capital_iq"],
      [{ key: "source-sec_edgar", label: "SEC EDGAR" }, "sec_edgar"],
      [{ key: "source-twse", label: "TWSE Open API" }, "twse"],
      [{ key: "source-mops", label: "MOPS Taiwan" }, "mops"],
      [{ key: "source-yfinance", label: "Yahoo Finance" }, "yahoo"],
      [{ key: "source-bigquery", label: "Google BigQuery" }, "bigquery"],
      [{ key: "source-datacite", label: "DataCite" }, "datacite"],
      [{ key: "source-huggingface", label: "HuggingFace" }, "huggingface"],
      [{ key: "source-coingecko", label: "CoinGecko" }, "coingecko"],
      [{ key: "source-open_research", label: "Zenodo · OpenAlex" }, "zenodo"],
      [{ key: "source-web_generic", label: "Web (arbitrary)" }, "web"],
      [{ key: "layer-playwright", label: "Playwright scrape" }, "playwright"],
      [{ key: "layer-probe_url", label: "Source probe" }, "probe"],
      [{ label: "Refinitiv EDP" }, "lseg"],
    ];
    for (const [row, expected] of cases) {
      assert.equal(identifyProviderMarkId(row), expected, JSON.stringify(row));
      assert.notEqual(expected, "generic");
    }
  });

  it("keeps bundled asset files on disk for every mark id", () => {
    for (const [id, file] of Object.entries(PROVIDER_MARK_FILES)) {
      const abs = path.join(providersDir, file);
      assert.ok(existsSync(abs), `missing ${id} → ${file}`);
    }
    for (const id of NAMED_PROVIDER_MARK_IDS) {
      assert.ok(PROVIDER_MARK_FILES[id], `named mark ${id} has no file mapping`);
      assert.notEqual(id, "generic");
    }
  });

  it("attaches markId on Source capabilities ledger rows", () => {
    const families = groupSourceCapabilities([
      {
        rows: [
          { key: "source-lseg_edp", label: "LSEG Workspace / EDP", status: "pending" },
          { key: "source-wrds", label: "WRDS", status: "unavailable" },
          { key: "source-sec_edgar", label: "SEC EDGAR", status: "pending" },
          { key: "source-bigquery", label: "Google BigQuery", status: "observed" },
          { key: "source-datacite", label: "DataCite", status: "observed" },
          { key: "source-web_generic", label: "Web (arbitrary)", status: "conditional" },
        ],
      },
    ]);
    const rows = families.flatMap((f) => f.rows);
    const byKey = Object.fromEntries(rows.map((r) => [r.id, r]));
    assert.equal(byKey["source-lseg_edp"].markId, "lseg");
    assert.equal(byKey["source-wrds"].markId, "wrds");
    assert.equal(byKey["source-sec_edgar"].markId, "sec_edgar");
    assert.equal(byKey["source-bigquery"].markId, "bigquery");
    assert.equal(byKey["source-datacite"].markId, "datacite");
    assert.equal(byKey["source-web_generic"].markId, "web");
  });
});
