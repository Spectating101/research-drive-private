import assert from "node:assert/strict";
import test from "node:test";
import { workspaceAskBindKey } from "./askWorkspaceBind.js";

test("Discover bind key follows open Explore query", () => {
  assert.equal(
    workspaceAskBindKey({
      surface: "discover",
      search_query: "Taiwan stock prices",
      workspace: { surface: "discover", query: "Taiwan stock prices" },
    }),
    "discover:taiwan stock prices|",
  );
});

test("Library and Synthesis bind keys follow selected work", () => {
  assert.equal(
    workspaceAskBindKey({
      surface: "library",
      dataset_id: "stablecoin_trust_engagement_weekly",
      workspace: { surface: "library", dataset_id: "stablecoin_trust_engagement_weekly" },
    }),
    "library:stablecoin_trust_engagement_weekly",
  );
  assert.equal(
    workspaceAskBindKey({
      surface: "synthesis",
      thread_id: "thr_1",
      workspace: { surface: "synthesis", thread_id: "thr_1" },
    }),
    "synthesis:thr_1",
  );
});

test("surface switches do not share the same bind key", () => {
  const discover = workspaceAskBindKey({
    surface: "discover",
    workspace: { surface: "discover", query: "Taiwan" },
  });
  const library = workspaceAskBindKey({
    surface: "library",
    workspace: { surface: "library", dataset_id: "x" },
  });
  assert.notEqual(discover, library);
});
