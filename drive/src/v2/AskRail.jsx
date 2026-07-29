import { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { GuidedState, ProgressSteps } from "@/v2/InteractionFeedback";
import { useAskChat } from "@/v2/useAskChat";
import { handleEnterToSubmit } from "@/v2/enterToSubmit";
import { formatAskText } from "@/v2/askText.jsx";
import { AskAgentCard } from "@/v2/AskAgentCard.jsx";
import { displayName } from "@/v2/datasetMeta";

export function AskRail({
  dataset,
  mainTab,
  searchQuery,
  pendingMessage,
  onPendingConsumed,
  onCollected,
  onApproveJob,
  onToast,
  railContext,
}) {
  const { messages, input, setInput, busy, status, send, contextLabel } = useAskChat({
    dataset,
    railContext,
    onCollected,
    onToast,
  });
  const pendingSentRef = useRef("");
  const textareaRef = useRef(null);
  const [approvalState, setApprovalState] = useState({});

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

  const ctxParts = [contextLabel, mainTab, searchQuery ? `search: ${searchQuery}` : ""].filter(Boolean);
  const isProfile = mainTab === "profile";
  const isSettings = mainTab === "settings";
  const isDiscover = mainTab === "browse";
  const isDiscoverHistory = isDiscover && dataset?.kind === "discover_history";
  const isDiscoverInvestigation = isDiscover && dataset?.kind === "discover_investigation";
  const isSynthesis = mainTab === "synthesis";
  const profileContext = dataset?.title || "Profile";
  const synthesisContext =
    dataset?.title && dataset.title !== "Synthesis studio"
      ? dataset.title
      : "Synthesis studio";
  const hasThread = messages.length > 0;
  const discoverTitle = dataset?.title || dataset?.dataset_id || "";
  const railTitle = isProfile
    ? "Ask"
    : isSettings
      ? "Ask · desk setup"
    : isDiscoverHistory
      ? "Ask · lifecycle item"
      : isDiscoverInvestigation
        ? "Ask · investigation"
      : isDiscover
        ? "Ask · selected source"
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
        ? `Selected context · ${discoverTitle}`
        : isDiscover && discoverTitle
          ? `Evaluating · ${discoverTitle}`
          : isSynthesis
            ? hasThread
              ? `Continuing · thread → ${synthesisContext}`
              : `Thread context · ${synthesisContext}`
            : ctxParts.length
              ? ctxParts.join(" · ")
              : "Select a dataset for grounded answers";

  const askEntityTitle =
    (dataset?.dataset_id || dataset?.title
      ? displayName(dataset) || dataset?.title || dataset?.dataset_id
      : "") ||
    (isProfile ? profileContext : isSynthesis ? synthesisContext : "");

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
                  `Compare ${discoverTitle} with my lab holdings`,
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
          ) : isSynthesis ? (
            <div className="rd-v2-ask-placeholder">
              <p>
                This conversation shares the active Synthesis thread. Challenge the interpretation, add a constraint,
                compare constructions, or ask how a proposal changes the durable method.
              </p>
              <div className="rd-v2-chips-row rd-v2-ask-chips">
                {[
                  "Explain the current construction.",
                  "Challenge the main assumption.",
                  "Compare the alternatives.",
                ].map((p) => (
                  <button
                    key={p}
                    type="button"
                    className="rd-v2-chip clickable"
                    disabled={busy}
                    onClick={() => send(p)}
                  >
                    {p}
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
            ) : isSynthesis ? (
              <p className="rd-v2-ask-context-notice" data-testid="ask-context-notice">
                New messages use this Synthesis thread and its current accepted state.
              </p>
            ) : null}
            {messages.map((m, i) => {
              if (m.streaming && !m.text) {
                return (
                  <AskAgentCard
                    key={`assistant-stream-${i}`}
                    message={m}
                    busy={busy}
                  />
                );
              }
              const approval = m.pendingJobId ? approvalState[m.pendingJobId]?.status : "";
              if (m.role === "assistant") {
                return (
                  <AskAgentCard
                    key={`assistant-${i}`}
                    message={m}
                    busy={busy}
                    approval={approval}
                    onSend={send}
                    onApprove={requestApproval}
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
