import assert from "node:assert/strict";
import test from "node:test";

import { sortRows } from "./sortRows.js";

const ROWS = [
  { dataset_id: "b", title: "Beta panel", size_bytes: 100, query_verified_at: "2026-08-01" },
  { dataset_id: "a", title: "Alpha panel", size_bytes: 900, query_verified_at: "2026-08-04" },
  { dataset_id: "c", title: "Gamma panel", size_bytes: 500 },
];

test("relevance keeps backend order untouched", () => {
  const out = sortRows(ROWS, "relevance");
  assert.deepEqual(out.map((r) => r.dataset_id), ["b", "a", "c"]);
  assert.equal(out, ROWS);
});

test("size sorts largest first", () => {
  assert.deepEqual(
    sortRows(ROWS, "size").map((r) => r.dataset_id),
    ["a", "c", "b"],
  );
});

test("recently verified sorts newest first and sinks unverified rows", () => {
  assert.deepEqual(
    sortRows(ROWS, "verified").map((r) => r.dataset_id),
    ["a", "b", "c"],
  );
});

test("name sorts alphabetically by displayed title", () => {
  assert.deepEqual(
    sortRows(ROWS, "name").map((r) => r.dataset_id),
    ["a", "b", "c"],
  );
});

test("sorting never mutates the input", () => {
  const before = ROWS.map((r) => r.dataset_id);
  sortRows(ROWS, "size");
  sortRows(ROWS, "name");
  assert.deepEqual(ROWS.map((r) => r.dataset_id), before);
});

test("an unknown sort falls through unchanged", () => {
  assert.deepEqual(
    sortRows(ROWS, "nonsense").map((r) => r.dataset_id),
    ["b", "a", "c"],
  );
});
