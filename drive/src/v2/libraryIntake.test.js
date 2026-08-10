import assert from "node:assert/strict";
import test from "node:test";

import { classifyLibraryIntakeTarget } from "./libraryIntake.js";

test("recognizes a DOI in canonical DOI URL form", () => {
  assert.deepEqual(classifyLibraryIntakeTarget("https://doi.org/10.5281/zenodo.58938"), {
    doi: "10.5281/zenodo.58938",
    url: "",
  });
});

test("recognizes a bare DOI", () => {
  assert.deepEqual(classifyLibraryIntakeTarget("10.1000/example.dataset"), {
    doi: "10.1000/example.dataset",
    url: "",
  });
});

test("keeps a non-DOI URL on the governed URL intake route", () => {
  assert.deepEqual(classifyLibraryIntakeTarget("https://data.example.org/observations.csv"), {
    doi: "",
    url: "https://data.example.org/observations.csv",
  });
});

test("rejects an empty or unsupported intake target", () => {
  assert.equal(classifyLibraryIntakeTarget("not a URL"), null);
});
