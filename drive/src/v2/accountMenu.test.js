import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { accountDisplayName, accountInitials } from "./accountPresentation.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const navSrc = readFileSync(join(__dirname, "nav-config.jsx"), "utf8");

test("primary sidebar is five workspace destinations only", () => {
  const block = navSrc.split("export const V2_SIDEBAR_TABS")[1].split("];")[0];
  assert.match(block, /id: "home"/);
  assert.match(block, /id: "library"/);
  assert.match(block, /id: "browse"/);
  assert.match(block, /id: "synthesis"/);
  assert.match(block, /id: "resources"/);
  assert.doesNotMatch(block, /id: "profile"/);
  assert.doesNotMatch(block, /id: "settings"/);
});

test("Profile and Settings remain routable via V2_ACCOUNT_TABS", () => {
  assert.match(navSrc, /export const V2_ACCOUNT_TABS/);
  const block = navSrc.split("export const V2_ACCOUNT_TABS")[1].split("];")[0];
  assert.match(block, /id: "profile"/);
  assert.match(block, /id: "settings"/);
});

test("account initials and display name reflect bound/unbound state", () => {
  assert.equal(accountDisplayName(null), "Research context");
  assert.equal(accountDisplayName({ unknown: true }), "Research context");
  assert.equal(
    accountDisplayName({ name_en: "Kong, De-Rong", email: "drkong@saturn.yzu.edu.tw" }),
    "Kong, De-Rong",
  );
  assert.equal(accountInitials(null, "YZ"), "YZ");
  assert.equal(accountInitials({ name_en: "Kong, De-Rong", email: "a@b.edu" }, "YZ"), "KD");
});
