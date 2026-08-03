import {
  RailDecisionSummary,
  RailEntityHeader,
  RailField,
  RailFieldGrid,
  RailFrame,
} from "@/v2/RailFrame";
import {
  intentCollection,
  intentState,
  selectedIntentRoute,
} from "@/v2/discoverIntent";

function text(value, fallback = "") {
  return String(value || "").trim() || fallback;
}

function routeTitle(route, sourceTitle = "") {
  const raw = text(route?.title);
  return /^collect through [a-z0-9_-]+$/i.test(raw) && sourceTitle
    ? `Collect from ${sourceTitle}`
    : raw;
}

function statusLabel(state, collection) {
  if (collection.registered_dataset_id) return "Registered in Library";
  if (collection.job_id) return text(collection.status, "Pending approval").replaceAll("_", " ");
  if (state.proposal) return "Proposal ready";
  if (state.routes?.length) return "Routes reviewed";
  return "Route investigation needed";
}

export function DiscoverIntentRailPanel({ record }) {
  const intent = record?.intent || {};
  const state = intentState(intent);
  const collection = intentCollection(intent);
  const route = selectedIntentRoute(intent);
  const label = statusLabel(state, collection);
  const next = collection.registered_dataset_id
    ? "Open the resulting asset in Library."
    : collection.job_id
      ? "Track approval, collection, and registration in History."
      : state.proposal
        ? "Continue to route selection or reject the proposal in the review canvas."
        : state.routes?.length
          ? "Select a route and submit it for approval."
          : "Ask the desk to investigate a supported route.";
  const boundary = collection.job_id
    ? "Discover preserves the decision; History owns execution."
    : "No collection starts until a reviewed route is submitted and approved.";
  const sourceTitle = text(state.candidate?.title || intent.title);
  const selectedRouteLabel = routeTitle(route, sourceTitle)
    || (state.proposal ? "Choose after reviewing the proposal" : "Not selected");

  return (
    <RailFrame>
      <RailEntityHeader
        title={text(intent.title || state.candidate?.title, "Acquisition review")}
        pills={<span className="rd-v2-pill warn">{label}</span>}
        description="Durable Discover decision record"
      />
      <RailDecisionSummary
        primary={collection.job_id ? "Execution moved to History" : "Collection has not started"}
        risk={boundary}
        next={next}
        labels={{
          primary: "Collection",
          risk: "Boundary",
          next: "Next",
        }}
      />
      <div className="rd-v2-rail-scroll">
        <section className="rd-v2-library-inspector-block" aria-label="Decision memory">
          <p className="rd-v2-rail-section-label">Decision memory</p>
          <RailFieldGrid>
            <RailField label="Research need" value={intent.research_need || record?.researchNeed} />
            <RailField label="Offering" value={state.candidate?.title || intent.title} />
            <RailField label="Selected route" value={selectedRouteLabel} />
            {collection.job_id ? <RailField label="Job" value={collection.job_id} mono /> : null}
            {collection.registered_dataset_id ? (
              <RailField label="Library asset" value={collection.registered_dataset_id} mono />
            ) : null}
          </RailFieldGrid>
        </section>
        <section className="rd-v2-library-inspector-block" aria-label="Workflow boundary">
          <p className="rd-v2-rail-section-label">Workflow boundary</p>
          <p className="rd-v2-library-inspector-prose">
            Discover compares and records the route. History governs approval and execution.
            Library owns the verified registered output.
          </p>
        </section>
        <details className="rd-v2-rail-technical">
          <summary>Technical details</summary>
          <RailFieldGrid>
            <RailField label="Intent ID" value={intent.id} mono />
            <RailField label="Candidate key" value={state.candidate?.candidate_key} mono />
            {route?.connector_id ? <RailField label="Connector" value={route.connector_id} mono /> : null}
          </RailFieldGrid>
        </details>
      </div>
    </RailFrame>
  );
}
