import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  groupDiscoverBrowseRows,
  interpretEvidenceNeed,
  splitBestFitAndOthers,
} from "./discoverComposition.js";

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
