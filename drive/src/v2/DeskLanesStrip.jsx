/**
 * Compact Home action row — Search / Discover / Ask.
 * Destinations unchanged from the previous desk-lanes strip.
 */
const ACTIONS = [
  {
    id: "library",
    label: "Search the lab",
    detail: "Browse vault holdings",
    tab: "library",
  },
  {
    id: "discover",
    label: "Discover data",
    detail: "Find and probe sources",
    tab: "browse",
  },
  {
    id: "ask",
    label: "Ask the assistant",
    detail: "Search, collect, join",
    prompt:
      "You are the lab research assistant. Start from our Google Drive vault and registry. " +
      "If I need something we do not hold, search Hugging Face or DataCite or probe a public URL, " +
      "then collect into the vault. Answer in plain language.",
  },
];

export function DeskLanesStrip({ holdings = 0, onGoTab, onAskComposer }) {
  return (
    <section className="rd-v2-home-actions" aria-label="Home actions">
      <div className="rd-v2-home-actions-row">
        {ACTIONS.map((action) => (
          <button
            key={action.id}
            type="button"
            className="rd-v2-home-action"
            onClick={() => {
              if (action.prompt) {
                onAskComposer?.(action.prompt);
                return;
              }
              onGoTab?.(action.tab);
            }}
          >
            <strong>{action.label}</strong>
            <span>
              {action.id === "library" && holdings > 0
                ? `${holdings} holdings`
                : action.detail}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
