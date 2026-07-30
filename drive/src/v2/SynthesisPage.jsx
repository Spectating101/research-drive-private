import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageShell } from "@/v2/ui";
import {
  createSynthesisThread,
  decideSynthesisProposal,
  getSynthesisThread,
  listSynthesisProfiles,
  listSynthesisThreads,
  requestSynthesisExecution,
} from "@/v2/api";
import { handleEnterToSubmit } from "@/v2/enterToSubmit";
import { buildStageDetail, executionTrack } from "@/v2/synthesisLifecycle";

function text(value, fallback = "") {
  return String(value || "").trim() || fallback;
}

function titleFor(thread) {
  return text(thread?.title || thread?.state?.title, "Untitled synthesis");
}

function stateFor(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const lifecycle = text(execution.status || thread?.materialisation).toLowerCase().replace(/-/g, "_");
  if (lifecycle === "query_ready") return "query_ready";
  if (lifecycle === "registered") return "registered";
  if (lifecycle === "failed") return "failed";
  if (execution.status) return "execution";
  if (state.proposal) return "proposal";
  if ((state.nodes || []).length) return "explore";
  return "draft";
}

function stageLabel(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const mode = stateFor(thread);
  if (mode === "query_ready") return "Query-ready output";
  if (mode === "registered") return "Registered output";
  if (mode === "failed") return "Execution failed";
  if (mode === "execution") return text(execution.status).replace(/_/g, " ");
  if (mode === "proposal") return "Proposal needs review";
  return text(state.maturityLabel || state.maturity, mode === "draft" ? "New thread" : "Evidence mapping");
}

function evidenceNodes(thread) {
  return (thread?.state?.nodes || []).filter(
    (node) => node?.layer === "evidence" || node?.type === "source" || node?.type === "construct",
  );
}

function targetNode(thread) {
  return (thread?.state?.nodes || []).find((node) => node?.layer === "target" || node?.type === "target");
}

function threadStatus(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const mode = stateFor(thread);
  if (mode === "query_ready") return "Query ready";
  if (mode === "registered") return "Registered";
  if (mode === "failed") return "Needs recovery";
  if (execution.status) return text(execution.status).replace(/_/g, " ");
  if (state.proposal) return "Review proposal";
  return text(state.maturityLabel || state.maturity, "Exploring");
}

function threadOutput(thread) {
  const state = thread?.state || {};
  return state.execution?.output_dataset_id || state.execution_spec?.output_dataset_id || "";
}

const SYNTHESIS_STAGES = [
  ["Define", "Research object"],
  ["Ground", "Library evidence"],
  ["Review", "Method decision"],
  ["Build", "Execution record"],
  ["Reuse", "Library asset"],
];

function synthesisStageIndex(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const mode = stateFor(thread);
  if (mode === "registered" || mode === "query_ready") return 4;
  if (execution.status || state.execution_spec) return 3;
  if (state.proposal) return 2;
  if ((state.nodes || []).length) return 1;
  return 0;
}

function SynthesisProgress({ thread }) {
  const active = synthesisStageIndex(thread);
  const buildDetail = buildStageDetail(thread);
  return (
    <ol className="s04-steps" aria-label="Synthesis project stages">
      {SYNTHESIS_STAGES.map(([label, detail], index) => (
        <li key={label} className={index < active ? "done" : index === active ? "now" : ""}>
          <span>{index < active ? "✓" : index + 1}</span>
          <b>{label}</b>
          <small>{label === "Build" ? buildDetail : detail}</small>
        </li>
      ))}
    </ol>
  );
}

