import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildProfessorVaultTree } from "./professorVaultTree.js";
import { reconcileLibraryDeepLink } from "./libraryDeepLink.js";

const DATASETS = [
  {
    dataset_id: "gdelt_asia_daily_country_panel",
    name: "GDELT Asia panel",
    analysis_readiness: "instant",
    partition_id: "gdelt",
  },
  {
    dataset_id: "other_holding",
    name: "Other holding",
    analysis_readiness: "registered",
    partition_id: "unfiled",
  },
];

const PARTITIONS = [
  {
    partition_id: "gdelt",
    shelf_id: "research_panels",
    shelf_label: "Research panels",
    professor_label: "gdelt",
    registry_dataset_ids: ["gdelt_asia_daily_country_panel"],
  },
];

const SHELVES = [
  {
    id: "research_panels",
    label: "Research panels",
    partition_ids: ["gdelt"],
  },
];

describe("reconcileLibraryDeepLink", () => {
  it("keeps a query-ready selection that belongs to the displayed folder", () => {
    const tree = buildProfessorVaultTree(DATASETS, PARTITIONS, SHELVES);
    const next = reconcileLibraryDeepLink({
      folderId: "research_panels/gdelt",
      selectedId: "gdelt_asia_daily_country_panel",
      tree,
    });
    assert.deepEqual(next, {
      folderId: "research_panels/gdelt",
      selectedId: "gdelt_asia_daily_country_panel",
    });
  });

  it("corrects an empty folder when a selected query-ready asset lives elsewhere", () => {
    const tree = buildProfessorVaultTree(DATASETS, PARTITIONS, SHELVES);
    const next = reconcileLibraryDeepLink({
      folderId: "research_panels/empty_branch",
      selectedId: "gdelt_asia_daily_country_panel",
      tree,
    });
    assert.equal(next.selectedId, "gdelt_asia_daily_country_panel");
    assert.equal(next.folderId, "research_panels/gdelt");
  });

  it("clears an orphan selection that is not in the vault tree", () => {
    const tree = buildProfessorVaultTree(DATASETS, PARTITIONS, SHELVES);
    const next = reconcileLibraryDeepLink({
      folderId: "research_panels/gdelt",
      selectedId: "missing_asset",
      tree,
    });
    assert.deepEqual(next, {
      folderId: "research_panels/gdelt",
      selectedId: "",
    });
  });
});
