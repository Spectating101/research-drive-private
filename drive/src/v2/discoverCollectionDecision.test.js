import assert from "node:assert/strict";
import test from "node:test";

import { buildVerifiedConnectorProposal, decideDiscoverCollection } from "./discoverCollectionDecision.js";

test("uses direct collection only for a probed connector", () => {
  const decision = decideDiscoverCollection({
    candidate: { candidate_key: "url:https://data.example/public.csv", url: "https://data.example/public.csv" },
    probe: { connector: { connector_id: "public_csv" } },
  });

  assert.deepEqual(decision, { kind: "direct", connectorId: "public_csv" });
});

test("opens an acquisition brief when a source has no approved connector", () => {
  const decision = decideDiscoverCollection({
    candidate: { candidate_key: "doi:10.1000/example", doi: "10.1000/example" },
    probe: { connector: null },
  });

  assert.equal(decision.kind, "brief");
  assert.match(decision.reason, /connector/i);
});

test("opens an acquisition brief when a probe reports an access gate", () => {
  const decision = decideDiscoverCollection({
    candidate: { candidate_key: "url:https://vendor.example/data", url: "https://vendor.example/data" },
    probe: { connector: { connector_id: "vendor_csv" }, needs_approval: true },
  });

  assert.equal(decision.kind, "brief");
  assert.match(decision.reason, /approval/i);
});

test("builds a reviewable intent proposal only from a verified connector", () => {
  const proposal = buildVerifiedConnectorProposal({
    candidate: {
      candidate_key: "url:https://data.example/public.csv",
      title: "Public research CSV",
      url: "https://data.example/public.csv",
    },
    probe: { connector: { connector_id: "public_csv" } },
  });

  assert.equal(proposal.routes.length, 1);
  assert.equal(proposal.routes[0].connector_id, "public_csv");
  assert.equal(proposal.routes[0].candidate_key, "url:https://data.example/public.csv");
  assert.equal(proposal.recommended_route_id, proposal.routes[0].id);
});

test("does not invent an intent proposal without a connector", () => {
  assert.equal(
    buildVerifiedConnectorProposal({
      candidate: { candidate_key: "doi:10.1000/example" },
      probe: {},
    }),
    null,
  );
});
