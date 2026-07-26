import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  dedupeDiscoverCandidates,
  descriptiveLine,
  humanizeDiscoverDescription,
  sanitizeDiscoverPlainText,
} from "./browseMeta.js";

describe("sanitizeDiscoverPlainText", () => {
  it("strips externally supplied HTML into plain text", () => {
    assert.equal(
      sanitizeDiscoverPlainText("<p>TWSE <b>daily</b> prices &amp; volumes</p>"),
      "TWSE daily prices & volumes",
    );
  });

  it("collapses whitespace without inventing copy", () => {
    assert.equal(sanitizeDiscoverPlainText("  a \n\n b  "), "a b");
    assert.equal(sanitizeDiscoverPlainText(""), "");
  });
});

describe("descriptiveLine / humanizeDiscoverDescription", () => {
  it("never surfaces raw markup from external descriptions", () => {
    const line = descriptiveLine({
      description: "<script>alert(1)</script><em>Open market index</em>",
      source: "DataCite",
    });
    assert.equal(line.includes("<"), false);
    assert.equal(line.includes("script"), false);
    assert.match(line, /Open market index/);
  });

  it("humanizes connector terms after plain-text sanitization", () => {
    const text = humanizeDiscoverDescription("<b>daily_prices</b> · onchain_crypto");
    assert.equal(text.includes("<"), false);
    assert.match(text, /daily market prices/);
    assert.match(text, /on-chain market data/);
  });
});

describe("dedupeDiscoverCandidates", () => {
  it("suppresses exact duplicate candidate identities", () => {
    const rows = dedupeDiscoverCandidates([
      { dataset_id: "twse_index", title: "TWSE", source: "catalog" },
      { dataset_id: "twse_index", title: "TWSE copy", source: "web" },
      { title: "Same DOI paper", doi: "10.1234/abc" },
      { title: "Same DOI paper again", doi: "https://doi.org/10.1234/abc" },
    ]);
    assert.equal(rows.length, 2);
    assert.equal(rows[0].dataset_id, "twse_index");
    assert.equal(candidateKeyOf(rows[1]), "doi:10.1234/abc");
  });

  it("keeps distinct sources that do not share an identity key", () => {
    const rows = dedupeDiscoverCandidates([
      { title: "Stablecoin flows", url: "https://a.example/x", source: "Tavily" },
      { title: "Stablecoin flows", url: "https://b.example/x", source: "DataCite" },
      { title: "Untitled fragment", source: "web" },
      { title: "Another fragment", source: "hf" },
    ]);
    assert.equal(rows.length, 4);
  });
});

function candidateKeyOf(row) {
  return row.candidate_key || "";
}
