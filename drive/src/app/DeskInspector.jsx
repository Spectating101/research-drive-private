export function DeskInspector({ show, tab, onTabChange, detailsPanel, assistantPanel }) {
  if (!show) return null;

  return (
    <aside className={`yzu-inspector inspector-with-assistant inspector-tab-${tab}`}>
      <div className="yzu-inspector-stack">
        <div className="rd-inspector-tabs" role="tablist" aria-label="Inspector">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "details"}
            className={tab === "details" ? "active" : ""}
            onClick={() => onTabChange("details")}
          >
            Details
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "assistant"}
            className={tab === "assistant" ? "active" : ""}
            onClick={() => onTabChange("assistant")}
          >
            Assistant
          </button>
        </div>
        {tab === "details" ? detailsPanel : (
          <div className="rd-inspector-chat-panel">{assistantPanel}</div>
        )}
      </div>
    </aside>
  );
}