function ThreadList({ threads, selectedId, loading, onSelect, onNew }) {
  const selectedRef = useRef(null);
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <aside className="s04-threads" aria-label="Synthesis threads">
      <header>
        <div>
          <span>Research construction</span>
          <small>{loading ? "Loading" : `${threads.length} threads`}</small>
        </div>
        <button type="button" className="s04-thread-new" onClick={onNew}>+ New</button>
      </header>
      {threads.map((thread) => (
        <button
          type="button"
          key={thread.id}
          ref={thread.id === selectedId ? selectedRef : null}
          className={thread.id === selectedId ? "active" : ""}
          onClick={() => onSelect(thread.id)}
          data-testid="synthesis-thread-item"
        >
          <b>{["registered", "query_ready"].includes(stateFor(thread)) ? "✓" : stateFor(thread) === "failed" ? "!" : "S"}</b>
          <span>
            <strong>{titleFor(thread)}</strong>
            <small>{threadStatus(thread)}</small>
          </span>
        </button>
      ))}
      {!loading && !threads.length ? <p className="s04-thread-empty">No Synthesis threads yet.</p> : null}
      <footer>
        <small>Thread memory</small>
        <p>Methods, review decisions, execution state, and registered outputs stay attached to the research object.</p>
      </footer>
    </aside>
  );
}

function ThreadHeader({ thread }) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const mode = stateFor(thread);
  const queryReady = mode === "query_ready";
  const registered = mode === "registered" || queryReady;
  return (
    <>
      <header className="s04-head">
        <div>
          <small>{stageLabel(thread)}</small>
          <h1>{titleFor(thread)}</h1>
          <p>{text(thread?.objective || state.objective, "A durable research-construction thread.")}</p>
        </div>
        <em>
          {queryReady
            ? "Query-ready evidence"
            : registered
              ? "Registered evidence"
              : execution.status
              ? "Durable execution state"
              : state.proposal
                ? "Reviewable change"
                : "Nothing registered"}
        </em>
      </header>
      <div className="s04-brief">
        <span>
          <small>Current record</small>
          {text(state.lastActivity, "No method or output claim has been recorded yet.")}
        </span>
        <span className="s04-brief-grain">
          <small>Required grain</small>
          {text(state.required_grain || state.spec?.grain, "Not specified")}
        </span>
      </div>
      <SynthesisProgress thread={thread} />
    </>
  );
}

function EvidenceMap({ thread, onAsk }) {
  const target = targetNode(thread);
  const evidence = evidenceNodes(thread);
  const state = thread?.state || {};
  const missing = evidence.filter((node) => /missing|needs_access|sourceable/i.test(String(node.status || "")));
  return (
    <section className="s04-card" data-testid="synthesis-evidence-state">
      <header className="s04-title">
        <div>
          <small>Evidence map</small>
          <h2>{text(target?.label, "Research construction")}</h2>
        </div>
        <em className="neutral">{evidence.length ? `${evidence.length} mapped inputs` : "No inputs mapped"}</em>
      </header>
      <div className="s04-map" role="img" aria-label="The current Synthesis evidence map">
        <div className="sources">
          {evidence.length ? (
            evidence.slice(0, 6).map((node) => (
              <article key={node.id || node.label}>
                <small>{text(node.role || node.eyebrow || node.status, "Evidence")}</small>
                <strong>{text(node.label || node.dataset_id, "Unnamed evidence")}</strong>
                <span>{[node.grain, node.coverage].filter(Boolean).join(" · ") || "Metadata not reported"}</span>
              </article>
            ))
          ) : (
            <article className="s04-empty-evidence">
              <small>Next</small>
              <strong>Map evidence with Ask</strong>
              <span>No source relationship has been persisted.</span>
            </article>
          )}
        </div>
        <b>↓</b>
        {state.spec?.summary || state.spec?.method ? (
          <>
            <span className="process">{text(state.spec.summary || state.spec.method, "Method detail not reported")}</span>
            <b>↓</b>
          </>
        ) : null}
        <strong className="target">{text(target?.label, text(thread?.objective, "Research objective"))}</strong>
      </div>
      <div className="s04-pairs">
        <article>
          <small>Research object</small>
          <strong>{text(thread?.objective || state.objective, "Not reported")}</strong>
          <p>{text(target?.interpretation, "Ask can refine the object before a method proposal is accepted.")}</p>
        </article>
        <article>
          <small>Unresolved evidence</small>
          <strong>{missing.length ? `${missing.length} source decision${missing.length === 1 ? "" : "s"} remain` : "No missing source is recorded"}</strong>
          <p>{missing.length ? missing.map((node) => node.label || node.dataset_id).filter(Boolean).join(" · ") : "This is not a claim of complete coverage."}</p>
        </article>
      </div>
      <footer className="s04-actions">
        <p>
          <small>Next</small>
          Ask proposes reviewable changes. It cannot silently accept a method or register an output.
        </p>
        <button type="button" className="rd-v2-btn primary" onClick={() => onAsk("Explain the current evidence map and identify the next material research decision.")}>
          Discuss construction in Ask
        </button>
      </footer>
    </section>
  );
}

