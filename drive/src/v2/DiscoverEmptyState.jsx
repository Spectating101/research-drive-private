import { DISCOVER_SUGGESTIONS } from "@/v2/deskSeed";
import { handleEnterToRequestSubmit } from "@/v2/enterToSubmit";

/**
 * Discover Explore empty / starter — DISCOVER_FULL_SCALE_FREEZE.
 * Centre owns the evidence-need field; starters are shortcuts only.
 * Fill first viewport with need + method cue + starter ledger (no giant empty canvas).
 */
export function DiscoverEmptyState({ onSuggest, onCraftUrl }) {
  const suggestions = DISCOVER_SUGGESTIONS.length
    ? DISCOVER_SUGGESTIONS
    : ["TWSE governance", "MOPS filings", "stablecoin", "Indonesia IDX", "GDELT news shocks"];

  return (
    <div className="rd-v2-discover-explore-start" data-testid="discover-empty">
      <header className="rd-v2-discover-explore-need">
        <span className="rd-v2-eyebrow">Explore</span>
        <h2>What evidence are you looking for?</h2>
        <form
          className="rd-v2-discover-need-form"
          data-testid="discover-need-form"
          onSubmit={(event) => {
            event.preventDefault();
            const next = String(event.currentTarget.elements.need?.value || "").trim();
            if (next) onSuggest?.(next);
          }}
        >
          <textarea
            name="need"
            className="rd-v2-discover-need-input"
            data-testid="discover-need-query"
            rows={1}
            placeholder="Describe the evidence need — keyword, gap, or research question…"
            aria-label="Evidence need"
            onKeyDown={handleEnterToRequestSubmit}
          />
          <button type="submit" className="rd-v2-btn sm primary" aria-label="Search evidence need">
            Search
          </button>
        </form>
        <p className="rd-v2-ask-send-hint rd-v2-discover-enter-hint">Enter to search · ⇧↵ newline</p>
      </header>

      <ol className="rd-v2-discover-method-cue" aria-label="How Discover works">
        <li>
          <strong>1 · Need</strong>
          <span>State the evidence gap in research language.</span>
        </li>
        <li>
          <strong>2 · Rank</strong>
          <span>Lab holdings first, then external candidates.</span>
        </li>
        <li>
          <strong>3 · Evaluate</strong>
          <span>Detail owns fit, unknowns, and one primary action.</span>
        </li>
        <li>
          <strong>Or · Craft</strong>
          <span>Paste a public URL to draft a generic collect plan (approval required).</span>
        </li>
      </ol>

      {onCraftUrl ? (
        <form
          className="rd-v2-discover-craft-form"
          data-testid="discover-craft-form"
          onSubmit={(event) => {
            event.preventDefault();
            const next = String(event.currentTarget.elements.craftUrl?.value || "").trim();
            if (next) onCraftUrl(next);
          }}
        >
          <label className="rd-v2-eyebrow" htmlFor="rd-discover-craft-url">
            Craft a URL plan
          </label>
          <div className="rd-v2-discover-need-form">
            <input
              id="rd-discover-craft-url"
              name="craftUrl"
              type="url"
              className="rd-v2-discover-need-input"
              data-testid="discover-craft-url"
              placeholder="https://example.com/data.csv or API endpoint…"
              aria-label="Public URL to craft a collect plan"
            />
            <button type="submit" className="rd-v2-btn sm" aria-label="Craft collect plan for URL">
              Craft
            </button>
          </div>
        </form>
      ) : null}

      <section className="rd-v2-discover-explore-starters" aria-label="Suggested evidence needs">
        <span className="rd-v2-eyebrow">Suggested needs</span>
        <ul className="rd-v2-discover-starter-list">
          {suggestions.slice(0, 6).map((s) => (
            <li key={s}>
              <button type="button" className="rd-v2-discover-starter-row" onClick={() => onSuggest?.(s)}>
                <strong>{s}</strong>
                <em>Search →</em>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
