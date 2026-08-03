/**
 * Profile binding persistence — faculty email is an explicit browser preference.
 * No automatic pilot identity; unbound never renders empty Memory/Works/Lab shells.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { loadUserEmail, saveUserEmail } from "./deskSession.js";
import {
  PROFILE_TEST_EMAIL,
  isProfileBound,
  profileSectionsVisible,
  buildUnboundProfileCentre,
  buildProfileRailState,
} from "./profilePresentation.js";

function withFakeStorage(run) {
  const store = new Map();
  const fake = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => {
      store.set(k, String(v));
    },
    removeItem: (k) => {
      store.delete(k);
    },
  };
  const prevLocal = globalThis.localStorage;
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: fake,
  });
  try {
    return run(store);
  } finally {
    if (prevLocal === undefined) {
      delete globalThis.localStorage;
    } else {
      Object.defineProperty(globalThis, "localStorage", {
        configurable: true,
        value: prevLocal,
      });
    }
  }
}

test("no automatic identity — empty browser stays unbound", () => {
  withFakeStorage(() => {
    assert.equal(loadUserEmail(), "");
    assert.equal(isProfileBound({ unknown: true }), false);
    assert.equal(profileSectionsVisible({ unknown: true }), false);
    const zero = buildUnboundProfileCentre();
    assert.doesNotMatch(JSON.stringify(zero), /drkong|Kong|EXAMPLE|pilot/i);
  });
});

test("binding + reload persistence via localStorage preference", () => {
  withFakeStorage(() => {
    const saved = saveUserEmail(PROFILE_TEST_EMAIL);
    assert.equal(saved, PROFILE_TEST_EMAIL);
    assert.equal(loadUserEmail(), PROFILE_TEST_EMAIL);

    // Simulate reload: read keys again without re-saving
    assert.equal(loadUserEmail(), PROFILE_TEST_EMAIL);

    // Clear is also persistent
    saveUserEmail("");
    assert.equal(loadUserEmail(), "");
  });
});

test("unknown registry stub is unbound — no empty section clutter", () => {
  const stub = {
    unknown: true,
    name_en: "Nobody",
    email: "nobody@yzu.edu.tw",
    specialties: [],
    publication_highlights: [],
    lab_fintech_stack: [],
  };
  assert.equal(isProfileBound(stub), false);
  assert.equal(profileSectionsVisible(stub), false);
  const rail = buildProfileRailState({ profile: stub, profileResolved: true });
  assert.equal(rail.status, "unbound");
  assert.doesNotMatch(rail.identity.join(" "), /Nobody/i);
  assert.equal(rail.unknowns.length, 0);
});

test("resolved Kong profile is bound and shows section order", () => {
  const kong = {
    unknown: false,
    name_en: "Kong, De-Rong",
    email: PROFILE_TEST_EMAIL,
    specialties: ["FinTech"],
  };
  assert.equal(isProfileBound(kong), true);
  assert.equal(profileSectionsVisible(kong), true);
});
