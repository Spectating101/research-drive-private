import test from "node:test";
import assert from "node:assert/strict";
import { collectDatasetDescendants, listFolderChildren } from "./driveTree.js";

const tree = {
  root: {
    id: "",
    kind: "folder",
    name: "Lab",
    children: {
      news: {
        id: "news",
        kind: "folder",
        name: "News",
        children: {
          "news/gdelt": {
            id: "news/gdelt",
            kind: "folder",
            name: "GDELT",
            children: {
              "ds-asia": {
                kind: "dataset",
                id: "ds-asia",
                name: "Asia Daily News Shock Panel",
                row: { dataset_id: "ds-asia", name: "Asia Daily News Shock Panel" },
              },
              "ds-other": {
                kind: "dataset",
                id: "ds-other",
                name: "Other panel",
                row: { dataset_id: "ds-other", name: "Other panel" },
              },
            },
          },
        },
      },
    },
  },
};

test("listFolderChildren at root only returns shelves (folders)", () => {
  const kids = listFolderChildren(tree, "");
  assert.deepEqual(
    kids.map((k) => k.kind),
    ["folder"],
  );
  assert.equal(kids[0].name, "News");
});

test("collectDatasetDescendants flattens matching files under Lab", () => {
  const hits = collectDatasetDescendants(tree, "");
  assert.equal(hits.length, 2);
  assert.deepEqual(
    hits.map((h) => h.id).sort(),
    ["ds-asia", "ds-other"],
  );
  assert.ok(hits.every((h) => h.kind === "dataset"));
});

test("collectDatasetDescendants scopes to open branch", () => {
  const hits = collectDatasetDescendants(tree, "news/gdelt");
  assert.equal(hits.length, 2);
  const none = collectDatasetDescendants(tree, "missing");
  assert.equal(none.length, 0);
});
