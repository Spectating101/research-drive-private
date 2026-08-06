import { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { GuidedState, ProgressSteps } from "@/v2/InteractionFeedback";
import { useAskChat } from "@/v2/useAskChat";
import { handleEnterToSubmit } from "@/v2/enterToSubmit";
import { formatAskText } from "@/v2/askText.jsx";
import { AskAgentCard } from "@/v2/AskAgentCard.jsx";
import { displayName } from "@/v2/datasetMeta";
import { decideSynthesisProposal, requestSynthesisExecution } from "@/v2/api";

export function AskRail({
  dataset,
  mainTab,
  searchQuery,
  pendingMessage,
  onPendingConsumed,
  onCollected,
  onSynthesisChanged,
  onApproveJob,
  onToast,
  railContext,
}) {
  const { messages, input, setInput, busy, status, send, contextLabel } = useAskChat({
    dataset,
    railContext,
    onCollected,
    onSynthesisChanged,
    onToast,
  });
  const pendingSentRef = useRef("");
  const textareaRef = useRef(null);
  const [approvalState, setApprovalState] = useState({});
  const [proposalState, setProposalState] = useState("");

  useEffect(() => {
    if (!pendingMessage || busy) return;
    const pendingKey =
      typeof pendingMessage === "string"
        ? pendingMessage
        : `${pendingMessage.prompt || ""}::${pendingMessage.displayText || ""}`;
    if (!pendingKey || pendingSentRef.current === pendingKey) return;
    pendingSentRef.current = pendingKey;
    send(pendingMessage).finally(() => {
      pendingSentRef.current = "";
      onPendingConsumed?.();
    });
  }, [pendingMessage, busy, send, onPendingConsumed]);

  const requestApproval = async (jobId) => {
    if (!jobId || approvalState[jobId]?.status === "working") return;
    setApprovalState((current) => ({ ...current, [jobId]: { status: "working" } }));
    try {
      await Promise.resolve(onApproveJob?.(jobId));
    } finally {
      setApprovalState((current) => {
        const next = { ...current };
        delete next[jobId];
        return next;
      });
    }
  };

  const decideProposal = async ({ decision, threadId, proposal } = {}) => {
    const tid = String(threadId || dataset?.thread_id || railContext?.thread_id || "").trim();
    if (!tid || !decision || proposalState === "working") return;
    setProposalState("working");
    try {
      await decideSynthesisProposal(tid, {
        decision,
        proposalId: proposal?.id,
        proposalHash: proposal?.proposal_hash || proposal?.hash,
      });
      onSynthesisChanged?.({ threadId: tid, proposal, decision });
      onToast?.(decision === "accept" ? "Proposal accepted" : "Proposal rejected");
    } catch (err) {
      onToast?.(err?.message || "Proposal decision failed");
    } finally {
      setProposalState("");
    }
  };

  const requestExecution = async (threadId) => {
    const tid = String(threadId || dataset?.thread_id || railContext?.thread_id || "").trim();
    if (!tid || proposalState === "working") return;
    setProposalState("working");
    try {
      await requestSynthesisExecution(tid);
      onSynthesisChanged?.({ threadId: tid, executionRequested: true });
      onToast?.("Execution requested — review in Synthesis");
    } catch (err) {
      const raw = String(err?.message || err || "");
      const human = /input_dataset_id|output_dataset_id|execution_spec|aggregate metrics|row_output/i.test(raw)
        ? "Accepted method is documented, but it has no bounded registry execution_spec yet. Ask can propose aggregates or row_output lag/diff/rolling transforms when those are defensible from held evidence."
        : raw || "Execution request failed";
      onToast?.(human);
      // Persist in the rail so faculty can still read it after the toast fades.
      setStatus(human);
    } finally {
      setProposalState("");
    }
  };

  const ctxParts = [contextLabel, mainTab, searchQuery ? `search: ${searchQuery}` : ""].filter(Boolean);
  const isProfile = mainTab === "profile";
  const isSettings = mainTab === "settings";
  const isDiscover = mainTab === "browse";
  const isDiscoverHistory = isDiscover && dataset?.kind === "discover_history";
  const isDiscoverInvestigation = isDiscover && dataset?.kind === "discover_investigation";
  const isSynthesis = mainTab === "synthesis";
  const isLibrary = mainTab === "library";
  const workspace = railContext?.workspace && typeof railContext.workspace === "object"
    ? railContext.workspace
    : null;
  const openQuery = String(workspace?.query || searchQuery || "").trim();
  const openProposal =
    (workspace?.proposal && typeof workspace.proposal === "object" && workspace.proposal) ||
    (railContext?.selected?.proposal && typeof railContext.selected.proposal === "object"
      ? railContext.selected.proposal
      : null);
  const openProposalThreadId = String(
    workspace?.thread_id || railContext?.thread_id || dataset?.thread_id || "",
  ).trim();
  const profileContext = dataset?.title || "Profile";
  const synthesisContext =
    dataset?.title && dataset.title !== "Synthesis studio"
      ? dataset.title
      : "Synthesis studio";
  const hasThread = messages.length > 0;
  const discoverTitle = dataset?.title || dataset?.dataset_id || "";
  const assistingLabel = workspace?.label
    || (isDiscover ? "Discover" : isLibrary ? "Library" : isSynthesis ? "Synthesis" : "");
  const libraryAssistFocus = String(
    dataset?.title || workspace?.dataset_title || workspace?.folder_id || "",
  ).trim();
  const libraryAssistFocusClean = /^library(\s*·\s*library)?$/i.test(libraryAssistFocus)
    ? ""
    : libraryAssistFocus.replace(/^Library\s*·\s*/i, "").trim() || libraryAssistFocus;
  const railTitle = isProfile
    ? "Ask"
    : isSettings
      ? "Ask · desk setup"
    : isDiscoverHistory
      ? "Ask · lifecycle item"
      : isDiscoverInvestigation
        ? "Ask · investigation"
      : isDiscover && discoverTitle
        ? "Ask · selected source"
      : isDiscover && openQuery
        ? "Ask · Discover"
      : isDiscover
        ? "Ask · Discover"
        : isLibrary
          ? "Ask · Library"
        : isSynthesis
          ? "Ask · synthesis thread"
          : "Procurement chat";
  const railSubtitle = isProfile
    ? hasThread
      ? `Continuing · context → ${profileContext}`
      : `Context · ${profileContext}`
    : isSettings
      ? "Context · desk preferences and connection state"
    : isDiscoverHistory && discoverTitle
      ? `Lifecycle context · ${discoverTitle}`
      : isDiscoverInvestigation && discoverTitle
        ? hasThread
          ? `Continuing · investigation → ${discoverTitle}`
          : `Investigation · ${discoverTitle}`
      : isDiscover && discoverTitle && hasThread
        ? `Continuing · source → ${discoverTitle}`
      : isDiscover && discoverTitle
        ? `Selected · ${discoverTitle}`
      : isDiscover && openQuery
        ? `Assisting Discover · ${openQuery}`
      : isLibrary && libraryAssistFocusClean
        ? `Assisting Library · ${libraryAssistFocusClean}`
      : isLibrary
        ? "Assisting Library"
      : isSynthesis
        ? hasThread
          ? `Continuing · ${synthesisContext}`
          : `Assisting Synthesis · ${synthesisContext}`
      : assistingLabel && openQuery
        ? `Assisting ${assistingLabel} · ${openQuery}`
        : ctxParts.length
          ? `Context · ${ctxParts.join(" · ")}`
          : "Assisting the open desk surface";

  const askEntityTitle =
    (isLibrary
      ? libraryAssistFocusClean || "Library"
      : dataset?.dataset_id || dataset?.title
        ? displayName(dataset) || dataset?.title || dataset?.dataset_id
        : "") ||
    (isDiscover && openQuery ? openQuery : "") ||
    (isProfile ? profileContext : isSynthesis ? synthesisContext : assistingLabel || "Ask");

  return (
    <div className="rd-v2-ask-shell">
      <header className="rd-v2-ask-head">
        <p className="rd-v2-ask-head-eyebrow">{railTitle}</p>
        <strong>{askEntityTitle || "Ask"}</strong>
        <p className="rd-v2-ask-ctx">{railSubtitle}</p>
      </header>
      <div className="rd-v2-ask-messages" data-testid="ask-messages" aria-busy={busy}>
        {messages.length === 0 ? (
          isProfile ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                Ask how the saved research memory shapes Discover and Synthesis, or correct context that the desk
                should stop carrying forward.
              </p>
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  "What research context do you remember?",
                  "How does this profile affect Discover?",
                  "Which assumptions should I correct?",
                ].map((p) => (
                  <button key={p} type="button" className="rd-v2-chip clickable" disabled={busy} onClick={() => send(p)}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ) : isSettings ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                Ask what the current desk settings change, which connections are available, and where approval or
                readiness boundaries still apply.
              </p>
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  "Explain the current desk setup.",
                  "Which settings affect approvals?",
                  "What remains unconnected?",
                ].map((p) => (
                  <button key={p} type="button" className="rd-v2-chip clickable" disabled={busy} onClick={() => send(p)}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ) : isDiscoverHistory && discoverTitle ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                This lifecycle record stays in context. Ask about its durable state, evidence, uncertainty, or the
                safest next action without upgrading a status claim.
              </p>
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  `Explain the current state of ${discoverTitle}`,
                  `What remains unverified for ${discoverTitle}?`,
                  `What is the safest next action for ${discoverTitle}?`,
                ].map((p) => (
                  <button key={p} type="button" className="rd-v2-chip clickable" disabled={busy} onClick={() => send(p)}>
                    {String(p).slice(0, 42)}
                  </button>
                ))}
              </div>
            </div>
          ) : isDiscover && discoverTitle ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                Selected candidate stays in context. Ask about usability, risks, lab overlap, or what to probe next —
                without inventing clearance or completeness.
              </p>
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  `Assess this source: ${discoverTitle}`,
                  `What are the main risks of ${discoverTitle}?`,
                  `Compare ${discoverTitle} with my Library holdings`,
                  `What should I probe next for ${discoverTitle}?`,
                ].map((p) => (
                  <button
                    key={p}
                    type="button"
                    className="rd-v2-chip clickable"
                    disabled={busy}
                    onClick={() => send(p)}
                  >
                    {String(p).slice(0, 42)}
                  </button>
                ))}
              </div>
            </div>
          ) : isDiscover && openQuery ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                Ask is assisting this Explore. Ask what to collect next, what is already held, or how these routes
                fit the research question — without inventing holdings.
              </p>
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  "What should I collect next from this Explore?",
                  "What is already held for this query?",
                  "Which route is the strongest first pull?",
                ].map((p) => (
                  <button key={p} type="button" className="rd-v2-chip clickable" disabled={busy} onClick={() => send(p)}>
                    {String(p).slice(0, 42)}
                  </button>
                ))}
              </div>
            </div>
          ) : isLibrary && (dataset?.dataset_id || dataset?.title) ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                Ask is assisting this Library asset. Ask about readiness, joins, coverage limits, or how it fits
                Synthesis — without inventing query-ready status.
              </p>
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  "Can I query this now?",
                  "What joins or grain should I watch?",
                  "How would this feed a Synthesis construct?",
                ].map((p) => (
                  <button key={p} type="button" className="rd-v2-chip clickable" disabled={busy} onClick={() => send(p)}>
                    {String(p).slice(0, 42)}
                  </button>
                ))}
              </div>
            </div>
          ) : isSynthesis ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                Ask is assisting this Synthesis thread. Challenge the interpretation, map held evidence to roles,
                compare proxies, or ask how a proposal changes the durable method.
              </p>
              {openProposal ? (
                <AskAgentCard
                  message={{
                    role: "assistant",
                    text:
                      String(openProposal.summary || "").trim() ||
                      "A reviewable Synthesis proposal is attached to this thread. Accept or reject it before execution.",
                    synthesisProposal: openProposal,
                    synthesisThreadId: openProposalThreadId,
                  }}
                  busy={busy}
                  proposalState={proposalState}
                  onDecideProposal={decideProposal}
                  onRequestExecution={requestExecution}
                />
              ) : workspace?.output_ready && openProposalThreadId ? (
                <AskAgentCard
                  message={{
                    role: "assistant",
                    text: workspace.query_ready
                      ? "This construct is already query-ready in Library. Ask about reuse, method limits, or a revision — do not re-request execution for the same output."
                      : "This construct is already registered in Library. Ask about reuse or a revision — do not re-request execution unless proposing a new method.",
                    synthesisThreadId: openProposalThreadId,
                    nextSteps: [
                      {
                        label: "How should I reuse this output?",
                        prompt:
                          "Explain how to reuse the current Synthesis output from Library, including grain, readiness, and any method limits that still apply.",
                      },
                      {
                        label: "What would a revision change?",
                        prompt:
                          "If we revised this construct, what would change in the method or evidence map, and what would stay durable?",
                      },
                    ],
                  }}
                  busy={busy}
                  onSend={send}
                />
              ) : workspace?.can_request_execution && openProposalThreadId ? (
                <AskAgentCard
                  message={{
                    role: "assistant",
                    text: "This thread has a bounded execution_spec. Request execution to queue a pending desk approval job.",
                    synthesisThreadId: openProposalThreadId,
                    allowRequestExecution: true,
                  }}
                  busy={busy}
                  proposalState={proposalState}
                  onRequestExecution={requestExecution}
                />
              ) : workspace?.method_not_executable && openProposalThreadId ? (
                <AskAgentCard
                  message={{
                    role: "assistant",
                    text:
                      "Method accepted as documented construction. The registry executor runs bounded aggregates and row_output transforms (lag / diff / rolling). This thread still needs a concrete execution_spec before Request execution is offered.",
                    synthesisThreadId: openProposalThreadId,
                    methodNotExecutable: true,
                    nextSteps: [
                      {
                        label: "Ask for a bounded execution_spec if one is defensible",
                        prompt:
                          "If a bounded execution_spec is defensible from held evidence, propose one with input_dataset_id, output_dataset_id, and either metrics or row_output transforms (lag/diff/rolling). Otherwise explain why this method should remain construction-only.",
                      },
                      {
                        label: "Challenge the accepted method",
                        prompt:
                          "Challenge the accepted method: what remains ambiguous, and what would change the durable construction notes?",
                      },
                    ],
                  }}
                  busy={busy}
                  onSend={send}
                />
              ) : null}
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  "Interpret the construct and name the highest-value ambiguity",
                  "Map the strongest Library evidence to roles",
                  "Compare defensible proxy definitions",
                ].map((p) => (
                  <button
                    key={p}
                    type="button"
                    className="rd-v2-chip clickable"
                    disabled={busy}
                    onClick={() => send(p)}
                  >
                    {String(p).slice(0, 42)}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <GuidedState
              className="rd-v2-ask-guided-empty"
              eyebrow="Grounded assistant"
              title="Ask from an active research context"
              detail="Research Drive can search holdings, inspect evidence, propose collection, and explain what remains uncertain."
              checks={[
                "Visible context stays attached to the conversation",
                "Material collection still requires the appropriate approval path",
                "Readiness claims remain evidence-bound",
              ]}
            />
          )
        ) : (
          <>
            {isDiscoverHistory ? (
              <p className="rd-v2-ask-context-notice" data-testid="ask-context-notice">
                New messages use this lifecycle context.
              </p>
            ) : isDiscover && discoverTitle ? (
              <p className="rd-v2-ask-context-notice" data-testid="ask-context-notice">
                New messages use this source context.
              </p>
            ) : isDiscover && openQuery ? (
              <p className="rd-v2-ask-context-notice" data-testid="ask-context-notice">
                New messages assist this Discover Explore.
              </p>
            ) : isLibrary && (dataset?.dataset_id || dataset?.title) ? (
              <p className="rd-v2-ask-context-notice" data-testid="ask-context-notice">
                New messages assist this Library asset.
              </p>
            ) : isSynthesis ? (
              <p className="rd-v2-ask-context-notice" data-testid="ask-context-notice">
                New messages use this Synthesis thread and its current accepted state.
              </p>
            ) : null}
            {isSynthesis &&
            openProposalThreadId &&
            (openProposal ||
              workspace?.output_ready ||
              workspace?.can_request_execution ||
              workspace?.method_not_executable) ? (
              <AskAgentCard
                message={{
                  role: "assistant",
                  text: openProposal
                    ? String(openProposal.summary || "").trim() ||
                      "A reviewable Synthesis proposal is attached to this thread."
                    : workspace?.output_ready
                      ? workspace.query_ready
                        ? "This construct is already query-ready in Library. Ask about reuse, method limits, or a revision — do not re-request execution for the same output."
                        : "This construct is already registered in Library. Ask about reuse or a revision — do not re-request execution unless proposing a new method."
                      : workspace?.can_request_execution
                        ? "This thread has a bounded execution_spec. Request execution to queue a pending desk approval job."
                        : "Method accepted as documented construction. The registry executor runs bounded aggregates and row_output lag/diff/rolling — this thread still needs a concrete execution_spec.",
                  synthesisProposal: openProposal || undefined,
                  synthesisThreadId: openProposalThreadId,
                  allowRequestExecution: Boolean(!openProposal && workspace?.can_request_execution),
                  methodNotExecutable: Boolean(!openProposal && workspace?.method_not_executable),
                  nextSteps: workspace?.output_ready
                    ? [
                        {
                          label: "How should I reuse this output?",
                          prompt:
                            "Explain how to reuse the current Synthesis output from Library, including grain, readiness, and any method limits that still apply.",
                        },
                        {
                          label: "What would a revision change?",
                          prompt:
                            "If we revised this construct, what would change in the method or evidence map, and what would stay durable?",
                        },
                      ]
                    : workspace?.method_not_executable
                      ? [
                          {
                            label: "Ask for a bounded execution_spec if one is defensible",
                            prompt:
                              "If a bounded execution_spec is defensible from held evidence, propose one with input_dataset_id, output_dataset_id, and either metrics or row_output transforms (lag/diff/rolling). Otherwise explain why this method should remain construction-only.",
                          },
                        ]
                      : undefined,
                }}
                busy={busy}
                proposalState={proposalState}
                onDecideProposal={decideProposal}
                onRequestExecution={requestExecution}
                onSend={send}
              />
            ) : null}
            {messages.map((m, i) => {
              if (m.streaming && !m.text && !m.deskFacts && !m.pendingJobId && !m.synthesisProposal) {
                return (
                  <AskAgentCard
                    key={`assistant-stream-${i}`}
                    message={m}
                    busy={busy}
                  />
                );
              }
              const approval = m.pendingJobId ? approvalState[m.pendingJobId]?.status : "";
              if (m.role === "assistant" || m.streaming) {
                return (
                  <AskAgentCard
                    key={`assistant-${i}`}
                    message={m}
                    busy={busy}
                    approval={approval}
                    proposalState={proposalState}
                    onSend={send}
                    onApprove={requestApproval}
                    onDecideProposal={decideProposal}
                    onRequestExecution={requestExecution}
                  />
                );
              }
              return (
                <div
                  key={`${m.role}-${i}`}
                  className={`rd-v2-ask-bubble${m.role === "error" ? " error" : ""}${m.role === "notice" ? " notice" : ""}`}
                >
                  <span className="rd-v2-ask-bubble-role">
                    {m.role === "error" ? "Error" : m.role === "notice" ? "Read-only review" : "You"}
                  </span>
                  <div className="rd-v2-ask-bubble-text">{formatAskText(m.text)}</div>
                </div>
              );
            })}
          </>
        )}
      </div>
      <ProgressSteps active={busy} activeText={status} label="Research assistant progress" />
      {!busy && status ? <p className="rd-v2-ask-status">{status}</p> : null}
      <div className="rd-v2-ask-input">
        <textarea
          ref={textareaRef}
          value={input}
          rows={3}
          placeholder={
            isProfile
              ? "Correct the research memory or ask how it is used…"
              : isSettings
                ? "Ask about desk behavior, access, or approvals…"
              : isSynthesis
                ? "Correct the interpretation, add a constraint, or ask…"
                : isDiscoverHistory
                  ? "Ask about this lifecycle record…"
                  : "Ask about coverage, overlaps, or procurement…"
          }
          disabled={busy}
          data-testid="ask-composer"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            handleEnterToSubmit(e, () => {
              if (!busy && input.trim()) send();
            });
          }}
        />
        <div className="rd-v2-ask-send-row">
          <span className="rd-v2-ask-send-hint">Enter to send · ⇧↵ newline</span>
          <button
            type="button"
            className="rd-v2-btn sm primary"
            disabled={busy || !input.trim()}
            aria-busy={busy}
            onClick={() => send()}
          >
            {busy ? <><LoaderCircle className="rd-v2-inline-spinner" aria-hidden="true" /> Working…</> : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
