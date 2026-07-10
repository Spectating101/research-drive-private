import { useMemo } from "react";
import { downloadText } from "@/v2/api";
import {
  computeDatasetOverlap,
  coverageWidth,
  savePinnedCompare,
} from "@/v2/clusterOverlap";
import { displayName } from "@/v2/datasetMeta";
import { Chip, ChipRow, PageShell, StatementRow, StatementSection } from "@/v2/ui";

export function ClusterPage({
  datasets,
  compareIds,
  onCompareChange,
  onGoTab,
  onAskComposer,
}) {
  const picks = useMemo(() => {
    const ids = compareIds.filter(Boolean);
    return ids.map((id) => datasets.find((d) => d.dataset_id === id)).filter(Boolean);
  }, [datasets, compareIds]);

  const [aId, bId] = compareIds;
  const setA = (id) => onCompareChange([id, bId]);
  const setB = (id) => onCompareChange([aId, id]);

  const overlap = useMemo(() => {
    if (picks.length < 2) return null;
    return computeDatasetOverlap(picks[0], picks[1]);
  }, [picks]);

  const exportKeys = () => {
    if (!overlap) return;
    const lines = [
      `# ${picks[0].dataset_id} × ${picks[1].dataset_id}`,
      `shared: ${overlap.shared.join(", ") || "—"}`,
      `only_a: ${overlap.onlyA.join(", ") || "—"}`,
      `only_b: ${overlap.onlyB.join(", ") || "—"}`,
      `grain_match: ${overlap.grainMatch}`,
    ];
    downloadText(`join-keys-${aId}-${bId}.txt`, lines.join("\n"));
  };

  return (
    <PageShell title="Cluster" lead="Coverage & overlap — registry join keys, not row counts" footer="click timeline gap → highlight missing span">
      <div className="rd-v2-cluster-toolbar">
        Compare:{" "}
        <select value={aId || ""} onChange={(e) => setA(e.target.value)}>
          <option value="">Select A</option>
          {datasets.map((d) => (
            <option key={d.dataset_id} value={d.dataset_id}>
              {displayName(d)}
            </option>
          ))}
        </select>{" "}
        <select value={bId || ""} onChange={(e) => setB(e.target.value)}>
          <option value="">Select B</option>
          {datasets.map((d) => (
            <option key={d.dataset_id} value={d.dataset_id}>
              {displayName(d)}
            </option>
          ))}
        </select>{" "}
        <button type="button" className="rd-v2-btn sm" onClick={() => onGoTab("library")}>
          + Library
        </button>
        <button
          type="button"
          className="rd-v2-btn sm"
          disabled={picks.length < 2}
          onClick={() => {
            if (picks.length < 2) return;
            savePinnedCompare(picks[0].dataset_id, picks[1].dataset_id, `${displayName(picks[0])} × ${displayName(picks[1])}`);
          }}
        >
          Save compare
        </button>
        {overlap ? (
          <span className="rd-v2-cluster-meta">
            {datasets.length} mapped · {overlap.label}
          </span>
        ) : null}
      </div>

      <div className="rd-v2-toolbar inline">
        <Chip active>All</Chip>
        <Chip>Asia</Chip>
        <Chip>Crypto</Chip>
        <Chip>Taiwan</Chip>
      </div>

      <StatementSection title="Compare summary">
        <StatementRow
          label="Dataset A"
          metric={picks[0] ? displayName(picks[0]) : "Not selected"}
          sublabel={picks[0]?.grain || "Pick from Library"}
          detail={picks[0]?.dataset_id || "Select A to start"}
        />
        <StatementRow
          label="Dataset B"
          metric={picks[1] ? displayName(picks[1]) : "Not selected"}
          sublabel={picks[1]?.grain || "Pick a second dataset"}
          detail={picks[1]?.dataset_id || "Select B to compare"}
        />
        <StatementRow
          label="Join readiness"
          metric={overlap ? `${overlap.pct}% overlap` : "Waiting"}
          sublabel={overlap?.grainMatch ? "grain matches" : "verify grain"}
          detail={overlap?.join ? `Join on ${overlap.join}` : "Shared keys appear after two selections"}
          warn={Boolean(overlap && overlap.pct < 50)}
        />
      </StatementSection>

      <div className="rd-v2-timeline">
        <div className="years">
          <span>2018</span>
          <span>2020</span>
          <span>2022</span>
          <span>2024</span>
          <span>now</span>
        </div>
        {(picks.length ? picks : datasets.slice(0, 3)).map((d, i) => (
          <div key={d.dataset_id} className="rd-v2-bar-row">
            <span className="rd-v2-bar-label">{displayName(d)}</span>
            <div className={`rd-v2-bar${i === 2 && picks.length < 3 ? " gap" : ""}`}>
              <span style={{ width: `${coverageWidth(d)}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="rd-v2-overlap-section">
        {overlap ? (
          <>
            <span className={`rd-v2-overlap-badge${overlap.pct >= 50 ? "" : overlap.pct > 0 ? " partial" : " none"}`}>
              {overlap.pct}% key overlap — {displayName(picks[0])} × {displayName(picks[1])}
            </span>
            <div className="rd-v2-venn-row">
              <div className="rd-v2-venn-set">
                <div className="rd-v2-venn-set-title">Only A</div>
                <span className="muted small">{overlap.onlyA.join(" · ") || "—"}</span>
              </div>
              <div className="rd-v2-venn-set">
                <div className="rd-v2-venn-set-title">Shared keys</div>
                <span className="muted small">{overlap.shared.join(" · ") || "—"}</span>
              </div>
              <div className="rd-v2-venn-set">
                <div className="rd-v2-venn-set-title">Only B</div>
                <span className="muted small">{overlap.onlyB.join(" · ") || "—"}</span>
              </div>
            </div>
            {overlap.join ? <p className="muted small" style={{ marginTop: 6 }}>Join on: <code>{overlap.join}</code></p> : null}
            <p className="muted small" style={{ marginTop: 8 }}>
              Overlap is context for Composer — use Ask to compare join viability or request a synthesis run.
            </p>
          </>
        ) : (
          <p className="muted">Pick two datasets above to compare overlap.</p>
        )}
      </div>

      <ChipRow>
        <Chip onClick={() => onGoTab("browse")}>Find in Discover</Chip>
        <Chip
          onClick={() =>
            onAskComposer?.(
              `Compare ${picks[0]?.dataset_id} and ${picks[1]?.dataset_id} for synthesis. Shared keys: ${overlap?.shared?.join(", ") || "none"}. Use the research tools to assess join viability and recommend next steps.`,
            )
          }
          disabled={!overlap}
        >
          Ask about overlap
        </Chip>
        <Chip onClick={exportKeys} disabled={!overlap}>
          Export join keys
        </Chip>
        <Chip onClick={() => onGoTab("library")}>Open Library</Chip>
      </ChipRow>
    </PageShell>
  );
}
