import test from "node:test";
import assert from "node:assert/strict";
import {
  PROFILE_SECTION_ORDER,
  assertNoExamplePrimary,
  buildProfileContextAskPrompt,
  buildProfileRailState,
  profileCentreMode,
  profilePrimaryCommand,
} from "./profilePresentation.js";
import { buildResearchUnderstanding, buildWorks } from "./profileViewModel.js";

test("Profile centre model is exactly Memory → Works → Lab", () => {
  assert.deepEqual(PROFILE_SECTION_ORDER, ["memory", "works", "lab"]);
});

test("unbound profile is not shown as primary EXAMPLE bind", () => {
  assert.equal(profileCentreMode(null), "unbound");
  assert.equal(profileCentreMode({ unknown: true, email: "" }), "unbound");
  const cmd = profilePrimaryCommand("unbound");
  assert.equal(cmd?.id, "connect-email");
  assert.equal(cmd?.inline, true);
  assert.equal(cmd?.tab, undefined);
  assert.equal(assertNoExamplePrimary("unbound", cmd), true);
  assert.equal(
    assertNoExamplePrimary("unbound", { label: "Bind example identity" }),
    false,
  );
});

test("Profile Detail rail never says Loading when profile data exists", () => {
  const unbound = buildProfileRailState({ profile: { unknown: true }, profileResolved: true });
  assert.notEqual(unbound.status, "pending");
  assert.equal(unbound.loadingLabel, null);
  assert.match(unbound.judgement, /Connect a faculty email/i);
  assert.doesNotMatch(unbound.judgement, /^Loading/i);
  assert.equal(unbound.primaryAction?.id, "connect-email");

  const profile = {
    name_en: "Kong, De-Rong",
    email: "drkong@saturn.yzu.edu.tw",
    discipline: "Finance",
    specialties: ["Asset Pricing", "FinTech"],
    research_tracks: [
      { id: "token", title: "Token taxonomy — on-chain data", phase: "active_grant", weight: 10 },
    ],
    lab_fintech_stack: [{ id: "coingecko", label: "CoinGecko prices", route: "vault" }],
  };
  const understanding = buildResearchUnderstanding(profile);
  const bound = buildProfileRailState({
    profile,
    profileResolved: true,
    understanding,
  });
  assert.equal(bound.status, "context");
  assert.equal(bound.primaryAction?.id, "ask-context");
  assert.ok(bound.provenance?.length >= 1);
  assert.match(bound.judgement, /Derivation/i);
  assert.ok(!bound.judgement.includes(understanding.synthesis.slice(0, 40)));

  const work = buildProfileRailState({
    profile: { name_en: "Kong, De-Rong" },
    profileResolved: true,
    selectedWork: {
      title: "NFT risk and return",
      type: "Publication",
      relationship: "FinTech output",
      raw: "Kong (2023). NFT…",
    },
  });
  assert.equal(work.status, "work");
  assert.equal(work.primaryAction?.id, "ask-work");
});

test("bound Profile Detail without understanding has no sticky CTA", () => {
  const bound = buildProfileRailState({
    profile: {
      name_en: "Kong, De-Rong",
      email: "drkong@saturn.yzu.edu.tw",
      discipline: "Finance",
    },
    profileResolved: true,
  });
  assert.equal(bound.primaryAction, null);
});

test("Ask about this context prompt carries structured inputs only", () => {
  const understanding = buildResearchUnderstanding({
    name_en: "Kong, De-Rong",
    email: "drkong@saturn.yzu.edu.tw",
    discipline: "Finance",
    specialties: ["Asset Pricing", "FinTech"],
    research_tracks: [
      { id: "token", title: "Token taxonomy — on-chain data", phase: "active_grant", weight: 10 },
      { id: "tw", title: "Taiwan equity misconduct", weight: 4 },
    ],
    lab_fintech_stack: [{ id: "coingecko", label: "CoinGecko prices", route: "vault" }],
    procurement_recommendations: [
      { dataset: "TWSE daily prices", search_query: "TWSE daily prices" },
    ],
  });
  const prompt = buildProfileContextAskPrompt(understanding.askContext);
  assert.match(prompt, /Kong, De-Rong/);
  assert.match(prompt, /Threads seen/i);
  assert.match(prompt, /Do not invent facts/i);
});

test("Works presentation exposes real titles without fabricating success", () => {
  const works = buildWorks({
    paper_count: 18,
    publication_highlights: [
      "Kong (2023). Alternative investments in the Fintech era: The risk and return of Non-Fungible Token (NFT).",
      "Kong (2022). Something else about markets.",
      "Kong (2021). Third.",
      "Kong (2020). Fourth.",
    ],
  });
  assert.ok(works.items.length >= 2);
  assert.ok(works.items.length <= 3);
  for (const item of works.items) {
    assert.ok(item.title);
    assert.doesNotMatch(item.title, /success|ready|complete/i);
  }
});
