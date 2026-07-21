import test from "node:test";
import assert from "node:assert/strict";
import {
  PROFILE_SECTION_ORDER,
  PROFILE_TEST_EMAIL,
  assertNoAutomaticPilotIdentity,
  assertNoExamplePrimary,
  buildProfileRailState,
  buildUnboundProfileCentre,
  isProfileBound,
  profileCentreMode,
  profilePrimaryCommand,
  profileSectionsVisible,
} from "./profilePresentation.js";
import { buildWorks, PILOT_PREVIEW_EMAIL } from "./profileViewModel.js";

test("Profile centre model is exactly Memory → Works → Lab", () => {
  assert.deepEqual(PROFILE_SECTION_ORDER, ["memory", "works", "lab"]);
});

test("no automatic pilot identity — test email is explicit only", () => {
  assert.equal(PROFILE_TEST_EMAIL, "drkong@saturn.yzu.edu.tw");
  assert.equal(PILOT_PREVIEW_EMAIL, PROFILE_TEST_EMAIL);
  assert.equal(assertNoAutomaticPilotIdentity(""), true);
  assert.equal(assertNoAutomaticPilotIdentity(PROFILE_TEST_EMAIL), true);
  // Empty storage must not invent the pilot address
  assert.notEqual("", PROFILE_TEST_EMAIL);
});

test("unbound profile is not shown as primary EXAMPLE bind", () => {
  assert.equal(profileCentreMode(null), "unbound");
  assert.equal(profileCentreMode({ unknown: true, email: "" }), "unbound");
  assert.equal(profileCentreMode({ unknown: true, name_en: "Nobody", email: "nobody@yzu.edu.tw" }), "unbound");
  assert.equal(isProfileBound({ unknown: true, name_en: "Nobody" }), false);
  const cmd = profilePrimaryCommand("unbound");
  assert.equal(cmd?.tab, "settings");
  assert.match(cmd?.label || "", /Settings/i);
  assert.equal(assertNoExamplePrimary("unbound", cmd), true);
  assert.equal(
    assertNoExamplePrimary("unbound", { label: "Bind example identity" }),
    false,
  );
  assert.equal(assertNoExamplePrimary("unbound", { label: "Use drkong" }), false);
});

test("unbound centre hides Memory/Works/Lab section shells", () => {
  assert.equal(profileSectionsVisible(null), false);
  assert.equal(profileSectionsVisible({ unknown: true }), false);
  assert.equal(profileSectionsVisible({ name_en: "Kong, De-Rong", email: PROFILE_TEST_EMAIL }), true);
  const zero = buildUnboundProfileCentre();
  assert.match(zero.title, /No researcher context/i);
  assert.match(zero.hint, /not a sign-in/i);
  assert.doesNotMatch(zero.title, /Kong|EXAMPLE|drkong/i);
  assert.doesNotMatch(zero.lead, /Kong|EXAMPLE/i);
});

test("Profile Detail rail never says Loading when profile data exists", () => {
  const unbound = buildProfileRailState({ profile: { unknown: true }, profileResolved: true });
  assert.notEqual(unbound.status, "pending");
  assert.equal(unbound.loadingLabel, null);
  assert.match(unbound.judgement, /Settings|faculty email/i);
  assert.doesNotMatch(unbound.judgement, /^Loading/i);
  assert.ok(!unbound.identity.some((line) => /^Loading/i.test(line)));
  assert.equal(unbound.unknowns.length, 0);
  assert.ok(unbound.facts.every((f) => !/Memory|Works|Lab links/i.test(f)));
  assert.match(JSON.stringify(unbound.facts), /preference|authentication/i);

  const pendingNull = buildProfileRailState({ profile: null, profileResolved: false });
  assert.equal(pendingNull.status, "unbound");
  assert.equal(pendingNull.loadingLabel, null);
  assert.doesNotMatch(pendingNull.judgement, /Loading/i);
  assert.ok(!pendingNull.identity.some((line) => /Loading/i.test(line)));

  const bound = buildProfileRailState({
    profile: {
      name_en: "Kong, De-Rong",
      email: PROFILE_TEST_EMAIL,
      discipline: "Finance",
      specialties: ["Asset Pricing"],
    },
    profileResolved: true,
  });
  assert.equal(bound.status, "context");
  assert.equal(bound.loadingLabel, null);
  assert.ok(!bound.identity.some((line) => /^Loading/i.test(line)));

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
  assert.equal(work.loadingLabel, null);
  assert.match(work.identity[0], /NFT/);
  assert.equal(work.primaryAction?.id, "ask-work");
  assert.match(work.primaryAction?.label || "", /Ask about this work/i);
  assert.doesNotMatch(work.primaryAction?.label || "", /Show research context/i);
});

test("selected work Detail primary action asks about the work", () => {
  const work = buildProfileRailState({
    profile: { name_en: "Kong, De-Rong" },
    profileResolved: true,
    selectedWork: { title: "Token taxonomy", type: "Publication", raw: "x" },
  });
  assert.equal(work.primaryAction?.id, "ask-work");
  assert.equal(work.primaryAction?.label, "Ask about this work");
});

test("Works presentation exposes real titles without fabricating success", () => {
  const works = buildWorks({
    paper_count: 18,
    publication_highlights: [
      "Kong (2023). Alternative investments in the Fintech era: The risk and return of Non-Fungible Token (NFT).",
      "Kong (2022). Something else about markets.",
    ],
  });
  assert.ok(works.items.length >= 2);
  assert.ok(works.items.length <= 6);
  for (const item of works.items) {
    assert.ok(item.title);
    assert.ok(item.type);
    assert.ok(item.relationship);
    assert.doesNotMatch(item.title, /success|ready|complete/i);
  }
});
