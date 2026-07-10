import { Strip } from "@/v2/ui";

/**
 * Three-lane desk — matches DESK_STATUS + UI contract.
 * Library ≈ Google Drive vault; Discover ≈ HF/DOI/web procure; Ask ≈ Composer agent.
 * No direct API calls — lanes route context into the Ask rail.
 */
const LANES = [
  {
    id: "library",
    label: "Library",
    metric: "Google Drive vault",
    detail: "What the lab already holds — folders, query-ready panels, archive paths.",
    tab: "library",
  },
  {
    id: "discover",
    label: "Discover",
    metric: "Hugging Face · DOI · web",
    detail: "Find what is missing. The assistant procures via catalog search, then collects into the vault.",
    tab: "browse",
  },
  {
    id: "ask",
    label: "Ask",
    metric: "Lab assistant",
    detail: "Search, preview, import, approve jobs, and join sources — Composer uses the research tools for you.",
    prompt:
      "You are the lab research assistant. Start from our Google Drive vault and registry. " +
      "If I need something we do not hold, search Hugging Face or DataCite or probe a public URL, " +
      "then collect into the vault. Answer in plain language.",
  },
];

export function DeskLanesStrip({ holdings = 0, onGoTab, onAskComposer }) {
  return (
    <section className="rd-v2-desk-lanes" aria-label="Research desk lanes">
      <p className="muted small rd-v2-desk-lanes-lead">
        Three lanes — browse the vault like Drive, discover and probe like Hugging Face, and use Ask when you need
        multi-step procure, joins, or cross-source reasoning.
      </p>
      <ul className="rd-v2-desk-lanes-list">
        {LANES.map((lane) => (
          <li key={lane.id}>
            <button
              type="button"
              className="rd-v2-desk-lane-card"
              onClick={() => {
                if (lane.prompt) {
                  onAskComposer?.(lane.prompt);
                  return;
                }
                onGoTab?.(lane.tab);
              }}
            >
              <span className="rd-v2-desk-lane-label">{lane.label}</span>
              <strong>{lane.metric}</strong>
              <span className="muted small">{lane.detail}</span>
              {lane.id === "library" && holdings > 0 ? (
                <span className="rd-v2-desk-lane-meta">{holdings} registered holdings</span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
      <Strip>
        Collect once → lands in GDrive <code>collection/</code> → registered for the next search hit.
      </Strip>
    </section>
  );
}
