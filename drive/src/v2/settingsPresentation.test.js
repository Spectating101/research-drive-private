import test from "node:test";
import assert from "node:assert/strict";
import { SETTINGS_SECTION_ORDER, buildSettingsRailState, settingsAdvancedDefaultOpen } from "./settingsPresentation.js";
import { loadSettings, resetLocalPreferences, saveSettings } from "./settingsStore.js";

test("Settings centre model is Research context → Workspace → Advanced", () => {
  assert.deepEqual(SETTINGS_SECTION_ORDER, ["context", "workspace", "advanced"]);
});
test("Advanced disclosure defaults to collapsed", () => {
  assert.equal(settingsAdvancedDefaultOpen(), false);
});
test("Settings Detail shows local values", () => {
  const context = buildSettingsRailState({
    group: "context",
    settings: { email: "drkong@saturn.yzu.edu.tw", defaultTab: "home" },
    profile: { name_en: "Kong, De-Rong" },
  });
  assert.equal(context.primaryAction?.id, "clear-context");
  assert.equal(context.judgement, null);
});
test("saveSettings and resetLocalPreferences persist", () => {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  saveSettings({ email: "drkong@saturn.yzu.edu.tw", defaultTab: "library", onSelect: "ask" });
  assert.equal(loadSettings().defaultTab, "library");
  assert.equal(resetLocalPreferences().email, "");
});
