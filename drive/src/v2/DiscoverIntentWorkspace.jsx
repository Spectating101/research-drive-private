import { useMemo, useState } from "react";
import {
  reviewDiscoverIntentProposal,
  selectDiscoverIntentRoute,
  submitDiscoverIntent,
} from "@/v2/api";
import {
  canSubmitDiscoverIntent,
  intentCollection,
  intentState,
  selectedIntentRoute,
} from "@/v2/discoverIntent";

function text(value, fallback = "") {
  return String(value || "").trim() || fallback;
}

function Fact({ label, value, unknown = false }) {
  if (!value) return null;
  return (
    <div>
      <dt>{label}</dt>
      <dd className={unknown ? "is-unknown" : ""}>{value}</dd>
    </div>
  );
}

function RouteCard({ route, selected, recommended = false, disabled, onSelect }) {
  const highlighted = selected || recommended;
  return (
    <article className={`rd-v2-intent-route${highlighted ? " is-selected" : ""}`}>
      <header>
        <div>
          <span className="rd-v2-eyebrow">
            {selected ? "Selected route" : recommended ? "Recommended route" : "Available route"}
          </span>
          <h3>{text(route.title, "Untitled acquisition route")}</h3>
        </div>
        {!selected ? (
          <button type="button" disabled={disabled} onClick={onSelect}>Select route</button>
        ) : null}
      </header>
      {route.summary ? <p>{route.summary}</p> : null}
      <dl>
        <Fact label="Coverage" value={route.coverage} />
        <Fact label="Grain" value={route.grain} />
        <Fact label="Access" value={route.access} />
        <Fact label="Destination" value={route.destination} />
        <Fact label="Refresh" value={route.refresh} />
        <Fact label="Cost" value={route.cost} unknown />
        <Fact label="Limitation" value={route.limitation} unknown />
      </dl>
    </article>
  );
}

