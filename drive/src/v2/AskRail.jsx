import { useCallback, useEffect, useMemo, useRef } from "react";
import { approveDatasetLicense, decideSynthesisProposal } from "@/v2/api";
import { useAskChat } from "@/v2/useAskChat";
import { AskMessageArtifacts } from "@/v2/AskMessageArtifacts";
import { isTerminalJobStatus } from "@/v2/askArtifacts";
import { useJobsPoll } from "@/v2/useJobsPoll";

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
  chatSessionId = "",
  persistSession = true,
  onChatComplete,
  onSynthesisThreadRefresh,
}) {
  const isSynthesis = mainTab === "synthesis";
  const synthesisThreadId = isSynthesis ? railContext?.thread_id || "" : "";
  const synthesisProposal = isSynthesis ? railContext?.entity?.proposal || null : null;
  const boundSessionId = isSynthesis ? chatSessionId || railContext?.session_id || "" : "";

  const { messages, input, setInput, busy, status, send, patchMessageJob, contextLabel } = useAskChat({
    dataset,
    railContext,
    chatSessionId: boundSessionId,
    persistSession: isSynthesis ? false : persistSession,
    onCollected,
    onToast,
    onChatComplete: (out) => {
      onChatComplete?.(out);
      if (
        isSynthesis &&
        synthesisThreadId &&
        (out?.artifacts?.synthesis_proposal ||
          out?.synthesis_proposal ||
          out?.artifacts?.synthesis_thread_id ||
          out?.action === "composer" ||
          out?.action === "composer_pending")
      ) {
        onSynthesisThreadRefresh?.();
      }
    },
  });
  const pendingSentRef = useRef("");
  const textareaRef = useRef(null);
  const decisionBusyRef = useRef(false);

  const pendingJobs = useMemo(() => {
    const seen = new Set();
    const rows = [];
    for (const m of messages) {
      if (m.role !== "assistant" || !m.pendingJobId || isTerminalJobStatus(m.jobStatus)) continue;
      if (seen.has(m.pendingJobId)) continue;
      seen.add(m.pendingJobId);
      rows.push({ id: m.pendingJobId, status: m.jobStatus });
    }
    return rows;
  }, [messages]);

  useJobsPoll(pendingJobs, (jobId, nextStatus) => patchMessageJob(jobId, nextStatus), {
    enabled: pendingJobs.length > 0,
  });

  const handleApproveJob = useCallback(
    async (jobId) => {
      if (!jobId) return;
      patchMessageJob(jobId, "queued");
      await onApproveJob?.(jobId);
    },
    [onApproveJob, patchMessageJob],
  );

  const handleApproveLicense = useCallback(
    async (doi) => {
      if (!doi) return;
      try {
        await approveDatasetLicense({ doi });
        onToast?.(`License approved for ${doi} — retry collect`);
      } catch (err) {
        onToast?.(err.message || "License approve failed", "error");
      }
    },
    [onToast],
  );

  const handleProposalDecision = useCallback(
    async (decision) => {
      if (!synthesisThreadId || !synthesisProposal?.id) return;
      const proposalHash = synthesisProposal.proposalHash || synthesisProposal.proposal_hash;
      if (!proposalHash) return;
      if (decisionBusyRef.current) return;
      decisionBusyRef.current = true;
      try {
        await decideSynthesisProposal(synthesisThreadId, {
          decision,
          proposalId: synthesisProposal.id,
          proposalHash,
        });
        onToast?.(decision === "accept" ? "Proposal accepted" : "Proposal rejected");
        onSynthesisThreadRefresh?.();
      } catch (err) {
        onToast?.(err.message || "Proposal decision failed", "error");
      } finally {
        decisionBusyRef.current = false;
      }
    },
    [synthesisThreadId, synthesisProposal, onToast, onSynthesisThreadRefresh],
  );

  useEffect(() => {
    if (!pendingMessage || busy) return;
    if (pendingSentRef.current === pendingMessage) return;
    pendingSentRef.current = pendingMessage;
    send(pendingMessage).finally(() => {
      pendingSentRef.current = "";
      onPendingConsumed?.();
    });
  }, [pendingMessage, busy, send, onPendingConsumed]);

  const ctxParts = [contextLabel, mainTab, searchQuery ? `search: ${searchQuery}` : ""].filter(Boolean);
  const isProfile = mainTab === "profile";
  const hasThread = messages.length > 0;
  const headLabel = isSynthesis ? "Composer" : "Ask";
  const placeholder = isSynthesis
    ? "Describe the research measure or revise the construction…"
    : isProfile
      ? "Message…"
      : "Ask about coverage, overlaps, or procurement…";
  const synthesisDraft = Boolean(railContext?.entity?.draft);
  const synthesisCtx = synthesisThreadId
    ? hasThread
      ? `Thread ${synthesisThreadId} · ${dataset?.title || "Synthesis"}`
      : `Thread ${synthesisThreadId} — proposals update Model and Spec.`
    : synthesisDraft
      ? "Local draft — thread API unavailable. Proposals cannot persist."
      : "Record the research measure — proposals update Model and Spec.";
  const objectCtx = isSynthesis
    ? synthesisCtx
    : isProfile
      ? hasThread
        ? `Continuing · context → ${dataset?.title || "Profile"}`
        : `Context · ${dataset?.title || "Profile"}`
      : ctxParts.length
        ? ctxParts.join(" · ")
        : "Select an object for grounded answers";

  const suggestedPrompts = isSynthesis
    ? synthesisDraft
      ? [
          "What research measure should we construct?",
          "Which Lab holdings should supply the inputs?",
          "Propose a join method for this draft.",
        ]
      : [
          "Tighten inputs, grain, or join method.",
          "What evidence is still missing?",
          "What would count as accepted output?",
        ]
    : !hasThread && dataset?.title
      ? [
          `What coverage does ${dataset.title} give me?`,
          "What is still unknown before I rely on this?",
          "What is the safest next action?",
        ]
      : !hasThread && mainTab === "browse"
        ? [
            "How does this candidate fit the lab?",
            "What should I probe before collecting?",
            "What remains unknown?",
          ]
        : [];

  return (
    <div
      className={`rd-v2-ask-shell rd-v2-ask-shell--quiet${isSynthesis ? " rd-v2-ask-shell--composer" : ""}`}
    >
      <header className="rd-v2-ask-head">
        <strong>{headLabel}</strong>
        <p className="rd-v2-ask-ctx" data-testid={isSynthesis ? "synthesis-composer-context" : "ask-object-context"}>
          {objectCtx}
        </p>
      </header>
      {isSynthesis && synthesisProposal?.title ? (
        <div className="rd-v2-composer-proposal-card" data-testid="synthesis-composer-proposal">
          <strong>{synthesisProposal.title}</strong>
          {synthesisProposal.summary ? <p>{synthesisProposal.summary}</p> : null}
          <div className="rd-v2-chips-row">
            <button
              type="button"
              className="rd-v2-btn sm primary"
              data-testid="synthesis-composer-accept"
              disabled={busy}
              onClick={() => handleProposalDecision("accept")}
            >
              Accept
            </button>
            <button
              type="button"
              className="rd-v2-btn sm"
              data-testid="synthesis-composer-reject"
              disabled={busy}
              onClick={() => handleProposalDecision("reject")}
            >
              Reject
            </button>
          </div>
        </div>
      ) : null}
      <div className="rd-v2-ask-messages" data-testid="ask-messages">
        {messages.length === 0 ? (
          <div
            className="rd-v2-ask-placeholder rd-v2-ask-placeholder-quiet"
            data-testid={isSynthesis ? "synthesis-composer-empty" : "ask-empty"}
            aria-hidden="true"
          />
        ) : (
          messages.map((m, i) => (
            <div
              key={`${m.role}-${i}`}
              className={`rd-v2-ask-bubble${m.role === "assistant" ? " agent" : ""}${m.role === "error" ? " error" : ""}`}
              data-testid={m.role === "user" ? "synthesis-composer-user" : m.role === "assistant" ? "synthesis-composer-assistant" : undefined}
            >
              {m.role === "user" ? (
                <>
                  <strong>You:</strong> {m.text}
                </>
              ) : m.role === "error" ? (
                m.text
              ) : (
                <>
                  {m.activity ? <p className="muted small">{m.activity}</p> : null}
                  <strong>Agent:</strong> {m.text || (m.streaming ? "…" : "")}
                  {!m.streaming ? (
                    <AskMessageArtifacts
                      message={m}
                      onApproveJob={handleApproveJob}
                      onApproveLicense={handleApproveLicense}
                      busy={busy}
                    />
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
          ))
        )}
      </div>
      {!hasThread && suggestedPrompts.length ? (
        <div
          className="rd-v2-chips-row rd-v2-ask-affordances"
          data-testid={isSynthesis ? "synthesis-composer-affordances" : "ask-affordances"}
        >
          {suggestedPrompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="rd-v2-chip clickable"
              disabled={busy}
              onClick={() => send(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
      ) : null}
      {status && !isSynthesis ? <p className="rd-v2-ask-status">{status}</p> : null}
      {status && isSynthesis ? (
        <p className="rd-v2-ask-status rd-v2-ask-status--composer" data-testid="synthesis-composer-status">
          {status}
        </p>
      ) : null}
      <div className={`rd-v2-ask-input${isSynthesis ? " rd-v2-ask-input--composer" : ""}`}>
        <textarea
          ref={textareaRef}
          value={input}
          rows={isSynthesis ? 4 : 3}
          placeholder={placeholder}
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