function metricLabel(metric) {
  const fn = text(metric?.function || metric?.aggregate, "metric");
  const column = text(metric?.column || metric?.field);
  const alias = text(metric?.as || metric?.name);
  const expression = column ? `${fn}(${column})` : fn;
  return alias && alias !== expression ? `${alias} ← ${expression}` : expression;
}

function softIdentifier(value, fallback = "Not reported") {
  return text(value, fallback).replace(/([_/.-])/g, "$1\u200b");
}

function ProposalReview({ thread, busy, onDecide, onAsk }) {
  const state = thread?.state || {};
  const proposal = state.proposal || {};
  const spec = proposal.execution_spec || {};
  const operations = Array.isArray(proposal.operations) ? proposal.operations : [];
  const metrics = Array.isArray(spec.metrics) ? spec.metrics : [];
  const groupBy = Array.isArray(spec.group_by) ? spec.group_by : [];
  const limitations = (
    Array.isArray(state.spec?.limitations)
      ? state.spec.limitations
      : Array.isArray(state.limitations)
        ? state.limitations
        : []
  ).filter(Boolean);
  const unknowns = (
    Array.isArray(state.spec?.unavailable)
      ? state.spec.unavailable
      : Array.isArray(state.unavailable)
        ? state.unavailable
        : []
  ).filter(Boolean);
  const canDecide = Boolean(proposal.id && proposal.proposal_hash);
  return (
    <section className="s04-card s04-proposal-card" data-testid="synthesis-proposal-state">
      <header className="s04-title">
        <div>
          <small>Review proposed change</small>
          <h2>{text(proposal.title, "Untitled proposal")}</h2>
        </div>
        <em className={proposal.execution_preflight?.ok ? "success" : "warn"}>
          {proposal.execution_preflight?.ok ? "Preflight passed · review required" : "Review required"}
        </em>
      </header>
      <p className="s04-proposal-summary">
        {text(proposal.summary, "The agent proposed a change to this durable construction.")}
      </p>
      {proposal.execution_spec ? (
        <div className="s04-method-flow" aria-label="Proposed construction pipeline">
          <article>
            <small>Held input</small>
            <strong>{softIdentifier(spec.input_dataset_id)}</strong>
            <span>Registered Library evidence</span>
          </article>
          <b aria-hidden="true">→</b>
          <article className="transform">
            <small>Construction</small>
            <strong>{groupBy.length ? `Group by ${groupBy.join(" + ")}` : "Aggregate all rows"}</strong>
            <div>
              {metrics.length
                ? metrics.slice(0, 5).map((metric, index) => <span key={`${metricLabel(metric)}-${index}`}>{metricLabel(metric)}</span>)
                : <span>Metric detail not reported</span>}
            </div>
          </article>
          <b aria-hidden="true">→</b>
          <article className="output">
            <small>Proposed output</small>
            <strong>{softIdentifier(spec.output_dataset_id)}</strong>
            <span>Nothing is materialised yet</span>
          </article>
        </div>
      ) : null}
      <div className="s04-review-grid">
        <section className="s04-resolved-list">
          <small>Exact change set</small>
          <ul>
            {operations.length ? (
              operations.slice(0, 8).map((operation, index) => (
                <li key={`${operation.op || operation.type || "change"}-${index}`}>
                  {text(operation.summary || operation.label || operation.path || operation.op || operation.type, "Structured state change")}
                </li>
              ))
            ) : (
              <li>No operation summary was returned. Inspect this proposal with Ask before deciding.</li>
            )}
          </ul>
        </section>
        <section className="s04-review-risks">
          <small>Still not established</small>
          {limitations.length || unknowns.length ? (
            <ul>
              {[...limitations, ...unknowns].slice(0, 5).map((item, index) => (
                <li key={`${text(item)}-${index}`}>{text(item)}</li>
              ))}
            </ul>
          ) : (
            <p>No additional limitation was recorded. Ask should still challenge construct validity before acceptance.</p>
          )}
        </section>
      </div>
      {!canDecide ? <p className="s04-fixture">This proposal has no revision hash, so it cannot be accepted from the desk. Refresh it through Ask.</p> : null}
      <footer className="s04-actions">
        <p>
          <small>Approval boundary</small>
          A decision is bound to this exact proposal revision. A changed proposal must be reviewed again.
        </p>
        <button type="button" className="rd-v2-btn" onClick={() => onAsk("Challenge this Synthesis proposal and explain every methodological consequence.")}>Challenge in Ask</button>
        <button type="button" className="rd-v2-btn" disabled={busy || !canDecide} onClick={() => onDecide("reject")}>Reject</button>
        <button type="button" className="rd-v2-btn primary" disabled={busy || !canDecide} onClick={() => onDecide("accept")}>Accept proposal</button>
      </footer>
    </section>
  );
}

