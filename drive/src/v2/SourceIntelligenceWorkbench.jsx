import { useState } from "react";
import {
  createResearchNeed,
  getResearchNeedShortlist,
  recordSourceOffering,
  rejectSourceOffering,
  selectSourceOfferingRoute,
  submitSourceOfferingCollect,
  syncSourceOfferingOutcome,
} from "@/v2/api";
import {
  offeringFromCandidate,
  preferredRouteForOffering,
  researchNeedFromQuery,
} from "@/v2/sourceIntelligence";

function stateLabel(value) {
  return String(value || "unknown").replace(/_/g, " ");
}

function evidenceBadge(offering) {
  const probe = (offering.evidence || []).find((row) => row.kind === "probe");
  if (probe?.status === "verified") return "probe verified";
  if (probe) return "probe seen";
  return "catalog only";
}

export function SourceIntelligenceWorkbench({
  query,
  candidates = [],
  probeByKey = {},
  destination = "",
  onSelectCandidate,
  onCollectionQueued,
}) {
  const [shortlist, setShortlist] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [compareIds, setCompareIds] = useState([]);
  const [actionKey, setActionKey] = useState("");

  const refresh = async (needId) => setShortlist(await getResearchNeedShortlist(needId));

  const qualify = async () => {
    if (!query?.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const need = await createResearchNeed(researchNeedFromQuery(query));
      await Promise.all(
        candidates.slice(0, 8).map((candidate) => {
          const key = candidate.candidate_key || candidate.dataset_id || candidate.url || "";
          const probe = probeByKey[key] || candidate.probe_snapshot || null;
          return recordSourceOffering(need.id, offeringFromCandidate(candidate, probe));
        }),
      );
      await refresh(need.id);
      setCompareIds([]);
    } catch (reason) {
      setError(reason?.message || "Could not qualify this source shortlist.");
    } finally {
      setBusy(false);
    }
  };

  const toggleCompare = (id) => {
    setCompareIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : current.length < 4 ? [...current, id] : current,
    );
  };

  const reject = async (offering) => {
    const reason = window.prompt(`Why is ${offering.title} not acceptable for this research need?`);
    if (!reason?.trim() || !shortlist?.need?.id) return;
    setActionKey(`reject:${offering.id}`);
    try {
      await rejectSourceOffering(shortlist.need.id, offering.id, reason.trim());
      await refresh(shortlist.need.id);
    } catch (failure) {
      setError(failure?.message || "Could not record the source decision.");
    } finally {
      setActionKey("");
    }
  };

  const selectRoute = async (offering) => {
    if (!shortlist?.need?.id) return;
    setActionKey(`route:${offering.id}`);
    try {
      await selectSourceOfferingRoute(shortlist.need.id, offering.id, {
        route: preferredRouteForOffering(offering),
        rationale: "Selected from an evidence-backed source shortlist.",
      });
      await refresh(shortlist.need.id);
    } catch (failure) {
      setError(failure?.message || "Could not record this route decision.");
    } finally {
      setActionKey("");
    }
  };

  const collect = async (offering) => {
    if (!shortlist?.need?.id) return;
    setActionKey(`collect:${offering.id}`);
    setError("");
    try {
      if (offering.decision?.state !== "selected") {
        await selectSourceOfferingRoute(shortlist.need.id, offering.id, {
          route: preferredRouteForOffering(offering),
          rationale: "Selected route immediately before approval-gated collection.",
        });
      }
      const out = await submitSourceOfferingCollect(shortlist.need.id, offering.id, {
        destination,
        limit: 200,
      });
      await refresh(shortlist.need.id);
      onCollectionQueued?.(out?.job, out?.offering || offering);
    } catch (failure) {
      setError(failure?.message || "Could not queue approval-gated collection.");
    } finally {
      setActionKey("");
    }
  };

  const syncOutcome = async (offering) => {
    if (!offering?.id) return;
    setActionKey(`sync:${offering.id}`);
    try {
      await syncSourceOfferingOutcome(offering.id, offering.decision?.collection?.job_id || "");
      await refresh(shortlist.need.id);
    } catch (failure) {
      setError(failure?.message || "Could not sync collection outcome.");
    } finally {
      setActionKey("");
    }
  };

  const selected = (shortlist?.offerings || []).filter((offering) => compareIds.includes(offering.id));
  return (
    <section className="rd-v2-source-intelligence" data-testid="source-intelligence-workbench">
      <header>
        <div>
          <span className="rd-v2-eyebrow">Source intelligence</span>
          <strong>Qualify this financial evidence need</strong>
          <p>Compare observed coverage, point-in-time integrity, access, and route before collection.</p>
        </div>
        <button type="button" className="rd-v2-btn sm primary" disabled={!query?.trim() || busy} onClick={qualify}>
          {busy ? "Qualifying…" : "Qualify shortlist"}
        </button>
      </header>
      {error ? <p className="rd-v2-source-intelligence-error">{error}</p> : null}
      {shortlist ? (
        <>
          <div className="rd-v2-source-intelligence-spec">
            <span>{shortlist.need.spec.market || "Market not specified"}</span>
            <span>{shortlist.need.spec.frequency || "Frequency not specified"}</span>
            <span>{shortlist.need.spec.point_in_time_required ? "Point-in-time required" : "PIT not required"}</span>
            <span>{(shortlist.need.spec.fields || []).join(" · ") || "Fields not specified"}</span>
          </div>
          <div className="rd-v2-source-intelligence-list">
            {shortlist.offerings.map((offering) => {
              const collection = offering.decision?.collection || {};
              const reliability = offering.reliability || {};
              return (
                <article key={offering.id} className={offering.decision?.state === "rejected" ? "rejected" : ""}>
                  <button type="button" className="rd-v2-source-intelligence-title" onClick={() => onSelectCandidate?.(offering)}>
                    <strong>{offering.title}</strong>
                    <span>Fit {offering.fit_score}/100</span>
                  </button>
                  <dl>
                    <div><dt>Coverage</dt><dd>{stateLabel(offering.fit?.coverage?.state)}</dd></div>
                    <div><dt>Fields</dt><dd>{stateLabel(offering.fit?.fields?.state)}</dd></div>
                    <div><dt>PIT</dt><dd>{stateLabel(offering.fit?.point_in_time?.state)}</dd></div>
                    <div><dt>Access</dt><dd>{stateLabel(offering.fit?.access?.state)}</dd></div>
                    <div><dt>Evidence</dt><dd>{evidenceBadge(offering)}</dd></div>
                    <div><dt>Reliability</dt><dd>{stateLabel(reliability.state)}{reliability.recent_failure_reason ? ` · ${reliability.recent_failure_reason}` : ""}</dd></div>
                  </dl>
                  <footer>
                    <label>
                      <input type="checkbox" checked={compareIds.includes(offering.id)} onChange={() => toggleCompare(offering.id)} />
                      Compare
                    </label>
                    {offering.decision?.state !== "selected" ? (
                      <button type="button" className="rd-v2-linkish" disabled={Boolean(actionKey)} onClick={() => selectRoute(offering)}>
                        Select route
                      </button>
                    ) : (
                      <span>Route selected</span>
                    )}
                    {offering.decision?.state !== "rejected" ? (
                      <>
                        <button type="button" className="rd-v2-linkish" disabled={Boolean(actionKey)} onClick={() => collect(offering)}>
                          {actionKey === `collect:${offering.id}` ? "Queuing…" : "Queue collect"}
                        </button>
                        <button type="button" className="rd-v2-linkish" onClick={() => reject(offering)}>Reject source</button>
                      </>
                    ) : (
                      <span>Rejected: {offering.decision.reason}</span>
                    )}
                    {collection.job_id ? (
                      <button type="button" className="rd-v2-linkish" disabled={Boolean(actionKey)} onClick={() => syncOutcome(offering)}>
                        Sync outcome ({collection.status || "linked"})
                      </button>
                    ) : null}
                  </footer>
                </article>
              );
            })}
          </div>
          {selected.length > 1 ? (
            <div className="rd-v2-source-intelligence-compare" data-testid="source-intelligence-compare">
              <strong>Compare selected sources</strong>
              {selected.map((offering) => (
                <div key={offering.id}>
                  <b>{offering.title}</b>
                  <span>{offering.coverage?.summary || offering.coverage?.frequency || "Coverage unknown"}</span>
                  <span>PIT: {stateLabel(offering.point_in_time?.status)}</span>
                  <span>Access: {stateLabel(offering.access?.status)}</span>
                  <span>Evidence: {evidenceBadge(offering)}</span>
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
