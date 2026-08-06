import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  cleanWhy,
  evidencePlacement,
  evidenceWhy,
  isMaterialLibraryRelation,
  PLACEMENT,
} from "./evidencePlacement.js";

describe("evidencePlacement", () => {
  it("strips canned semantic wallpaper", () => {
    assert.equal(cleanWhy("matched on meaning, not wording"), "");
    assert.equal(evidenceWhy({ selection_reason: "matched on meaning, not wording" }), "");
    assert.equal(evidenceWhy({ why: "USDT peg stress flows" }), "USDT peg stress flows");
  });

  it("prefers backend placement", () => {
    assert.equal(evidencePlacement({ placement: "route", local_ready: true }), PLACEMENT.ROUTE);
  });

  it("derives held from registry possession only", () => {
    assert.equal(
      evidencePlacement({ kind: "registry_dataset", dataset_id: "a", local_ready: true }),
      PLACEMENT.HELD,
    );
  });

  it("does not treat no-alternative as material", () => {
    assert.equal(isMaterialLibraryRelation("no-local-alternative"), false);
    assert.equal(isMaterialLibraryRelation("exact-local"), true);
  });
});