function ExecutionRecord({ thread, busy, onRequest, onReview, onAsk, onOpenDataset }) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const spec = state.execution_spec || {};
  const rawStatus = text(execution.status).toLowerCase().replace(/-/g, "_");
  const status = text(execution.status, "not requested").replace(/_/g, " ");
  const outputId = threadOutput(thread);
  const mode = stateFor(thread);
  const queryReady = mode === "query_ready";
  const registered = mode === "registered" || queryReady;
  const failed = execution.status === "failed";
  const pendingApproval = rawStatus === "pending_approval";
  const active = ["queued", "running", "registering", "archiving"].includes(rawStatus);
  const hasSpec = Boolean(spec.input_dataset_id && spec.output_dataset_id);
  const track = executionTrack(rawStatus, registered, queryReady);

  return (
    <section className="s04-card" data-testid={queryReady ? "synthesis-query-ready-state" : registered ? "synthesis-registered-state" : failed ? "synthesis-failed-state" : "synthesis-execution-state"}>
      <header className="s04-title">
        <div>
          <small>{queryReady ? "Query-ready research asset" : registered ? "Registered research asset" : failed ? "Execution failed" : "Execution record"}</small>
          <h2>{registered ? softIdentifier(outputId, "Registered output") : softIdentifier(spec.output_dataset_id, "No execution requested")}</h2>
        </div>
        <em className={registered ? "success" : failed ? "warn" : "neutral"}>{queryReady ? "Query ready" : registered ? "Registered" : status}</em>
      </header>
      {hasSpec ? (
        <dl className="s04-method">
          <div><dt>Input</dt><dd>{softIdentifier(spec.input_dataset_id)}</dd></div>
          <div><dt>Output</dt><dd>{softIdentifier(spec.output_dataset_id)}</dd></div>
          <div><dt>Group by</dt><dd>{Array.isArray(spec.group_by) ? spec.group_by.join(" · ") : "Not reported"}</dd></div>
          <div><dt>Metrics</dt><dd>{Array.isArray(spec.metrics) ? `${spec.metrics.length} defined` : "Not reported"}</dd></div>
        </dl>
      ) : null}
      {hasSpec ? (
        <ol className="s04-exec-track" aria-label="Synthesis execution lifecycle">
          {track.map((step, index) => (
            <li key={step.label} className={step.state}>
              <b>{step.state === "done" ? "✓" : index + 1}</b>
              <span>
                <strong>{step.label}</strong>
                <small>{step.detail}</small>
              </span>
            </li>
          ))}
        </ol>
      ) : null}
      <div className="s04-proof">
        <section>
          <small>Execution evidence</small>
          <dl>
            <div><dt>Job</dt><dd>{text(execution.job_id, "Not requested")}</dd></div>
            <div><dt>Rows</dt><dd>{execution.rows == null ? "Not reported" : Number(execution.rows).toLocaleString()}</dd></div>
            <div><dt>Manifest</dt><dd>{text(execution.manifest_id, "Not reported")}</dd></div>
          </dl>
        </section>
        <section>
          <small>Registration evidence</small>
          <dl>
            <div><dt>Archive</dt><dd>{execution.drive_verified ? "Reported verified" : "Not reported"}</dd></div>
            <div><dt>Registry</dt><dd>{queryReady ? "Query-ready output reported" : registered ? "Registered output reported" : "Not claimed"}</dd></div>
            <div><dt>Output</dt><dd>{softIdentifier(outputId, "Not registered")}</dd></div>
          </dl>
        </section>
      </div>
      {failed ? <p className="s04-fixture">{text(execution.error, "The execution failed without a recorded error detail.")}</p> : null}
      <footer className="s04-actions">
        <p>
          <small>Truth boundary</small>
          {queryReady
            ? "This asset is shown because the thread reports a query-ready output."
            : registered
              ? "This asset is shown because the thread reports a registered output; query readiness is not implied."
              : failed
              ? "The accepted specification remains inspectable; no output is claimed registered."
              : hasSpec
                ? "Requesting execution creates a durable job. Registration remains a separate verified outcome."
                : "An accepted execution specification is required before this thread can request a build."}
        </p>
        {registered ? (
          <button
            type="button"
            className="rd-v2-btn primary"
            onClick={() => onOpenDataset?.({
              dataset_id: outputId,
              name: outputId,
              analysis_readiness: queryReady ? "query_ready" : "registered",
            })}
          >
            Open in Library
          </button>
        ) : null}
        {!registered && hasSpec && !rawStatus ? <button type="button" className="rd-v2-btn primary" disabled={busy} onClick={onRequest}>Request execution</button> : null}
        {pendingApproval ? <button type="button" className="rd-v2-btn primary" onClick={() => onReview?.(execution)}>Review approval</button> : null}
        {active ? <span className="s04-live-note">This thread refreshes automatically.</span> : null}
        <button type="button" className="rd-v2-btn" onClick={() => onAsk("Explain the exact execution state and which evidence is still missing before this output can be trusted.")}>Ask about execution</button>
      </footer>
    </section>
  );
}

