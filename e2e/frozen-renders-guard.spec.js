/**
 * Routing guard. FROZEN_RENDERS.txt is the composition authority as of
 * 2026-08-14. These tests fail if an agent reintroduces a withdrawn July
 * composition or if the frozen set stops being reachable.
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const FROZEN = path.join("docs", "design-artifacts-20260805", "FROZEN_RENDERS.txt");
const WITHDRAWN = [
  "DISCOVER_FULL_SCALE_FREEZE_2026-07-15",
  "LIBRARY_FULL_SCALE_FREEZE_2026-07-15",
  "FROZEN_PAGE_CHANGE_LOCK_2026-07-16",
  "UX_CONVERGENCE_SNAPSHOT_2026-07-16",
];

function activeDocs(dir = "docs", out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== "superseded" && e.name !== "screenshots-review") activeDocs(p, out); }
    else if (e.name.endsWith(".md")) out.push(p);
  }
  return out;
}

test("the frozen render set exists and carries every state", () => {
  expect(fs.existsSync(FROZEN), `${FROZEN} is the composition authority and must exist`).toBe(true);
  const t = fs.readFileSync(FROZEN, "utf8");
  for (const n of [1,2,3,4,5,6,7,8,9,10,11]) {
    expect(t, `frozen render ${n} is missing`).toContain(`=== ${n} ·`);
  }
  expect(t).toContain("24 nav | 77 centre | 37 Detail/Ask rail");
});

test("no active document cites a withdrawn July composition as authority", () => {
  const offenders = [];
  for (const f of activeDocs()) {
    const t = fs.readFileSync(f, "utf8");
    for (const w of WITHDRAWN) {
      if (!t.includes(w)) continue;
      const cited = t.split("\n").filter((l) => l.includes(w) && !/supersede|withdrawn|retained|historical|not implementation authority/i.test(l));
      if (cited.length) offenders.push(`${f}: ${cited[0].trim().slice(0, 110)}`);
    }
  }
  expect(offenders, `withdrawn July compositions are cited as authority:\n${offenders.join("\n")}`).toEqual([]);
});

test("the withdrawn July wireframes are not back in the tree", () => {
  const back = WITHDRAWN.filter((w) => fs.existsSync(path.join("docs", `${w}.md`)));
  expect(back, `withdrawn compositions reappeared in docs/: ${back.join(", ")}`).toEqual([]);
});
