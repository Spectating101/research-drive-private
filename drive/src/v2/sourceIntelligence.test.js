import assert from "node:assert/strict";
import test from "node:test";

import {
  offeringFromCandidate,
  preferredRouteForOffering,
  researchNeedFromQuery,
} from "./sourceIntelligence.js";

test("turns a finance query into an editable evidence specification", () => {
  const need = researchNeedFromQuery("Point-in-time quarterly revenue for Taiwan listed issuers");

  assert.equal(need.point_in_time_required, true);
  assert.equal(need.frequency, "quarterly");
  assert.equal(need.market, "TW");
  assert.ok(need.fields.includes("revenue"));
});

test("preserves candidate identity and uncertainty when forming an offering", () => {
  const offering = offeringFromCandidate({
    candidate_key: "source:twse-filings",
    title: "TWSE filings",
    source: "TWSE",
    grain: "issuer-quarter",
    coverage: "2010–present",
    connector_id: "twse_filings",
  });

  assert.equal(offering.candidate_key, "source:twse-filings");
  assert.equal(offering.access.status, "inferred");
  assert.equal(offering.point_in_time.status, "unknown");
  assert.equal(offering.evidence[0].kind, "catalog");
});

test("probe evidence upgrades access from inferred to verified", () => {
  const offering = offeringFromCandidate(
    {
      candidate_key: "source:twse-filings",
      title: "TWSE filings",
      url: "https://example.com/filings",
    },
    {
      ok: true,
      connector: { connector_id: "twse_filings" },
      point_in_time: { status: "verified" },
    },
  );

  assert.equal(offering.access.status, "verified");
  assert.equal(offering.point_in_time.status, "verified");
  assert.equal(offering.evidence[1].kind, "probe");
  assert.equal(preferredRouteForOffering(offering).kind, "public_connector");
});
