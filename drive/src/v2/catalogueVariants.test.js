import assert from "node:assert/strict";
import test from "node:test";

import { groupCatalogueVariants } from "./catalogueVariants.js";

/** One stablecoin query returned the same catalogue at four crawl scales. */
const ROWS = [
  { dataset_id: "a", display_name: "Etherscan Stablecoin Catalog (Full Sweep)" },
  { dataset_id: "b", display_name: "Etherscan Stablecoin Catalog (Medium Crawl A)" },
  { dataset_id: "c", display_name: "Etherscan Stablecoin Catalog (Small Crawl A)" },
  { dataset_id: "d", display_name: "Etherscan Stablecoin Catalog (Medium Crawl C)" },
  { dataset_id: "e", display_name: "CoinGecko Simple Price API" },
];

test("scale variants collapse to one row carrying its variants", () => {
  const out = groupCatalogueVariants(ROWS);
  assert.equal(out.length, 2);
  assert.equal(out[0]._base, "Etherscan Stablecoin Catalog");
  assert.equal(out[0]._variants.length, 4);
});

test("a title without a parenthetical is never grouped away", () => {
  const out = groupCatalogueVariants(ROWS);
  assert.equal(out[1]._base, "CoinGecko Simple Price API");
  assert.equal(out[1]._variants.length, 0);
});

test("distinct datasets are not merged by a shared word", () => {
  const out = groupCatalogueVariants([
    { dataset_id: "x", display_name: "Ethereum USDT Transfer Pilot" },
    { dataset_id: "y", display_name: "Ethereum USDT Transfer Catalogue" },
  ]);
  assert.equal(out.length, 2);
});
