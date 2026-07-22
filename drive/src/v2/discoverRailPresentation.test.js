import test from "node:test";
import assert from "node:assert/strict";
import { PAGE_DETAIL_EMPTY } from "./railEmptyCopy.js";

test("Intelligence Rail empty Detail copy is page-specific and one line", () => {
  assert.equal(PAGE_DETAIL_EMPTY.browse, "Select a source to inspect.");
  assert.equal(PAGE_DETAIL_EMPTY.library, "Select an asset or folder.");
  assert.equal(PAGE_DETAIL_EMPTY.synthesis, "Select a construction node.");
  assert.equal(PAGE_DETAIL_EMPTY.resources, "Select an activity to inspect.");
});