export function DiscoverIntentWorkspace({
  record,
  onChange,
  onBack,
  onAsk,
  onSubmitted,
  onOpenHistory,
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const intent = record?.intent || null;
  const state = intentState(intent);
  const candidate = state.candidate || record?.candidate || {};
  const proposal = state.proposal || null;
  const routes = state.routes || [];
  const collection = intentCollection(intent);
  const selectedRoute = selectedIntentRoute(intent);
  const title = text(candidate.title || intent?.title, "Acquisition review");
  const description = text(
    candidate.description,
    "The catalog does not provide a description for this offering.",
  );
  const use = text(candidate.recommended_use);
  const registeredId = text(collection.registered_dataset_id);
  const jobStatus = text(record?.job?.status || intent?.job?.status || collection.status);
  const proposalRoutes = useMemo(() => proposal?.routes || [], [proposal]);

  const review = async (decision) => {
    if (!proposal?.id || !proposal?.proposal_hash || !intent?.id) return;
    setBusy(`review:${decision}`);
    setError("");
    try {
      const next = await reviewDiscoverIntentProposal(intent.id, {
        decision,
        proposalId: proposal.id,
        proposalHash: proposal.proposal_hash,
      });
      onChange?.({ ...record, intent: next });
    } catch (failure) {
      setError(failure?.message || "Could not review this route proposal.");
    } finally {
      setBusy("");
    }
  };

  const selectRoute = async (routeId) => {
    if (!intent?.id) return;
    setBusy(`route:${routeId}`);
    setError("");
    try {
      const next = await selectDiscoverIntentRoute(intent.id, routeId);
      onChange?.({ ...record, intent: next });
    } catch (failure) {
      setError(failure?.message || "Could not select this route.");
    } finally {
      setBusy("");
    }
  };

  const submit = async () => {
    if (!intent?.id || !canSubmitDiscoverIntent(intent)) return;
    setBusy("submit");
    setError("");
    try {
      const out = await submitDiscoverIntent(intent.id, { limit: 200 });
      const nextRecord = {
        ...record,
        intent: out?.intent || intent,
        job: out?.job || null,
      };
      onChange?.(nextRecord);
      onSubmitted?.(out?.job || null, nextRecord);
    } catch (failure) {
      setError(failure?.message || "Could not submit this route for approval.");
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="rd-v2-intent-workspace" data-testid="discover-intent-workspace">
      <header className="rd-v2-intent-workspace-head">
        <button type="button" className="rd-v2-linkish" onClick={onBack}>← Back to results</button>
        <div>
          <span className="rd-v2-eyebrow">Discover acquisition intent</span>
          <h2>{title}</h2>
          <p>{description}</p>
          {use ? <p className="rd-v2-intent-use"><b>How to use it</b> {use}</p> : null}
        </div>
        <div className="rd-v2-intent-identity">
          <span>Intent {text(intent?.id).slice(0, 12)}{intent?.id ? "…" : ""}</span>
          <strong>{text(state.status, "draft").replaceAll("_", " ")}</strong>
        </div>
      </header>

      <section className="rd-v2-intent-need">
        <span className="rd-v2-eyebrow">Research need</span>
        <p>{text(intent?.research_need || record?.researchNeed, "Research need not recorded")}</p>
      </section>

      {error ? <p className="rd-v2-intent-error">{error}</p> : null}

      {proposal ? (
        <section className="rd-v2-intent-proposal" aria-label="Proposed acquisition routes">
          <header>
            <div>
              <span className="rd-v2-eyebrow">Proposed routes · review required</span>
              <h3>{proposal.summary}</h3>
              {proposal.reason ? <p>{proposal.reason}</p> : null}
            </div>
          </header>
          <div className="rd-v2-intent-route-list">
            {proposalRoutes.map((route) => (
              <RouteCard
                key={route.id}
                route={route}
                recommended={route.id === proposal.recommended_route_id}
                disabled
              />
            ))}
          </div>
          <footer>
            <p>Accepting records these routes for review. It does not start collection.</p>
            <button type="button" className="rd-v2-btn primary" disabled={Boolean(busy)} onClick={() => review("accept")}>
              {busy === "review:accept" ? "Accepting…" : "Accept routes for review"}
            </button>
            <button type="button" className="rd-v2-btn" disabled={Boolean(busy)} onClick={() => review("reject")}>
              Reject draft
            </button>
          </footer>
        </section>
      ) : routes.length ? (
        <section className="rd-v2-intent-reviewed" aria-label="Reviewed acquisition routes">
          <header>
            <span className="rd-v2-eyebrow">Reviewed routes</span>
            <h3>Choose the concrete route to submit</h3>
          </header>
          <div className="rd-v2-intent-route-list">
            {routes.map((route) => (
              <RouteCard
                key={route.id}
                route={route}
                selected={route.id === state.selected_route_id}
                disabled={Boolean(busy) || Boolean(collection.job_id)}
                onSelect={() => selectRoute(route.id)}
              />
            ))}
          </div>
          {!collection.job_id ? (
            <div className="rd-v2-intent-submit">
              <div>
                <strong>{selectedRoute?.title || "Select a route"}</strong>
                <span>Submission creates a pending-approval job. It does not approve the collection.</span>
              </div>
              <button
                type="button"
                className="rd-v2-btn primary"
                disabled={Boolean(busy) || !canSubmitDiscoverIntent(intent)}
                onClick={submit}
              >
                {busy === "submit" ? "Submitting…" : "Submit for approval"}
              </button>
            </div>
          ) : null}
        </section>
      ) : (
        <section className="rd-v2-intent-empty">
          <span className="rd-v2-eyebrow">No supported route recorded</span>
          <h3>This intent is durable, but it has no reviewed acquisition route yet.</h3>
          <p>Ask the desk to investigate a connector, public URL, entitlement, or implementation path. No collection can be submitted from this state.</p>
          <button type="button" className="rd-v2-btn" onClick={() => onAsk?.(record)}>
            Ask the desk to investigate →
          </button>
        </section>
      )}

      {collection.job_id ? (
        <section className="rd-v2-intent-collection" data-testid="discover-intent-collection">
          <div>
            <span className="rd-v2-eyebrow">Collection lifecycle</span>
            <h3>{registeredId ? "Registered in Library" : text(jobStatus, "pending approval").replaceAll("_", " ")}</h3>
            <p>
              Job {collection.job_id}
              {registeredId ? ` · registered as ${registeredId}` : " · collection remains governed by History and approval state"}
            </p>
          </div>
          <button type="button" className="rd-v2-btn" onClick={() => onOpenHistory?.(record)}>
            Open in History →
          </button>
        </section>
      ) : null}
    </section>
  );
}
