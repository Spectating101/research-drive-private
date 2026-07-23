import test from "node:test";
import assert from "node:assert/strict";
import { countDatasetDescendants, folderBrowseSummary } from "./folderBrowseSummary.js";

test("shelf summary lists folders inside and total datasets", () => {
  const shelf = {
    kind: "folder",
    name: "US markets & fundamentals",
    blurb: "CRSP, Compustat, Refinitiv spine",
    children: {
      a: {
        kind: "folder",
        name: "US equity history (CRSP)",
        children: {
          d1: { kind: "dataset", id: "d1" },
          d2: { kind: "dataset", id: "d2" },
        },
      },
      b: {
        kind: "folder",
        name: "US fundamentals (Compustat)",
        children: { d3: { kind: "dataset", id: "d3" } },
      },
      c: {
        kind: "folder",
        name: "Refinitiv institutional spine",
        children: {},
      },
    },
  };
  const summary = folderBrowseSummary(shelf);
  assert.equal(countDatasetDescendants(shelf), 3);
  assert.match(summary.sub, /US equity history \(CRSP\)/);
  assert.match(summary.sub, /Compustat/);
  assert.match(summary.sub, /3 datasets/);
  assert.doesNotMatch(summary.sub, /items/i);
  assert.equal(summary.pill, "3");
  assert.equal(summary.desc, "CRSP, Compustat, Refinitiv spine");
});

test("empty partition folder is explicit", () => {
  const part = {
    kind: "folder",
    name: "Crowd signals",
    blurb: "Retail / social overlays",
    children: {},
  };
  const summary = folderBrowseSummary(part);
  assert.equal(summary.sub, "No datasets on this desk yet");
  assert.equal(summary.pill, "0");
  assert.equal(summary.desc, "Retail / social overlays");
});
