import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageShell } from "@/v2/ui";
import {
  createSynthesisThread,
  decideSynthesisProposal,
  getSynthesisDiscoverHandoff,
  getSynthesisThread,
  listSynthesisProfiles,
  listSynthesisThreads,
  requestSynthesisExecution,
} from "@/v2/api";
import {
  executionPrimaryAction,
  stateFor,
  text,
  threadCreatedCardModel,
  titleFor,
} from "@/v2/synthesisWorkspace";

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

function isEvidenceGap(node) {
  return /missing|needs_access|sourceable/i.test(String(node?.status || ""));
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
    </>
  );
}

function EvidenceMap({ thread, selectedField, onAsk, onRouteToDiscover, onSelectField }) {
  const target = targetNode(thread);
  const evidence = evidenceNodes(thread);
  const state = thread?.state || {};
  const missing = evidence.filter(isEvidenceGap);
  return (
    <section className="s04-card" data-testid="synthesis-evidence-state">
      <header className="s04-title">
        <div>
          <small>Evidence map</small>
          <h2>{text(target?.label, "Research construction")}</h2>
        </div>
        <em className="neutral">{evidence.length ? `${evidence.length} mapped inputs` : "No inputs mapped"}</em>
      </header>
      <div className="s04-map" role="group" aria-label="The current Synthesis evidence map">
        <strong className="target">{text(target?.label, text(thread?.objective, "Research objective"))}</strong>
        <b>↓</b>
        <div className="sources">
          {evidence.length ? (
            evidence.slice(0, 6).map((node) => (
              <button
                type="button"
                key={node.id || node.label}
                className={`s04-map-node${selectedField?.id === node.id ? " selected" : ""}`}
                onClick={() => onSelectField(node)}
                aria-pressed={selectedField?.id === node.id}
              >
                <small>{text(node.role || node.eyebrow || node.status, "Evidence")}</small>
                <strong>{text(node.label || node.dataset_id, "Unnamed evidence")}</strong>
                <span>{[node.grain, node.coverage].filter(Boolean).join(" · ") || "Metadata not reported"}</span>
              </button>
            ))
          ) : (
            <article className="s04-empty-evidence">
              <small>Next</small>
              <strong>Map evidence with Ask</strong>
              <span>No source relationship has been persisted.</span>
            </article>
          )}
        </div>
        {state.spec?.summary || state.spec?.method ? (
          <>
            <b>↓</b>
            <span className="process">{text(state.spec.summary || state.spec.method, "Method detail not reported")}</span>
          </>
        ) : null}
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
      {selectedField ? (
        <section className="s04-selected-field" data-testid="synthesis-selected-field">
          <div>
            <small>Selected evidence</small>
            <strong>{text(selectedField.label || selectedField.dataset_id, "Unnamed evidence")}</strong>
            <p>{text(selectedField.interpretation || selectedField.status, "No evidence interpretation has been recorded.")}</p>
          </div>
          <div>
            <button
              type="button"
              className="rd-v2-btn"
              onClick={() => onAsk(`Inspect ${text(selectedField.label || selectedField.dataset_id)} in this construction. State what it establishes, what remains unknown, and the valid next method decision.`)}
            >
              Inspect in Composer
            </button>
            {isEvidenceGap(selectedField) ? (
              <button type="button" className="rd-v2-btn primary" onClick={() => onRouteToDiscover(selectedField)}>
                Route to Discover
              </button>
            ) : null}
          </div>
        </section>
      ) : null}
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

function ProposalReview({ thread, busy, onDecide, onAsk }) {
  const proposal = thread?.state?.proposal || {};
  const operations = Array.isArray(proposal.operations) ? proposal.operations : [];
  const canDecide = Boolean(proposal.id && proposal.proposal_hash);
  return (
    <section className="s04-card" data-testid="synthesis-proposal-state">
      <header className="s04-title">
        <div>
          <small>Review proposed change</small>
          <h2>{text(proposal.title, "Untitled proposal")}</h2>
        </div>
        <em className="warn">Review required</em>
      </header>
      <div className="s04-resolved-list">
        <strong>{text(proposal.summary, "The agent proposed a change to this durable construction.")}</strong>
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
      </div>
      {proposal.execution_spec ? (
        <div className="s04-method">
          <div><dt>Input</dt><dd>{text(proposal.execution_spec.input_dataset_id, "Not reported")}</dd></div>
          <div><dt>Output</dt><dd>{text(proposal.execution_spec.output_dataset_id, "Not reported")}</dd></div>
          <div><dt>Grouping</dt><dd>{Array.isArray(proposal.execution_spec.group_by) ? proposal.execution_spec.group_by.join(" · ") : "Not reported"}</dd></div>
          <div><dt>Metrics</dt><dd>{Array.isArray(proposal.execution_spec.metrics) ? proposal.execution_spec.metrics.length : "Not reported"}</dd></div>
        </div>
      ) : null}
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

function ExecutionRecord({ thread, busy, onApproveAndRun, onAsk, onOpenDataset }) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const spec = state.execution_spec || {};
  const status = text(execution.status, "not requested").replace(/_/g, " ");
  const outputId = threadOutput(thread);
  const mode = stateFor(thread);
  const queryReady = mode === "query_ready";
  const registered = mode === "registered" || queryReady;
  const failed = execution.status === "failed";
  const hasSpec = Boolean(spec.input_dataset_id && spec.output_dataset_id);
  const primary = executionPrimaryAction(thread);

  return (
    <section className="s04-card" data-testid={queryReady ? "synthesis-query-ready-state" : registered ? "synthesis-registered-state" : failed ? "synthesis-failed-state" : "synthesis-execution-state"}>
      <header className="s04-title">
        <div>
          <small>{queryReady ? "Query-ready research asset" : registered ? "Registered research asset" : failed ? "Execution failed" : "Execution record"}</small>
          <h2>{registered ? text(outputId, "Registered output") : text(spec.output_dataset_id, "No execution requested")}</h2>
        </div>
        <em className={registered ? "success" : failed ? "warn" : "neutral"}>{queryReady ? "Query ready" : registered ? "Registered" : status}</em>
      </header>
      {hasSpec ? (
        <dl className="s04-method">
          <div><dt>Input</dt><dd>{text(spec.input_dataset_id)}</dd></div>
          <div><dt>Output</dt><dd>{text(spec.output_dataset_id)}</dd></div>
          <div><dt>Group by</dt><dd>{Array.isArray(spec.group_by) ? spec.group_by.join(" · ") : "Not reported"}</dd></div>
          <div><dt>Metrics</dt><dd>{Array.isArray(spec.metrics) ? `${spec.metrics.length} defined` : "Not reported"}</dd></div>
        </dl>
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
            <div><dt>Output</dt><dd>{text(outputId, "Not registered")}</dd></div>
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
                ? "Approve and run is the material write boundary. Backend may still pass through pending approval before the job is queued. Registration remains a separate verified outcome."
                : "An accepted execution specification is required before this thread can approve a build."}
        </p>
        {primary?.kind === "open_library" ? (
          <button type="button" className="rd-v2-btn primary" onClick={() => onOpenDataset?.({ dataset_id: outputId, name: outputId, analysis_readiness: "instant" })}>
            {primary.label}
          </button>
        ) : null}
        {primary?.kind === "approve_and_run" ? (
          <button type="button" className="rd-v2-btn primary" disabled={busy} onClick={onApproveAndRun}>
            {primary.label}
          </button>
        ) : null}
        <button type="button" className="rd-v2-btn" onClick={() => onAsk("Explain the exact execution state and which evidence is still missing before this output can be trusted.")}>Ask about execution</button>
      </footer>
    </section>
  );
}

function ThreadCreatedCard({ thread, onAsk }) {
  const card = threadCreatedCardModel(thread);
  return (
    <section className="s04-card s04-thread-created" data-testid="synthesis-thread-created-state">
      <header className="s04-title">
        <div>
          <small>{card.eyebrow}</small>
          <h2>{card.title}</h2>
        </div>
        <em className="neutral">{card.status}</em>
      </header>
      <div className="s04-pairs">
        <article>
          <small>Interpreted objective</small>
          <strong>{card.objective}</strong>
          <p>The durable thread is attached to this canvas and the conversation. No method is accepted yet.</p>
        </article>
        <article>
          <small>Required grain</small>
          <strong>{card.grain}</strong>
          <p>Ask may refine grain before a proposal is accepted.</p>
        </article>
        <article>
          <small>Next research step</small>
          <strong>{card.nextStep}</strong>
          <p>{card.truth}</p>
        </article>
      </div>
      <footer className="s04-actions">
        <p>
          <small>Conversation sync</small>
          Continue in Ask without leaving this construction canvas.
        </p>
        <button
          type="button"
          className="rd-v2-btn primary"
          onClick={() => onAsk(`Interpret this research objective and propose the smallest defensible construction: ${card.objective}`)}
        >
          Continue in conversation
        </button>
      </footer>
    </section>
  );
}

function NewThread({ objective, setObjective, busy, onCreate, onAsk }) {
  return (
    <section className="s04-intent" data-testid="synthesis-intent-state">
      <small>New research construction</small>
      <h2>What reusable research asset do you need?</h2>
      <p>Start with the research object. Ask can reason with the thread, but no method, execution, or Library asset is created until separately reviewed.</p>
      <textarea rows={7} value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="Describe the research object, coverage, grain, and constraints…" />
      <footer>
        <span>A new durable thread is created before the conversation continues.</span>
        <button type="button" className="rd-v2-btn primary" disabled={busy || !objective.trim()} onClick={onCreate}>Create thread &amp; discuss</button>
        <button type="button" className="rd-v2-btn" disabled={!objective.trim()} onClick={() => onAsk(objective)}>Ask first</button>
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

export function SynthesisPage({ onAskComposer, onApproveJob, onDiscoverHandoff, onOpenDataset, onSelectThread }) {
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
  const [selectedField, setSelectedField] = useState(null);
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
    onSelectThread?.(selected, { keepRail: true });
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
    setSelectedField(null);
    setNewMode(false);
    setError("");
    try {
      const next = await refreshThread(threadId);
      if (next) onSelectThread?.(next);
    } catch (cause) {
      setError(text(cause?.message, "This Synthesis thread could not be refreshed."));
    }
  };

  const ask = (prompt, threadOverride = selected) => {
    const context = threadOverride
      ? `\n\nSynthesis thread: ${titleFor(threadOverride)}\nObjective: ${text(threadOverride.objective || threadOverride.state?.objective)}\nDurable status: ${stageLabel(threadOverride)}.`
      : "\n\nSynthesis workspace context.";
    onAskComposer?.({ prompt: `${text(prompt)}${context}`, displayText: text(prompt, "Discuss this synthesis") });
  };

  const routeToDiscover = async (field) => {
    if (!selected || !isEvidenceGap(field)) return;
    setBusy(true);
    setError("");
    try {
      const handoff = await getSynthesisDiscoverHandoff(selected.id);
      const evidenceId = String(field.id || field.dataset_id || "");
      const match = (item) => String(item?.id || item?.evidence_id || item?.dataset_id || "") === evidenceId;
      const missingEvidence = (handoff?.missing_evidence || []).filter(match);
      const collectIntents = (handoff?.collect_intents || []).filter(match);
      if (!missingEvidence.length) throw new Error("This evidence gap is no longer part of the durable Discover handoff.");
      onDiscoverHandoff?.({
        field,
        handoff: {
          ...handoff,
          missing_evidence: missingEvidence,
          collect_intents: collectIntents,
        },
        thread: selected,
      });
    } catch (cause) {
      setError(text(cause?.message, "The Discover handoff could not be prepared."));
    } finally {
      setBusy(false);
    }
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
      notified.current = `${created.id}:${created.updated_at || ""}:${created.state?.execution?.status || ""}`;
      onSelectThread?.(created, { openAsk: true });
      ask(`Interpret this research objective and propose the smallest defensible construction: ${nextObjective}`, created);
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
      notified.current = `${created.id}:${created.updated_at || ""}:${created.state?.execution?.status || ""}`;
      onSelectThread?.(created, { openAsk: true });
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
      onSelectThread?.(next, { keepRail: true });
    } catch (cause) {
      setError(text(cause?.message, "The proposal changed before this decision could be saved."));
      refreshThread().catch(() => {});
    } finally {
      setBusy(false);
    }
  };

  const approveAndRun = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      let next = selected;
      let execution = next.state?.execution || {};
      if (execution.status !== "pending_approval") {
        const result = await requestSynthesisExecution(selected.id);
        next = result?.thread || (result?.state ? result : await refreshThread(selected.id));
        if (next) {
          replaceThread(next);
          onSelectThread?.(next, { keepRail: true });
        }
        execution = next?.state?.execution || result?.job || {};
      }
      const jobId = execution.job_id || execution.id;
      const status = text(execution.status || "").toLowerCase();
      if (status === "pending_approval" && jobId) {
        if (!onApproveJob) throw new Error("Approval is unavailable on this desk.");
        const approved = await onApproveJob(jobId);
        if (!approved) throw new Error("The build was not approved. Review the error and try again.");
        next = await refreshThread(selected.id);
        if (next) onSelectThread?.(next, { keepRail: true });
      } else if (!jobId && !status) {
        throw new Error("The execution request did not return a durable job.");
      }
    } catch (cause) {
      setError(text(cause?.message, "The execution could not be approved and run."));
      refreshThread().catch(() => {});
    } finally {
      setBusy(false);
    }
  };

  const mode = stateFor(selected);
  const showExecution = Boolean(selected && (mode === "execution" || mode === "registered" || mode === "failed" || selected.state?.execution_spec));

  return (
    <PageShell className="rd-v2-synthesis-page" title="Synthesis" lead="Construct reusable research assets from registered evidence, with decisions and execution state kept durable.">
      <div className="s04-shell" data-testid="synthesis-studio">
        <ThreadList
          threads={threads}
          selectedId={selectedId}
          loading={loading}
          onSelect={selectThread}
          onNew={() => { setNewMode(true); setObjective(""); }}
        />
        <main className="s04-main">
          {error ? <p className="s04-fixture" role="alert">{error}</p> : null}
          {newMode ? <NewThread objective={objective} setObjective={setObjective} busy={busy} onCreate={createThread} onAsk={ask} /> : null}
          {!newMode && !loading && !selected ? (
            <EmptyWorkspace
              profiles={profiles}
              profilesLoading={profilesLoading}
              profilesError={profilesError}
              onStartBlueprint={startBlueprint}
              onNew={() => setNewMode(true)}
            />
          ) : null}
          {!newMode && selected ? (
            <>
              <ThreadHeader thread={selected} />
              {mode === "proposal" ? <ProposalReview thread={selected} busy={busy} onDecide={decideProposal} onAsk={ask} /> : null}
              {showExecution ? <ExecutionRecord thread={selected} busy={busy} onApproveAndRun={approveAndRun} onAsk={ask} onOpenDataset={onOpenDataset} /> : null}
              {mode === "explore" ? <EvidenceMap thread={selected} selectedField={selectedField} onAsk={ask} onRouteToDiscover={routeToDiscover} onSelectField={setSelectedField} /> : null}
              {mode === "draft" && !showExecution ? <ThreadCreatedCard thread={selected} onAsk={ask} /> : null}
            </>
          ) : null}
        </main>
      </div>
    </PageShell>
  );
}
