import assert from "node:assert/strict";
import test from "node:test";
test("no access group", async () => {
  const { SETTINGS_SECTION_ORDER } = await import("./settingsPresentation.js");
  assert.ok(!SETTINGS_SECTION_ORDER.includes("access"));
  assert.deepEqual(SETTINGS_SECTION_ORDER, ["context","workspace","advanced"]);
});
