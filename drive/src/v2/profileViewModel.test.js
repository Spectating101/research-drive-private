import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDeskRead,
  buildLab,
  buildMemoryBrief,
  buildMemoryCards,
  buildWorks,
  workTitleFromHighlight,
} from "./profileViewModel.js";

const SAMPLE = {
  name_en: "Kong, De-Rong",
  discipline: "Finance",
  title: "Assistant Professor",
  email: "drkong@saturn.yzu.edu.tw",
  paper_count_parsed: 18,
  specialties: ["Asset Pricing", "FinTech"],
  research_tracks: [
    { id: "t1", title: "Token taxonomy — on-chain and off-chain data", phase: "active_grant", weight: 3 },
    { id: "t2", title: "Taiwan equity misconduct", weight: 1 },
  ],
  method_tags: ["panel_data", "on_chain"],
  publication_highlights: [
    "Kong (2020). Alternative investments in the Fintech era. Journal of Foo.",
    "Kong (2021). NFT liquidity. SSRN 123.",
    "Kong (2022). Third paper. Journal of Bar.",
    "Kong (2023). Fourth paper. Journal of Baz.",
  ],
  lab_fintech_stack: [
    { id: "opensea", label: "OpenSea NFT metadata graph", route: "vault" },
    { id: "coingecko", label: "CoinGecko market panels", route: "bigquery" },
    { id: "skynet", label: "SkyNet token flows", route: "vault" },
    { id: "extra", label: "Fourth linked asset", route: "vault" },
  ],
  procurement_recommendations: [
    { dataset: "TWSE listed firm daily prices", search_query: "TWSE daily", source_route: "web" },
    { dataset: "MOPS financial statements", search_query: "MOPS financial", source_route: "mops" },
    { dataset: "Third gap dataset", search_query: "third gap", source_route: "web" },
    { dataset: "OpenSea NFT metadata graph", source_route: "vault" },
  ],
};

test("Memory brief is a statement plus at most three descriptors", () => {
  const brief = buildMemoryBrief(SAMPLE);
  assert.match(brief.statement, /Token taxonomy/i);
  assert.ok(brief.descriptors.length <= 3);
});

test("Works capped at three", () => {
  assert.equal(buildWorks(SAMPLE).items.length, 3);
});

test("Lab compresses to ≤3 linked and ≤2 gaps", () => {
  const lab = buildLab(SAMPLE);
  assert.ok(lab.linked.length <= 3);
  assert.ok(lab.suggested.length <= 2);
});

test("workTitleFromHighlight strips citation noise", () => {
  assert.match(
    workTitleFromHighlight("Kong (2020). Alternative investments in the Fintech era. Journal of Foo."),
    /Alternative investments/i,
  );
});

test("Memory cards compatibility", () => {
  assert.ok(buildMemoryCards(SAMPLE).length >= 1);
});

test("Desk read exists", () => {
  assert.match(buildDeskRead(SAMPLE).scholar, /Finance/i);
});
