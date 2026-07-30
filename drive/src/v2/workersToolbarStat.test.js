import assert from "node:assert/strict";
import test from "node:test";
import {
  formatCollectorState,
  formatWorkersToolbarStat,
  workersToolbarFieldsFromRollup,
} from "./workersToolbarStat.js";

test("mixed joined+stale does not collapse to 0/N online", () => {
  assert.equal(
    formatWorkersToolbarStat({ online: 0, joined: 3, stale: 3, total: 4 }),
    "3 joined · 3 stale / 4",
  );
  assert.equal(
    formatWorkersToolbarStat({ joined: 0, stale: 3, total: 4, online: 0 }),
    "0 joined · 3 stale / 4",
  );
  assert.doesNotMatch(
    formatWorkersToolbarStat({ online: 0, joined: 3, stale: 3, total: 4 }),
    /online|available|busy/i,
  );
});

test("fresh+stale phrase stays explicit and preserves total", () => {
  assert.equal(
    formatWorkersToolbarStat({ fresh: 0, stale: 3, total: 3 }),
    "0 fresh · 3 stale / 3",
  );
});

test("available is used only when that field is explicitly supplied", () => {
  assert.equal(formatWorkersToolbarStat({ available: 2, total: 4 }), "2/4 available");
  assert.notEqual(formatWorkersToolbarStat({ online: 2, total: 4 }), "2/4 available");
  assert.equal(formatWorkersToolbarStat({ online: 2, total: 4 }), "2/4 online");
});

test("joined is never aliased as online", () => {
  assert.equal(formatWorkersToolbarStat({ joined: 0, total: 4 }), "0/4 joined");
  assert.equal(formatWorkersToolbarStat({ busy: 2, total: 12 }), "2/12 busy");
});

test("rollup field merge keeps compute joined/stale without inventing available", () => {
  const fields = workersToolbarFieldsFromRollup({
    hero: { workers: { busy: 0, total: 4, online: 0 } },
    compute: {
      windows_lab: { joined: 3, total: 4 },
      runtime: { worker_pools: { total: 4, online: 0, stale: 3, busy: 0 } },
    },
  });
  assert.equal(fields.joined, 3);
  assert.equal(fields.stale, 3);
  assert.equal(fields.online, 0);
  assert.equal(fields.available, undefined);
  assert.equal(formatWorkersToolbarStat(fields), "3 joined · 3 stale / 4");
});

test("runtime stale wins over hero stale:0 and drops conflicting available", () => {
  const fields = workersToolbarFieldsFromRollup({
    hero: {
      workers: {
        busy: 0,
        total: 4,
        online: 0,
        joined: 3,
        stale: 0,
        available: 3,
      },
    },
    compute: {
      windows_lab: { joined: 3, total: 4, online: 0, stale: 0, available: 3 },
      runtime: { worker_pools: { total: 4, busy: 0, stale: 3 } },
    },
  });
  assert.equal(fields.joined, 3);
  assert.equal(fields.stale, 3);
  assert.equal(fields.available, undefined);
  assert.equal(formatWorkersToolbarStat(fields), "3 joined · 3 stale / 4");
  assert.doesNotMatch(formatWorkersToolbarStat(fields), /online|available/i);
});

test("online/total preserved when joined/stale are absent", () => {
  assert.equal(formatWorkersToolbarStat({ online: 0, total: 4 }), "0/4 online");
  assert.equal(formatWorkersToolbarStat({ online: 2, total: 4 }), "2/4 online");
});

/* ── VC-4: canonical collector vocabulary ─────────────────────────────── */

test("collector state uses one vocabulary and one denominator", () => {
  assert.equal(
    formatCollectorState({ total: 12, online: 3, idle: 2, busy: 1 }),
    "12 registered · 3 connected · 2 idle · 1 running",
  );
});

test("collector state omits dimensions the backend did not report", () => {
  assert.equal(formatCollectorState({ total: 12, busy: 2 }), "12 registered · 2 running");
  assert.equal(formatCollectorState({ total: 4 }), "4 registered");
});

test("collector state never infers a missing dimension", () => {
  // online + idle must not be summed into an invented "available" count.
  const out = formatCollectorState({ total: 12, online: 3, idle: 2 });
  assert.doesNotMatch(out, /available/i);
  assert.equal(out, "12 registered · 3 connected · 2 idle");
});

test("declared membership stands in for connected only when presence is absent", () => {
  assert.equal(formatCollectorState({ total: 12, joined: 3 }), "12 registered · 3 connected");
  // Live presence wins over declared membership.
  assert.equal(
    formatCollectorState({ total: 12, joined: 9, online: 3 }),
    "12 registered · 3 connected",
  );
});

test("collector state reports absence explicitly", () => {
  assert.equal(formatCollectorState({}), "Not reported");
  assert.equal(formatCollectorState(null), "Not reported");
});

test("stale membership remains visible rather than silently dropped", () => {
  assert.equal(
    formatCollectorState({ total: 4, joined: 3, stale: 3 }),
    "4 registered · 3 connected · 3 stale",
  );
});
