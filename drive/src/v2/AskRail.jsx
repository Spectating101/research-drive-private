import { useEffect, useRef } from "react";
import { useAskChat } from "@/v2/useAskChat";

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

  const ctxParts = [contextLabel, mainTab, searchQuery ? `search: ${searchQuery}` : ""].filter(Boolean);
  const isProfile = mainTab === "profile";
  const isDiscover = mainTab === "browse";
  const isDiscoverHistory = isDiscover && dataset?.kind === "discover_history";
  const isSynthesis = mainTab === "synthesis";
  const profileContext = dataset?.title || "Profile";
  const synthesisContext =
    dataset?.title && dataset.title !== "Synthesis studio"
      ? dataset.title
      : "Historical stablecoin attention";
  const hasThread = messages.length > 0;
  const discoverTitle = dataset?.title || dataset?.dataset_id || "";
  const railTitle = isProfile
    ? "Ask"
    : isDiscoverHistory
      ? "Ask · lifecycle item"
    : isDiscover
      ? "Ask · selected source"
      : isSynthesis
        ? "Ask · synthesis thread"
        : "Procurement chat";
  const railSubtitle = isProfile
    ? hasThread
      ? `Continuing · context → ${profileContext}`
      : `Context · ${profileContext}`
    : isDiscoverHistory && discoverTitle
      ? `Lifecycle context · ${discoverTitle}`
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

  return (
    <div className="rd-v2-ask-shell">
      <header className="rd-v2-ask-head">
        <strong>{railTitle}</strong>
        <p className="rd-v2-ask-ctx">{railSubtitle}</p>
      </header>
      <div className="rd-v2-ask-messages" data-testid="ask-messages">
        {messages.length === 0 ? (
          isProfile ? (
            <p className="rd-v2-ask-placeholder rd-v2-ask-placeholder-quiet" />
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
            <p className="rd-v2-ask-placeholder">
              Ask about vault holdings, Hugging Face or DOI imports, overlaps, or what to procure next — the assistant
              searches, queries, collects, and archives via the research tools.
            </p>
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
            {messages.map((m, i) => (
              <div
                key={`${m.role}-${i}`}
                className={`rd-v2-ask-bubble${m.role === "assistant" ? " agent" : ""}${m.role === "error" ? " error" : ""}`}
              >
                {m.role === "user" ? (
                  <>
                    <strong>You:</strong> {m.text}
                  </>
                ) : m.role === "error" ? (
                  m.text
                ) : (
                  <>
                    {m.activityLog?.length ? (
                      <ol className="rd-v2-ask-phases" data-testid="ask-tool-phases" aria-label="Agent tool activity">
                        {m.activityLog.map((step, si) => (
                          <li key={`${step.phase}-${si}`} data-phase={step.phase}>
                            <span className="rd-v2-ask-phase-label">{step.phase}</span>
                            <span className="rd-v2-ask-phase-text">{step.text}</span>
                          </li>
                        ))}
                      </ol>
                    ) : m.activity ? (
                      <p className="muted small">{m.activity}</p>
                    ) : null}
                    <strong>Agent:</strong> {m.text || (m.streaming ? "…" : "")}
                    {m.action || m.toolName ? (
                      <p className="rd-v2-ask-action-meta muted small">
                        {[m.toolName, m.action].filter(Boolean).join(" · ")}
                      </p>
                    ) : null}
                    {m.pendingJobId && m.jobStatus === "pending_approval" ? (
                      <div className="rd-v2-ask-actions">
                        <button
                          type="button"
                          className="rd-v2-btn sm primary"
                          disabled={busy}
                          onClick={() => onApproveJob?.(m.pendingJobId)}
                        >
                          Approve job
                        </button>
                      </div>
                    ) : null}
                    {m.suggestedPrompts?.length ? (
                      <div className="rd-v2-chips-row rd-v2-ask-chips">
                        {m.suggestedPrompts.slice(0, 3).map((p) => (
                          <button
                            key={p}
                            type="button"
                            className="rd-v2-chip clickable"
                            disabled={busy}
                            onClick={() => send(p)}
                          >
                            {String(p).slice(0, 40)}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            ))}
          </>
        )}
      </div>
      {status ? <p className="rd-v2-ask-status">{status}</p> : null}
      <div className="rd-v2-ask-input">
        <textarea
          ref={textareaRef}
          value={input}
          rows={3}
          placeholder={
            isProfile
              ? "Message…"
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
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              send();
            }
          }}
        />
        <div className="rd-v2-ask-send-row">
          <span className="rd-v2-ask-send-hint">⌘↵ to send</span>
          <button
            type="button"
            className="rd-v2-btn sm primary"
            disabled={busy || !input.trim()}
            onClick={() => send()}
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
