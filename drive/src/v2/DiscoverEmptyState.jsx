import { DISCOVER_SUGGESTIONS } from "@/v2/deskSeed";

/**
 * Discover Explore empty / starter — DISCOVER_FULL_SCALE_FREEZE.
 * Short need prompt + starters. No marketing essay.
 */
export function DiscoverEmptyState({ onSuggest }) {
  const suggestions = DISCOVER_SUGGESTIONS.length
    ? DISCOVER_SUGGESTIONS
    : ["TWSE governance", "MOPS filings", "stablecoin", "Indonesia IDX", "GDELT news shocks"];

  return (
    <div className="rd-v2-discover-explore-start" data-testid="discover-empty">
      <header className="rd-v2-discover-explore-need">
        <span className="rd-v2-eyebrow">Explore</span>
        <h2>What evidence are you looking for?</h2>
        <p className="rd-v2-discover-explore-hint muted">
          Search the header — results stay ranked here; Detail judges the selected source.
        </p>
      </header>

      <section className="rd-v2-discover-explore-starters" aria-label="Suggested evidence needs">
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
