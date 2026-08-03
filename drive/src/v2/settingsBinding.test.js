import test from "node:test";
import assert from "node:assert/strict";
import { SETTINGS_SECTION_ORDER, buildSettingsRailState, settingsAdvancedDefaultOpen } from "./settingsPresentation.js";
export { SETTINGS_SECTION_ORDER, settingsAdvancedDefaultOpen };
export function buildSettingsDetailFacts(opts={}) { return buildSettingsRailState(opts).facts; }
test("order", () => assert.deepEqual(SETTINGS_SECTION_ORDER, ["context","workspace","advanced"]));
test("collapsed", () => assert.equal(settingsAdvancedDefaultOpen(), false));
test("clear", () => {
  assert.equal(buildSettingsRailState({ group:"context", settings:{email:"a@b.edu"} }).primaryAction?.id, "clear-context");
  assert.equal(buildSettingsRailState({ group:"context", settings:{email:""} }).primaryAction, null);
});