function DraftCanvas({ thread, onAsk }) {
  const state = thread?.state || {};
  return (
    <section className="s04-card s04-draft" data-testid="synthesis-draft-state">
      <header className="s04-title">
        <div>
          <small>AI construction workspace</small>
          <h2>Interpretation in progress</h2>
        </div>
        <em className="neutral">Grounding Library evidence</em>
      </header>
      <div className="s04-draft-flow" role="img" aria-label="The first Synthesis reasoning steps">
        <strong>{text(thread?.objective || state.objective, "Research objective")}</strong>
        <b>↓</b>
        <div>
          <article>
            <small>1 · Interpret</small>
            <span>Define the latent construct</span>
          </article>
          <article>
            <small>2 · Ground</small>
            <span>Map relevant Library evidence</span>
          </article>
          <article>
            <small>3 · Challenge</small>
            <span>Name the decisive validity risk</span>
          </article>
        </div>
      </div>
      <footer className="s04-actions">
        <p>
          <small>Working agreement</small>
          Ask clarifies the construct one decision at a time. Nothing is executed or registered from this state.
        </p>
        <button
          type="button"
          className="rd-v2-btn primary"
          onClick={() => onAsk("Continue interpreting this construct. Show what is supported, proposed, and unresolved, then ask the one highest-value question.")}
        >
          Continue in Ask
        </button>
      </footer>
    </section>
  );
}

