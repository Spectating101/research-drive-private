import assert from "node:assert/strict";
import test from "node:test";

import { buildProfessorVaultTree } from "./professorVaultTree.js";

/**
 * A shelf whose only partition is operator-hidden still holds datasets.
 * Crypto is the live case: markets.crypto-coingecko is an ops holding slot
 * flagged professor_visible=false while carrying 26 visible crypto datasets.
 * Before the fix the shelf rendered "no holdings in this branch" and every one
 * of those datasets was swept into Other holdings under Project downloads.
 */
const SHELVES = [
  { id: "crypto_onchain", label: "Crypto & on-chain", sort: 400, partition_ids: [] },
  { id: "project_downloads", label: "Project downloads", sort: 900, partition_ids: ["acquired.procured"] },
];

const PARTITIONS = [
  {
    partition_id: "acquired.procured",
    professor_label: "Procured one-offs",
    shelf_id: "project_downloads",
    shelf_label: "Project downloads",
    detail: { partition_id: "acquired.procured", registry_dataset_ids: [] },
  },
];

const DATASETS = [
  {
    dataset_id: "coingecko_btc_daily",
    display_name: "CoinGecko BTC Daily",
    partition_id: "markets.crypto-coingecko",
    shelf_hint: "crypto_onchain",
  },
  {
    dataset_id: "etherscan_stablecoin_catalog",
    display_name: "Etherscan Stablecoin Catalog",
    partition_id: "markets.crypto-coingecko",
    shelf_hint: "crypto_onchain",
  },
  {
    dataset_id: "zenodo_one_off",
    display_name: "Zenodo One-off",
    partition_id: "acquired.procured",
    shelf_hint: "project_downloads",
  },
];

function datasetIdsUnder(node) {
  const out = [];
  const walk = (n) => {
    for (const child of Object.values(n.children || {})) {
      if (child.kind === "dataset") out.push(child.id);
      else walk(child);
    }
  };
  walk(node);
  return out.sort();
}

test("datasets land on their own shelf when its partition is operator-hidden", () => {
  const { root: tree } = buildProfessorVaultTree(DATASETS, PARTITIONS, SHELVES);
  const crypto = tree.children.crypto_onchain;
  assert.ok(crypto, "crypto shelf should exist");
  assert.deepEqual(datasetIdsUnder(crypto), [
    "coingecko_btc_daily",
    "etherscan_stablecoin_catalog",
  ]);
});

test("hidden-partition datasets do not inflate project downloads", () => {
  const { root: tree } = buildProfessorVaultTree(DATASETS, PARTITIONS, SHELVES);
  // The regression this guards: crypto rows were swept here, so the shelf
  // reported far more holdings than it owned while crypto reported none.
  assert.deepEqual(datasetIdsUnder(tree.children.project_downloads), ["zenodo_one_off"]);
});

test("a dataset with no usable shelf hint still falls back to unfiled", () => {
  const orphan = [{ dataset_id: "mystery_row", display_name: "Mystery", shelf_hint: "" }];
  const { root: tree } = buildProfessorVaultTree(orphan, PARTITIONS, SHELVES);
  assert.deepEqual(datasetIdsUnder(tree.children.project_downloads), ["mystery_row"]);
});
