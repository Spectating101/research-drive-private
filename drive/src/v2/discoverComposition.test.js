import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  groupDiscoverBrowseRows,
  interpretEvidenceNeed,
  splitBestFitAndOthers,
} from "./discoverComposition.js";
import {
  hasSpecificDiscoverRoute,
  meaningfulDiscoverTerms,
  normalizeDiscoverText,
} from "./discoverQuerySpecificity.js";

describe("groupDiscoverBrowseRows", () => {
  it("buckets by taxonomy group into lab / external / needs access", () => {
    const groups = groupDiscoverBrowseRows([
      { title: "Lab A", discover_taxonomy: { key: "local-query-ready", group: 1, label: "In Library · Query ready" } },
      { title: "Ext B", discover_taxonomy: { key: "external-acquirable", group: 3, label: "External · Acquisition available" } },
      { title: "Lic C", discover_taxonomy: { key: "licensed-manual", group: 4, label: "Licensed / manual access" } },
    ]);
    assert.deepEqual(
      groups.map((g) => [g.id, g.rows.map((r) => r.title)]),
      [
        ["lab", ["Lab A"]],
        ["external", ["Ext B"]],
        ["access", ["Lic C"]],
      ],
    );
  });
});

describe("interpretEvidenceNeed", () => {
  it("emits named chips with overflow budget", () => {
    const { chips, overflow } = interpretEvidenceNeed(
      "transaction-level stablecoin evidence around market stress events before 2020 entity identifiers",
    );
    assert.ok(chips.length <= 4);
    assert.ok(chips.some((c) => /stablecoin/i.test(c)));
    assert.ok(overflow >= 0);
  });
});

describe("Discover query specificity", () => {
  it("normalizes CO₂ and drops question filler from route evidence", () => {
    assert.equal(normalizeDiscoverText("CO₂"), "co2");
    assert.deepEqual(
      meaningfulDiscoverTerms([
        "What", "Public", "Monthly", "Atmospheric", "CO₂", "Measurements",
        "Can", "I", "Use", "Illustrate", "Keeling", "Curve",
      ]),
      ["atmospheric", "co2", "keeling", "curve"],
    );
  });

  it("does not treat generic crypto offerings as a Keeling Curve route", () => {
    const tokens = ["What", "Public", "Monthly", "Atmospheric", "CO₂", "Measurements", "Keeling", "Curve"];
    assert.equal(hasSpecificDiscoverRoute([
      { title: "Google BigQuery on-chain transfers", description: "Public cryptocurrency transaction data" },
      { title: "CoinGecko market archive", description: "Daily crypto asset prices" },
      { title: "OpenAlex", description: "Open research graph" },
    ], tokens), false);
    assert.equal(hasSpecificDiscoverRoute([
      { title: "NOAA Mauna Loa atmospheric CO2", description: "Monthly Keeling Curve measurements" },
    ], tokens), true);
  });
});

describe("splitBestFitAndOthers", () => {
  it("promotes first ranked row as Best fit", () => {
    const { bestFit, others, total } = splitBestFitAndOthers([{ title: "A" }, { title: "B" }, { title: "C" }]);
    assert.equal(bestFit.title, "A");
    assert.deepEqual(
      others.map((r) => r.title),
      ["B", "C"],
    );
    assert.equal(total, 3);
  });
});
