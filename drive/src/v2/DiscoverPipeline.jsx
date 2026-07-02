/** Discover acquisition pipeline — desktop main-canvas staging. */

const STEPS = [
  { id: "search", label: "Search" },
  { id: "probe", label: "Probe" },
  { id: "approve", label: "Approve" },
  { id: "collect", label: "Collect" },
  { id: "register", label: "Register" },
];

function activePipelineStep(counts = {}) {
  if ((counts.inLab || 0) > 0) return 4;
  if ((counts.queued || 0) > 0) return 2;
  if ((counts.probeReady || 0) > 0) return 1;
  return 0;
}

export function DiscoverPipeline({ counts, searching = false }) {
  const active = searching ? 0 : activePipelineStep(counts);
  const hasCounts = counts && (counts.probeReady || counts.queued || counts.inLab);

  return (
    <section className="rd-v2-discover-pipeline" aria-label="Acquisition pipeline">
      <div className="rd-v2-discover-pipeline-steps">
        {STEPS.map((step, index) => (
          <span
            key={step.id}
            className={[
              index < active ? "done" : "",
              index === active ? "on" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <b>{index + 1}</b>
            {step.label}
          </span>
        ))}
      </div>
      {hasCounts ? (
        <div className="rd-v2-discover-pipeline-counts">
          <span>{counts.probeReady} to probe</span>
          <span>{counts.queued} awaiting approval</span>
          <span>{counts.inLab} in lab</span>
        </div>
      ) : (
        <p className="rd-v2-discover-pipeline-lead">
          Search registries and public sources, then probe, approve, collect, and register in Library.
        </p>
      )}
    </section>
  );
}
