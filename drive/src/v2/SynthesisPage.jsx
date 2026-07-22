import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createSynthesisThread,
  decideSynthesisProposal,
  getSynthesisThread,
  listSynthesisProfiles,
  listSynthesisThreads,
} from "@/v2/api";
import { synthesisThreadObject } from "@/v2/activeObject";
import {
  isSynthesisThreadsUnavailableError,
  presentLocalDraftFallback,
  presentSynthesisThread,
} from "@/v2/synthesisThreadPresentation";
import { PageShell } from "@/v2/ui";

const CONSTRUCTION_NODES = ["inputs", "method", "validation", "output"];
const NODE_LABELS = { inputs: "Inputs", method: "Method", validation: "Validation", output: "Output" };
const PENDING_OBJECTIVE = "New synthesis — research measure pending Composer.";

function profileTitle(row) {
  return row?.title || row?.id || "Synthesis profile";
}

function newComposerSessionId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `syn-${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
  }
  return `syn-${Date.now().toString(36)}`;
}

function toActiveThread(view, thread, { selectedStep, selectedEvidence, localDraftFallback }) {
  return {
    id: view.id,
    title: view.title,
    objective: view.objective,
    localDraft: Boolean(view.localDraft || localDraftFallback),
    materialisation: view.materialisation,
    session_id: view.sessionId || thread?.session_id || "",
    conversation_id: view.conversationId || thread?.conversation_id || "",
    state: {
      workbench: true,
      maturityLabel: view.maturityLabel,
      title: view.title,
      objective: view.objective,
      recordedNeed: view.localDraft ? view.objective : "",
      selectedStep,
      selectedStepLabel: NODE_LABELS[selectedStep],
      selectedStepSummary: view.nodeSummaries[selectedStep],
      selectedStepDetail: selectedEvidence
        ? `Selected evidence: ${selectedEvidence}`
        : view.nodeSummaries[selectedStep],
      selectedEvidence,
      sources: view.sources,
      joinKeys: view.grain ? [view.grain] : [],
      grain: view.grain,
      review: view.review,
      constructionState: view.constructionState,
      proposalState: view.constructionState,
      proposal: view.proposal,
      nodes: view.nodes,
      edges: view.edges,
      spec: view.spec,
      activity: view.activity,
      execution: view.outputProven
        ? { ...view.execution, status: "registered", output_dataset_id: view.outputId }
        : view.execution || { status: view.localDraft ? "local_draft" : "not_requested" },
    },
  };
}

export function SynthesisPage({
  onAskComposer,
  onToast,
  onOpenDataset,
  onSynthesisSelection,
  refreshToken = 0,
}) {
  const [catalog, setCatalog] = useState(null);
  const [threads, setThreads] = useState([]);
  const [threadsApiOk, setThreadsApiOk] = useState(null);
  const [thread, setThread] = useState(null);
  const [localDraftFallback, setLocalDraftFallback] = useState(false);
  const [sessionNeed, setSessionNeed] = useState("");
  const [busy, setBusy] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedNode, setSelectedNode] = useState("inputs");
  const [selectedEvidence, setSelectedEvidence] = useState("");
  const [dirOpen, setDirOpen] = useState(false);
  const [workbenchTab, setWorkbenchTab] = useState("model");
  const [selectionEpoch, setSelectionEpoch] = useState(1);
  const dirRef = useRef(null);
  const railFocusRef = useRef({ seq: 1, mode: "ask" });
  const appliedRailFocusSeqRef = useRef(0);

  const profiles = catalog?.profiles || [];

  const view = useMemo(() => {
    if (thread && !localDraftFallback) {
      return presentSynthesisThread(thread, {
        selectedStep: selectedNode,
        selectedEvidence,
      });
    }
    return presentLocalDraftFallback({ sessionNeed, selectedStep: selectedNode });
  }, [thread, localDraftFallback, sessionNeed, selectedNode, selectedEvidence]);

  const loadCatalog = useCallback(async () => {
    try {
      setCatalog(await listSynthesisProfiles());
    } catch (err) {
      /* profiles are optional starting points */
      setCatalog({ profiles: [], latest: {} });
      setError((prev) => prev || err.message || String(err));
    }
  }, []);

  const loadThreads = useCallback(async () => {
    try {
      const out = await listSynthesisThreads({ limit: 40 });
      setThreads(Array.isArray(out?.threads) ? out.threads : []);
      setThreadsApiOk(true);
      setError("");
      return true;
    } catch (err) {
      setThreads([]);
      setThreadsApiOk(false);
      if (!isSynthesisThreadsUnavailableError(err)) {
        setError(err.message || String(err));
      }
      return false;
    }
  }, []);

  const applyThread = useCallback((next, { focusAsk = false, focusDetail = false } = {}) => {
    setThread(next);
    setLocalDraftFallback(false);
    setSessionNeed("");
    setSelectedEvidence("");
    setWorkbenchTab("model");
    const seq = railFocusRef.current.seq + 1;
    railFocusRef.current = {
      seq,
      mode: focusDetail ? "detail" : focusAsk ? "ask" : railFocusRef.current.mode,
    };
    setSelectionEpoch(seq);
  }, []);

  const refreshOpenThread = useCallback(async () => {
    if (!thread?.id || localDraftFallback) return;
    try {
      const next = await getSynthesisThread(thread.id);
      setThread(next);
      setError("");
    } catch (err) {
      setError(err.message || String(err));
    }
  }, [thread?.id, localDraftFallback]);

  useEffect(() => {
    loadCatalog();
    loadThreads();
  }, [loadCatalog, loadThreads]);

  useEffect(() => {
    if (refreshToken > 0) refreshOpenThread();
  }, [refreshToken, refreshOpenThread]);

  useEffect(() => {
    if (!dirOpen) return undefined;
    const onPointer = (event) => {
      if (!dirRef.current?.contains(event.target)) setDirOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") setDirOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [dirOpen]);

  const publishSelection = useCallback(
    (nodeId, opts = {}) => {
      setSelectedNode(nodeId);
      setSelectedEvidence("");
      const seq = railFocusRef.current.seq + 1;
      railFocusRef.current = { seq, mode: opts.focusDetail ? "detail" : opts.focusAsk ? "ask" : "detail" };
      setSelectionEpoch(seq);
    },
    [],
  );

  const publishEvidence = useCallback((source) => {
    setSelectedEvidence(source);
    setSelectedNode("inputs");
    const seq = railFocusRef.current.seq + 1;
    railFocusRef.current = { seq, mode: "detail" };
    setSelectionEpoch(seq);
  }, []);

  useEffect(() => {
    const { seq, mode } = railFocusRef.current;
    const opts = {};
    if (seq > appliedRailFocusSeqRef.current && mode) {
      if (mode === "ask") opts.focusAsk = true;
      else if (mode === "detail") opts.focusDetail = true;
      appliedRailFocusSeqRef.current = seq;
    }
    onSynthesisSelection?.(
      synthesisThreadObject(
        toActiveThread(view, thread, {
          selectedStep: selectedNode,
          selectedEvidence,
          localDraftFallback: localDraftFallback || view.localDraft,
        }),
      ),
      opts,
    );
  }, [
    view,
    thread,
    selectedNode,
    selectedEvidence,
    localDraftFallback,
    selectionEpoch,
    onSynthesisSelection,
  ]);

  const startLocalDraft = useCallback(
    (message) => {
      setThread(null);
      setLocalDraftFallback(true);
      setSessionNeed("");
      setSelectedNode("inputs");
      setSelectedEvidence("");
      setWorkbenchTab("model");
      setDirOpen(false);
      const seq = railFocusRef.current.seq + 1;
      railFocusRef.current = { seq, mode: "ask" };
      setSelectionEpoch(seq);
      if (message) onToast?.(message);
    },
    [onToast],
  );

  const startNewSynthesis = useCallback(async () => {
    setBusy(true);
    setDirOpen(false);
    try {
      const ok = threadsApiOk === false ? false : threadsApiOk === true ? true : await loadThreads();
      if (!ok) {
        startLocalDraft("Synthesis thread API unavailable — keeping a local draft only.");
        return;
      }
      const sessionId = newComposerSessionId();
      const created = await createSynthesisThread({
        objective: PENDING_OBJECTIVE,
        title: "New synthesis",
        sessionId,
      });
      applyThread(created, { focusAsk: true });
      await loadThreads();
      onToast?.("Durable synthesis thread opened");
    } catch (err) {
      startLocalDraft(
        isSynthesisThreadsUnavailableError(err)
          ? "Synthesis thread API unavailable — keeping a local draft only."
          : `Could not create thread (${err.message || err}) — local draft only.`,
      );
    } finally {
      setBusy(false);
    }
  }, [threadsApiOk, loadThreads, startLocalDraft, applyThread, onToast]);

  const openThread = useCallback(
    async (threadId) => {
      setBusy(true);
      setDirOpen(false);
      try {
        const next = await getSynthesisThread(threadId);
        applyThread(next, { focusAsk: true });
        setError("");
      } catch (err) {
        setError(err.message || String(err));
        onToast?.(err.message || "Could not open synthesis thread", "error");
      } finally {
        setBusy(false);
      }
    },
    [applyThread, onToast],
  );

  const startFromProfile = useCallback(
    async (profile) => {
      setBusy(true);
      setDirOpen(false);
      try {
        const ok = threadsApiOk === false ? false : threadsApiOk === true ? true : await loadThreads();
        if (!ok) {
          startLocalDraft("Thread API unavailable — profile kept as local draft starting point.");
          setSessionNeed(profile?.research_questions?.[0] || profileTitle(profile));
          return;
        }
        const objective =
          profile?.research_questions?.[0] ||
          String(profile?.description || "").trim() ||
          `Construct a defensible panel from profile ${profileTitle(profile)}.`;
        const created = await createSynthesisThread({
          objective,
          title: profileTitle(profile),
          sessionId: newComposerSessionId(),
        });
        applyThread(created, { focusAsk: true });
        await loadThreads();
        onToast?.(`Opened durable thread from ${profileTitle(profile)}`);
      } catch (err) {
        startLocalDraft(`Could not open thread — local draft only. ${err.message || ""}`.trim());
        setSessionNeed(profile?.research_questions?.[0] || profileTitle(profile));
      } finally {
        setBusy(false);
      }
    },
    [threadsApiOk, loadThreads, startLocalDraft, applyThread, onToast],
  );

  const decideProposal = useCallback(
    async (decision) => {
      if (!thread?.id || !view.proposal?.id || !view.proposal?.proposalHash) return;
      setDecisionBusy(true);
      try {
        const next = await decideSynthesisProposal(thread.id, {
          decision,
          proposalId: view.proposal.id,
          proposalHash: view.proposal.proposalHash,
        });
        setThread(next);
        setError("");
        onToast?.(decision === "accept" ? "Proposal accepted" : "Proposal rejected");
        await loadThreads();
      } catch (err) {
        setError(err.message || String(err));
        onToast?.(err.message || "Proposal decision failed", "error");
      } finally {
        setDecisionBusy(false);
      }
    },
    [thread?.id, view.proposal, onToast, loadThreads],
  );

  useEffect(() => {
    if (threadsApiOk !== true || thread || localDraftFallback) return;
    if (threads.length) {
      openThread(threads[0].id);
      return;
    }
    startNewSynthesis();
  }, [threadsApiOk]); // eslint-disable-line react-hooks/exhaustive-deps -- one-shot open on API discovery

  useEffect(() => {
    if (threadsApiOk === false && !thread && !localDraftFallback) {
      startLocalDraft();
    }
  }, [threadsApiOk]); // eslint-disable-line react-hooks/exhaustive-deps

  const constructionState = view.constructionState;
  const activeTitle = view.title;
  const lifecycle = view.maturityLabel;

  const directoryPanel = (
    <div className="rd-v2-synthesis-directory-panel" data-testid="synthesis-directory" aria-label="Syntheses">
      <div className="rd-v2-synthesis-directory-head">
        <h2>Syntheses</h2>
        <button type="button" className="rd-v2-btn sm" data-testid="synthesis-directory-new" onClick={startNewSynthesis}>
          New synthesis
        </button>
      </div>
      <p className="rd-v2-synthesis-directory-note muted small">
        {threadsApiOk
          ? "Durable threads are authoritative. Profiles are starting points that open a new thread."
          : "Durable thread API unavailable — New synthesis stays a local draft only."}
      </p>
      {localDraftFallback || view.localDraft ? (
        <button
          type="button"
          className="rd-v2-synthesis-directory-item on"
          data-testid="synthesis-directory-draft"
          aria-pressed="true"
        >
          <strong>Current draft</strong>
          <span>Local only · not saved</span>
        </button>
      ) : null}
      {threads.length ? (
        <ul className="rd-v2-synthesis-directory-list" data-testid="synthesis-directory-threads">
          {threads.map((row) => {
            const active = !localDraftFallback && thread?.id === row.id;
            return (
              <li key={row.id}>
                <button
                  type="button"
                  className={`rd-v2-synthesis-directory-item${active ? " on" : ""}`}
                  data-testid={`synthesis-directory-thread-${row.id}`}
                  onClick={() => openThread(row.id)}
                >
                  <strong>{row.title || row.id}</strong>
                  <span>{row.materialisation || "not_materialised"}</span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {profiles.length ? (
        <>
          <p className="muted small" style={{ margin: "10px 0 6px" }}>
            Profile starting points
          </p>
          <ul className="rd-v2-synthesis-directory-list">
            {profiles.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className="rd-v2-synthesis-directory-item"
                  data-testid={`synthesis-directory-item-${row.id}`}
                  onClick={() => startFromProfile(row)}
                >
                  <strong>{profileTitle(row)}</strong>
                  <span>Opens a durable thread</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {!threads.length && !profiles.length ? <p className="muted small">No threads or profiles loaded yet.</p> : null}
    </div>
  );

  const proposalCard =
    view.proposal && !view.localDraft ? (
      <div className="rd-v2-synthesis-proposal-card" data-testid="synthesis-proposal-card">
        <header>
          <small>Controlled proposal</small>
          <strong>{view.proposal.title}</strong>
        </header>
        {view.proposal.summary ? <p>{view.proposal.summary}</p> : null}
        <div className="rd-v2-synthesis-actions">
          <button
            type="button"
            className="rd-v2-btn sm primary"
            data-testid="synthesis-proposal-accept"
            disabled={decisionBusy}
            onClick={() => decideProposal("accept")}
          >
            {decisionBusy ? "…" : "Accept proposal"}
          </button>
          <button
            type="button"
            className="rd-v2-btn sm"
            data-testid="synthesis-proposal-reject"
            disabled={decisionBusy}
            onClick={() => decideProposal("reject")}
          >
            Reject
          </button>
        </div>
      </div>
    ) : null;

  const modelPane = (
    <div className="rd-v2-synthesis-model" data-testid="synthesis-construction" aria-label="Construction model">
      <header className="rd-v2-synthesis-pane-head">
        <div>
          <small>{lifecycle}</small>
          <h2>{activeTitle}</h2>
        </div>
        {view.localDraft || localDraftFallback ? (
          <em data-testid="synthesis-session-draft">Local current-session draft</em>
        ) : constructionState === "empty" ? (
          <em className="rd-v2-synthesis-spec-state is-empty" data-testid="synthesis-state-empty">
            Unformed
          </em>
        ) : (
          <em
            className={`rd-v2-synthesis-spec-state${constructionState === "accepted" ? " is-accepted" : " is-proposed"}`}
            data-testid={constructionState === "accepted" ? "synthesis-state-accepted" : "synthesis-state-proposed"}
          >
            {constructionState === "accepted" ? "Accepted" : "Proposed"}
          </em>
        )}
      </header>

      {view.localDraft || localDraftFallback ? (
        <p className="rd-v2-synthesis-draft-note" data-testid="synthesis-draft-note">
          Local workbench draft only. Not saved thread history. Use Composer in the rail to record the research need.
        </p>
      ) : null}

      {!view.localDraft && threadsApiOk ? (
        <p className="muted small" data-testid="synthesis-thread-id">
          Thread {view.id}
          {view.sessionId ? ` · Composer session ${view.sessionId}` : ""}
        </p>
      ) : null}

      <p className="rd-v2-synthesis-model-lead">
        Semantic construction ·{" "}
        {constructionState === "proposed"
          ? "proposed, not accepted"
          : constructionState === "accepted"
            ? "accepted construction present"
            : "unformed — waiting for a controlled proposal"}
      </p>

      {constructionState === "empty" ? (
        <div className="rd-v2-synthesis-unformed" data-testid="synthesis-construction-unformed">
          <p>Model stays empty until Composer returns a controlled proposal on this thread.</p>
        </div>
      ) : (
        <ol
          className={`rd-v2-synthesis-nodes${constructionState === "proposed" ? " is-proposed" : ""}${constructionState === "accepted" ? " is-accepted" : ""}`}
          data-testid="synthesis-construction-map"
        >
          {CONSTRUCTION_NODES.map((nodeId, index) => {
            const selected = selectedNode === nodeId && !selectedEvidence;
            return (
              <li key={nodeId}>
                <button
                  type="button"
                  className={`rd-v2-synthesis-node${selected ? " on" : ""}${constructionState === "proposed" ? " is-proposed" : ""}`}
                  data-testid={`synthesis-node-${nodeId}`}
                  data-selected={selected ? "true" : "false"}
                  data-state={constructionState}
                  aria-pressed={selected}
                  onClick={() => publishSelection(nodeId, { focusDetail: true })}
                >
                  <span className="rd-v2-synthesis-node-step">{index + 1}</span>
                  <span className="rd-v2-synthesis-node-body">
                    <strong>{NODE_LABELS[nodeId]}</strong>
                    <em>{view.nodeSummaries[nodeId]}</em>
                  </span>
                </button>
                {index < CONSTRUCTION_NODES.length - 1 ? (
                  <span className="rd-v2-synthesis-node-arrow" aria-hidden="true">
                    ↓
                  </span>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}

      {proposalCard}

      {view.sources.length ? (
        <div className="rd-v2-synthesis-node-detail" data-testid="synthesis-node-detail">
          <h4>{selectedEvidence ? `Evidence · ${selectedEvidence}` : NODE_LABELS[selectedNode]}</h4>
          <p>
            {selectedEvidence
              ? `Selected evidence: ${selectedEvidence}`
              : view.nodeSummaries[selectedNode]}
          </p>
        </div>
      ) : null}

      <div className="rd-v2-synthesis-actions" data-testid="synthesis-actions">
        <button
          type="button"
          className="rd-v2-btn sm"
          data-testid="synthesis-ask"
          disabled={busy}
          onClick={() =>
            onAskComposer?.(
              view.localDraft || localDraftFallback
                ? sessionNeed
                  ? `Research need for this local synthesis draft: ${sessionNeed}. Inputs and method remain unresolved.`
                  : "Draft a new synthesis. What research measure should we construct?"
                : `Continue synthesis thread ${view.id}. Objective: ${view.objective}. Propose controlled construction ops only.`,
            )
          }
        >
          Discuss in Composer →
        </button>
        {!view.localDraft && thread?.id ? (
          <button type="button" className="rd-v2-btn sm" disabled={busy} onClick={refreshOpenThread}>
            Refresh thread
          </button>
        ) : null}
      </div>
    </div>
  );

  const evidencePane = (
    <div className="rd-v2-synthesis-evidence-pane" data-testid="synthesis-evidence-pane">
      <h3>Evidence</h3>
      <p className="muted small">Evidence mapped from the durable thread proposal or accepted nodes.</p>
      {view.sources.length ? (
        <ul className="rd-v2-synthesis-evidence-list" data-testid="synthesis-evidence-list">
          {view.sources.map((source) => (
            <li key={source}>
              <button
                type="button"
                className={`rd-v2-synthesis-evidence-item${selectedEvidence === source ? " on" : ""}`}
                data-testid={`synthesis-evidence-item-${source}`}
                data-selected={selectedEvidence === source ? "true" : "false"}
                aria-pressed={selectedEvidence === source}
                onClick={() => publishEvidence(source)}
              >
                <strong>{source}</strong>
                <span>Select to inspect in Detail</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted" data-testid="synthesis-evidence-empty">
          No evidence mapped until a controlled proposal arrives.
        </p>
      )}
    </div>
  );

  const dataPane = (
    <div className="rd-v2-synthesis-data-pane" data-testid="synthesis-data-pane">
      <h3>Data</h3>
      <p className="muted" data-testid="synthesis-data-empty">
        No preview data is available. This tab does not claim that collection ran.
      </p>
    </div>
  );

  const specPane = (
    <div className="rd-v2-synthesis-spec-pane" data-testid="synthesis-spec-pane">
      <header className="rd-v2-synthesis-pane-head">
        <div>
          <small>Spec</small>
          <h3>Construction specification</h3>
        </div>
        <em
          className={`rd-v2-synthesis-spec-state${
            constructionState === "accepted"
              ? " is-accepted"
              : constructionState === "proposed"
                ? " is-proposed"
                : " is-empty"
          }`}
          data-testid="synthesis-spec-state"
        >
          {constructionState === "accepted"
            ? "Accepted"
            : constructionState === "proposed"
              ? "Proposed"
              : "Empty"}
        </em>
      </header>
      <dl className="rd-v2-synthesis-spec-grid">
        <div>
          <dt>Target grain</dt>
          <dd data-testid="synthesis-spec-grain">{view.grain || "Not proposed"}</dd>
        </div>
        <div>
          <dt>Inputs</dt>
          <dd data-testid="synthesis-spec-inputs">
            {view.sources.length ? view.sources.join(" · ") : "No inputs mapped yet."}
          </dd>
        </div>
        <div>
          <dt>Transform / method</dt>
          <dd data-testid="synthesis-spec-method">{view.nodeSummaries.method}</dd>
        </div>
        <div>
          <dt>Validation</dt>
          <dd data-testid="synthesis-spec-validation">{view.nodeSummaries.validation}</dd>
        </div>
        <div>
          <dt>Output identity</dt>
          <dd data-testid="synthesis-spec-output" className={view.outputId ? "mono" : undefined}>
            {view.outputId || view.nodeSummaries.output}
          </dd>
        </div>
        <div>
          <dt>State</dt>
          <dd data-testid="synthesis-spec-lifecycle">
            {constructionState === "accepted"
              ? "Accepted"
              : constructionState === "proposed"
                ? "Proposed"
                : "Empty"}
          </dd>
        </div>
      </dl>
      <p className="muted small" data-testid="synthesis-spec-need">
        Research need: {view.objective || "Not recorded"}
      </p>
      {proposalCard}
    </div>
  );

  const outputPane = (
    <div className="rd-v2-synthesis-output-pane" data-testid="synthesis-output-pane">
      <h3>Output</h3>
      {view.outputProven ? (
        <div className="rd-v2-synthesis-output-proof" data-testid="synthesis-output-proof">
          <p>Registered identity: {view.outputId}</p>
          <div className="rd-v2-synthesis-actions">
            <button
              type="button"
              className="rd-v2-btn sm primary"
              onClick={() => onOpenDataset?.({ dataset_id: view.outputId, name: view.outputId })}
            >
              Open in Library
            </button>
          </div>
        </div>
      ) : (
        <p className="muted" data-testid="synthesis-output-empty">
          Output not materialised. No registered output is claimed without execution evidence.
        </p>
      )}
    </div>
  );

  const workbenchBody = (() => {
    if (workbenchTab === "evidence") return evidencePane;
    if (workbenchTab === "data") return dataPane;
    if (workbenchTab === "spec") return specPane;
    if (workbenchTab === "output") return outputPane;
    return modelPane;
  })();

  return (
    <PageShell className="rd-v2-synthesis-page" title="Synthesis" lead="Chat-to-construction workbench">
      {error ? <p className="rd-v2-error-banner">{error}</p> : null}

      <div className="rd-v2-synthesis-workbench" data-testid="synthesis-workbench">
        <div className="rd-v2-synthesis-strip" data-testid="synthesis-strip">
          <div className="rd-v2-synthesis-selector" ref={dirRef}>
            <button
              type="button"
              className="rd-v2-synthesis-selector-trigger"
              data-testid="synthesis-dir-trigger"
              aria-expanded={dirOpen}
              aria-haspopup="listbox"
              onClick={() => setDirOpen((open) => !open)}
            >
              <span>Syntheses</span>
              <strong>{activeTitle}</strong>
              <em>{lifecycle}</em>
            </button>
            {dirOpen ? (
              <div className="rd-v2-synthesis-selector-popover" role="listbox">
                {directoryPanel}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            className="rd-v2-btn sm rd-v2-synthesis-new"
            data-testid="synthesis-new"
            aria-label="New synthesis"
            disabled={busy}
            onClick={startNewSynthesis}
          >
            <span className="rd-v2-synthesis-new-full">New synthesis</span>
            <span className="rd-v2-synthesis-new-compact" aria-hidden="true">
              + New
            </span>
          </button>
        </div>

        <div
          className="rd-v2-synthesis-centre-tabs"
          role="tablist"
          aria-label="Workbench"
          data-testid="synthesis-workbench-tabs"
        >
          {["model", "evidence", "data", "spec", "output"].map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={workbenchTab === id}
              className={workbenchTab === id ? "is-active" : ""}
              data-testid={`synthesis-workbench-tab-${id}`}
              onClick={() => setWorkbenchTab(id)}
            >
              {id.charAt(0).toUpperCase() + id.slice(1)}
            </button>
          ))}
        </div>

        <section className="rd-v2-synthesis-active" aria-label="Active synthesis workspace">
          <div className="rd-v2-synthesis-workbench-body" data-testid="synthesis-workbench-body">
            {workbenchBody}
          </div>
        </section>
      </div>
    </PageShell>
  );
}