function NewThread({ objective, setObjective, busy, profiles, onCreate, onStartBlueprint }) {
  const startingPoints = (Array.isArray(profiles) ? profiles : []).slice(0, 3);
  return (
    <section className="s04-intent" data-testid="synthesis-intent-state">
      <small>New Synthesis project</small>
      <h2>Describe the dataset you wish existed.</h2>
      <p>Give the research purpose in ordinary language. Ask will clarify the construct, ground it in your Library, and expose every proxy choice before a method can be reviewed.</p>
      <textarea
        rows={7}
        value={objective}
        onChange={(event) => setObjective(event.target.value)}
        placeholder="Example: Build a weekly measure of stablecoin trust deterioration that separates security incidents, liquidity stress, and public attention…"
        onKeyDown={(event) => {
          handleEnterToSubmit(event, () => {
            if (!busy && objective.trim()) onCreate();
          });
        }}
      />
      <div className="s04-intent-contract" aria-label="What Synthesis does next">
        <span><b>1</b> Interpret</span>
        <span><b>2</b> Ground in Library</span>
        <span><b>3</b> Challenge proxies</span>
        <span><b>4</b> Review method</span>
      </div>
      {startingPoints.length ? (
        <div className="s04-intent-starts">
          <small>Or start from a registered method</small>
          <div>
            {startingPoints.map((profile) => (
              <button
                type="button"
                key={profile.id}
                disabled={busy}
                onClick={() => onStartBlueprint?.(profile)}
                title={text(profile.title, profile.id)}
              >
                <strong>{text(profile.title, profile.id)}</strong>
                <span>{text(profile.description, "Registered construction recipe")}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <footer>
        {/* VC-6: a disabled primary action must say why it is unavailable. */}
        <span>
          {objective.trim()
            ? "Creates a durable project, then opens Ask with this exact objective attached."
            : "Enter an objective to continue. Creates a durable project, then opens Ask with it attached."}
        </span>
        <button
          type="button"
          className="rd-v2-btn primary"
          disabled={busy || !objective.trim()}
          onClick={onCreate}
          title={objective.trim() ? undefined : "Enter an objective to continue"}
        >
          Start project in Ask
        </button>
      </footer>
    </section>
  );
}

function EmptyWorkspace({ profiles, profilesLoading, profilesError, onStartBlueprint, onNew }) {
  const list = Array.isArray(profiles) ? profiles : [];
  return (
    <section className="s04-intent s04-intent-quiet s04-exploration-ready" data-testid="synthesis-empty-state">
      <small>Exploration ready</small>
      <h2>Choose a blueprint or start a custom construction</h2>
      <p>
        Synthesis is blueprint/recipe oriented: owned Library inputs → defined method → verified output.
        Blueprints below come from the lab registry — not invented UI copy.
      </p>
      {profilesLoading ? <p className="s04-fixture">Loading registered blueprints…</p> : null}
      {profilesError ? <p className="s04-fixture">{profilesError}</p> : null}
      {!profilesLoading && !profilesError && !list.length ? (
        <p className="s04-fixture">No synthesis blueprints are registered on this desk yet.</p>
      ) : null}
      {list.length ? (
        <ul className="s04-blueprint-recipes" aria-label="Registered synthesis blueprints" data-testid="synthesis-blueprints">
          {list.map((profile) => {
            const sources = Array.isArray(profile.sources) ? profile.sources : [];
            const joins = Array.isArray(profile.join_keys) ? profile.join_keys : [];
            const body =
              text(profile.description) ||
              (sources.length
                ? `Inputs: ${sources.map((s) => s.label || s.id).filter(Boolean).join(" · ")}`
                : "Registered construction recipe");
            return (
              <li key={profile.id}>
                <button
                  type="button"
                  className="s04-blueprint-recipe"
                  data-testid="synthesis-blueprint"
                  onClick={() => onStartBlueprint?.(profile)}
                >
                  <strong>{text(profile.title, profile.id)}</strong>
                  <span>
                    {body}
                    {joins.length ? ` · join ${joins.join(", ")}` : ""}
                  </span>
                  <em>Start →</em>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      <footer>
        <button type="button" className="rd-v2-btn" onClick={onNew}>
          Custom objective…
        </button>
      </footer>
    </section>
  );
}

export function SynthesisPage({ onAskComposer, onOpenDataset, onReviewExecution, onSelectThread, onBeginNew }) {
  const [threads, setThreads] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesError, setProfilesError] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [newMode, setNewMode] = useState(false);
  const [objective, setObjective] = useState("");
  const notified = useRef("");

  const replaceThread = useCallback((next) => {
    if (!next?.id) return;
    setThreads((current) => {
      const present = current.some((thread) => thread.id === next.id);
      return present ? current.map((thread) => (thread.id === next.id ? next : thread)) : [next, ...current];
    });
  }, []);

  const refreshThreads = useCallback(async ({ keepLoading = false } = {}) => {
    if (!keepLoading) setLoading(true);
    setError("");
    try {
      const result = await listSynthesisThreads();
      const next = Array.isArray(result?.threads) ? result.threads : [];
      setThreads(next);
      setSelectedId((current) => {
        if (current && next.some((thread) => thread.id === current)) return current;
        const familiar = next.find((thread) => /stablecoin attention/i.test(titleFor(thread)));
        return familiar?.id || next[0]?.id || "";
      });
      if (!next.length) setNewMode(true);
    } catch (cause) {
      setError(text(cause?.message, "Synthesis threads could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshThreads();
  }, [refreshThreads]);

  useEffect(() => {
    let cancelled = false;
    setProfilesLoading(true);
    setProfilesError("");
    listSynthesisProfiles()
      .then((result) => {
        if (cancelled) return;
        const next = Array.isArray(result?.profiles) ? result.profiles : [];
        setProfiles(next);
      })
      .catch((cause) => {
        if (cancelled) return;
        setProfiles([]);
        setProfilesError(text(cause?.message, "Registered blueprints could not be loaded."));
      })
      .finally(() => {
        if (!cancelled) setProfilesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(() => threads.find((thread) => thread.id === selectedId) || null, [threads, selectedId]);

  useEffect(() => {
    if (!selected) return;
    const key = `${selected.id}:${selected.updated_at || ""}:${selected.state?.execution?.status || ""}`;
    if (notified.current === key) return;
    notified.current = key;
    onSelectThread?.(selected);
  }, [selected, onSelectThread]);

  const refreshThread = useCallback(async (threadId = selectedId) => {
    if (!threadId) return null;
    const next = await getSynthesisThread(threadId);
    replaceThread(next);
    return next;
  }, [replaceThread, selectedId]);

  useEffect(() => {
    const execution = selected?.state?.execution || {};
    if (!selected || !/pending_approval|queued|running|registering|archiving/i.test(String(execution.status || ""))) return undefined;
    const timer = window.setInterval(() => {
      refreshThread().catch(() => {});
    }, 4000);
    return () => window.clearInterval(timer);
  }, [selected, refreshThread]);

  const selectThread = async (threadId) => {
    setSelectedId(threadId);
    setNewMode(false);
    setError("");
    try {
      const next = await refreshThread(threadId);
      if (next) onSelectThread?.(next);
    } catch (cause) {
      setError(text(cause?.message, "This Synthesis thread could not be refreshed."));
    }
  };

  const ask = (prompt, thread = selected) => {
    const context = thread
      ? `\n\nSynthesis thread: ${titleFor(thread)}\nObjective: ${text(thread.objective || thread.state?.objective)}\nDurable status: ${stageLabel(thread)}.`
      : "\n\nSynthesis workspace context.";
    onAskComposer?.({ prompt: `${text(prompt)}${context}`, displayText: text(prompt, "Discuss this synthesis") });
  };

  const beginNew = () => {
    setSelectedId("");
    setNewMode(true);
    setObjective("");
    setError("");
    onSelectThread?.(null);
    onBeginNew?.();
  };

  const createThread = async () => {
    const nextObjective = objective.trim();
    if (!nextObjective) return;
    setBusy(true);
    setError("");
    try {
      const created = await createSynthesisThread({ objective: nextObjective });
      replaceThread(created);
      setSelectedId(created.id);
      setNewMode(false);
      setObjective("");
      onSelectThread?.(created);
      ask(
        `Interpret this research objective. Separate supported evidence, proposed proxy choices, and unresolved limitations, then ask the one highest-value clarification question: ${nextObjective}`,
        created,
      );
    } catch (cause) {
      setError(text(cause?.message, "The Synthesis thread could not be created."));
    } finally {
      setBusy(false);
    }
  };

  const startBlueprint = async (profile) => {
    if (!profile?.id) return;
    const title = text(profile.title, profile.id);
    const sources = Array.isArray(profile.sources)
      ? profile.sources.map((s) => s.label || s.id).filter(Boolean).join("; ")
      : "";
    const questions = Array.isArray(profile.research_questions) ? profile.research_questions.filter(Boolean) : [];
    const objectiveText = [
      `Blueprint: ${title}`,
      text(profile.description),
      sources ? `Registered inputs: ${sources}` : "",
      questions[0] ? `Lead question: ${questions[0]}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    setBusy(true);
    setError("");
    try {
      const created = await createSynthesisThread({
        objective: objectiveText,
        title,
        requiredGrain: Array.isArray(profile.join_keys) ? profile.join_keys.join(", ") : "",
      });
      replaceThread(created);
      setSelectedId(created.id);
      setNewMode(false);
      setObjective("");
      onSelectThread?.(created);
      ask(
        `Use registered blueprint ${profile.id} (${title}). Propose the smallest defensible construction from owned Library inputs. Do not invent missing sources.`,
        created,
      );
    } catch (cause) {
      setError(text(cause?.message, "Could not start this blueprint as a Synthesis thread."));
    } finally {
      setBusy(false);
    }
  };

  const decideProposal = async (decision) => {
    const proposal = selected?.state?.proposal;
    if (!selected || !proposal?.id || !proposal?.proposal_hash) return;
    setBusy(true);
    setError("");
    try {
      const next = await decideSynthesisProposal(selected.id, {
        decision,
        proposalId: proposal.id,
        proposalHash: proposal.proposal_hash,
      });
      replaceThread(next);
      onSelectThread?.(next);
    } catch (cause) {
      setError(text(cause?.message, "The proposal changed before this decision could be saved."));
      refreshThread().catch(() => {});
    } finally {
      setBusy(false);
    }
  };

  const requestExecution = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const result = await requestSynthesisExecution(selected.id);
      const next = result?.thread || (result?.state ? result : await refreshThread(selected.id));
      if (next) {
        replaceThread(next);
        onSelectThread?.(next);
      }
    } catch (cause) {
      setError(text(cause?.message, "The execution request could not be created."));
      refreshThread().catch(() => {});
    } finally {
      setBusy(false);
    }
  };

  const mode = stateFor(selected);
  const showExecution = Boolean(selected && (mode === "execution" || mode === "registered" || mode === "failed" || selected.state?.execution_spec));

  return (
    <PageShell className="rd-v2-synthesis-page" title="Synthesis" lead="Reason from Library evidence to a reviewable research construct, then preserve the method and its proof.">
      <div className="s04-shell" data-testid="synthesis-studio">
        <ThreadList
          threads={threads}
          selectedId={selectedId}
          loading={loading}
          onSelect={selectThread}
          onNew={beginNew}
        />
        <main className="s04-main">
          {error ? <p className="s04-fixture" role="alert">{error}</p> : null}
          {newMode ? (
            <NewThread
              objective={objective}
              setObjective={setObjective}
              busy={busy}
              profiles={profiles}
              onCreate={createThread}
              onStartBlueprint={startBlueprint}
            />
          ) : null}
          {!newMode && !loading && !selected ? (
            <EmptyWorkspace
              profiles={profiles}
              profilesLoading={profilesLoading}
              profilesError={profilesError}
              onStartBlueprint={startBlueprint}
              onNew={beginNew}
            />
          ) : null}
          {!newMode && selected ? (
            <>
              <ThreadHeader thread={selected} />
              {mode === "proposal" ? <ProposalReview thread={selected} busy={busy} onDecide={decideProposal} onAsk={ask} /> : null}
              {showExecution ? (
                <ExecutionRecord
                  thread={selected}
                  busy={busy}
                  onRequest={requestExecution}
                  onReview={onReviewExecution}
                  onAsk={ask}
                  onOpenDataset={onOpenDataset}
                />
              ) : null}
              {mode === "explore" ? <EvidenceMap thread={selected} onAsk={ask} /> : null}
              {mode === "draft" ? <DraftCanvas thread={selected} onAsk={ask} /> : null}
            </>
          ) : null}
        </main>
      </div>
    </PageShell>
  );
}
