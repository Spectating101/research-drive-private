/** Discover acquisition pipeline — job-derived staging only (no fake probe/in-lab theater). */

const STEPS = [
  { id: "search", label: "Search" },
  { id: "probe", label: "Probe" },
  { id: "approve", label: "Approve" },
  { id: "collect", label: "Collect" },
  { id: "register", label: "Register" },
];

function activePipelineStep(counts = {}) {
  if ((counts.awaiting || 0) > 0) return 2;
  if ((counts.running || 0) > 0 || (counts.queued || 0) > 0) return 3;
  return 0;
}

export function DiscoverPipeline({ counts = {}, searching = false }) {
  const active = searching ? 0 : activePipelineStep(counts);
  const awaiting = counts.awaiting || 0;
  const running = counts.running || 0;
  const queued = counts.queued || 0;
  const hasCounts = awaiting > 0 || running > 0 || queued > 0;

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
        <div className="rd-v2-discover-pipeline-counts" data-testid="discover-pipeline-counts">
          <span className={awaiting > 0 ? "warn" : ""}>{awaiting} awaiting</span>
          <span>{running} running</span>
          <span>{queued} queued</span>
        </div>
      ) : (
        <p className="rd-v2-discover-pipeline-lead">
          Search, probe, and Add to lab — then approve and collect here. Not resource spend.
        </p>
      )}
    </section>
  );
}
