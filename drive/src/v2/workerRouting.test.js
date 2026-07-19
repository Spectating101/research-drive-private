import assert from "node:assert/strict";
import test from "node:test";

import { evaluateJobRouting, normalizeJobRequirements, normalizeWorker } from "./workerRouting.js";

test("derives stable capability requirements from YZU job types", () => {
  assert.deepEqual(normalizeJobRequirements({ type: "scraper_run" }).capabilities, ["browser"]);
  assert.deepEqual(normalizeJobRequirements({ type: "archive_upload" }).capabilities, ["archive"]);
  assert.deepEqual(
    normalizeJobRequirements({ type: "registered_pipeline", required_capabilities: ["gpu"] }).capabilities,
    ["gpu", "pipeline"],
  );
});

test("normalizes worker capability aliases", () => {
  const worker = normalizeWorker({ id: "spectator", status: "online", capabilities: ["Puppeteer", "python3"] });
  assert.equal(worker.online, true);
  assert.deepEqual(worker.capabilities, ["browser", "python"]);
});

test("accepts a correctly assigned capable worker", () => {
  const routing = evaluateJobRouting({
    type: "scraper_run",
    assigned_worker: { id: "spectator", status: "online", capabilities: ["cdp", "python"] },
  });
  assert.equal(routing.status, "satisfied");
  assert.equal(routing.warn, false);
  assert.deepEqual(routing.eligible_workers, ["spectator"]);
});

test("surfaces an incompatible assigned worker as blocked", () => {
  const routing = evaluateJobRouting({
    type: "scraper_run",
    assigned_worker: { id: "asus-01", status: "online", capabilities: ["python", "http"] },
  });
  assert.equal(routing.status, "blocked");
  assert.equal(routing.warn, true);
  assert.deepEqual(routing.missing, ["browser"]);
});

test("finds eligible unassigned workers from reported inventory", () => {
  const routing = evaluateJobRouting(
    { type: "archive_upload" },
    [
      { id: "asus-01", status: "online", capabilities: ["python", "http"] },
      { id: "optiplex", status: "online", capabilities: ["rclone", "python"] },
    ],
  );
  assert.equal(routing.status, "eligible");
  assert.deepEqual(routing.eligible_workers, ["optiplex"]);
});

test("stays unknown rather than claiming blocked when capabilities are not reported", () => {
  const routing = evaluateJobRouting({ type: "harvest_shard" }, [{ id: "asus-01", status: "online" }]);
  assert.equal(routing.status, "unknown");
  assert.equal(routing.warn, false);
});
