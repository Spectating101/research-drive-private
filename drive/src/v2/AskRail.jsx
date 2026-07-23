import { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { GuidedState, ProgressSteps } from "@/v2/InteractionFeedback";
import { useAskChat } from "@/v2/useAskChat";
import { handleEnterToSubmit } from "@/v2/enterToSubmit";

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
      <div className="rd-v2-ask-messages" data-testid="ask-messages" aria-busy={busy}>
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
              if (m.streaming && !m.text) return null;
              const approval = m.pendingJobId ? approvalState[m.pendingJobId]?.status : "";
              return (
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
                      {!m.streaming && m.intent !== "status" && m.activityLog?.length ? (
                        <ol className="rd-v2-ask-phases" data-testid="ask-tool-phases" aria-label="Agent tool activity">
                          {m.activityLog
                            .filter((step) => !/describe[_ ]?dataset/i.test(`${step.phase || ""} ${step.text || ""}`))
                            .map((step, si) => (
                            <li key={`${step.phase}-${si}`} data-phase={step.phase}>
                              <span className="rd-v2-ask-phase-label">
                                {/^(planning|working)$/i.test(String(step.phase || ""))
                                  ? "Working"
                                  : step.phase}
                              </span>
                              <span className="rd-v2-ask-phase-text">{step.text}</span>
                            </li>
                          ))}
                        </ol>
                      ) : !m.streaming && m.intent !== "status" && m.activity ? (
                        <p className="muted small">{m.activity}</p>
                      ) : null}
                      <strong>Agent:</strong> {m.text}
                      {(() => {
                        if (m.intent === "status") return null;
                        const meta = [m.toolName, m.action]
                          .filter(Boolean)
                          .filter((part) => !/describe[_ ]?dataset|planning|working/i.test(String(part)));
                        if (!meta.length) return null;
                        return (
                          <p className="rd-v2-ask-action-meta muted small">{meta.join(" · ")}</p>
                        );
                      })()}
                      {m.intent !== "status" && m.pendingJobId && m.jobStatus === "pending_approval" ? (
                        <div className="rd-v2-ask-actions">
                          <button
                            type="button"
                            className="rd-v2-btn sm primary"
                            disabled={busy || approval === "working"}
                            aria-busy={approval === "working"}
                            onClick={() => requestApproval(m.pendingJobId)}
                          >
                            {approval === "working" ? (
                              <><LoaderCircle className="rd-v2-inline-spinner" aria-hidden="true" /> Approving…</>
                            ) : (
                              "Approve job"
                            )}
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
