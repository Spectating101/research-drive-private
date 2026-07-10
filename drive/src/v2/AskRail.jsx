import { useCallback, useEffect, useMemo, useRef } from "react";
import { approveDatasetLicense } from "@/v2/api";
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
}) {
  const { messages, input, setInput, busy, status, send, patchMessageJob, contextLabel } = useAskChat({
    dataset,
    railContext,
    onCollected,
    onToast,
  });
  const pendingSentRef = useRef("");
  const textareaRef = useRef(null);

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
  const profileContext = dataset?.title || "Profile";
  const hasThread = messages.length > 0;

  return (
    <div className="rd-v2-ask-shell">
      <header className="rd-v2-ask-head">
        <strong>{isProfile ? "Ask" : "Procurement chat"}</strong>
        <p className="rd-v2-ask-ctx">
          {isProfile
            ? hasThread
              ? `Continuing · context → ${profileContext}`
              : `Context · ${profileContext}`
            : ctxParts.length
              ? ctxParts.join(" · ")
              : "Select a dataset for grounded answers"}
        </p>
      </header>
      <div className="rd-v2-ask-messages" data-testid="ask-messages">
        {messages.length === 0 ? (
          isProfile ? (
            <p className="rd-v2-ask-placeholder rd-v2-ask-placeholder-quiet" />
          ) : (
            <p className="rd-v2-ask-placeholder">
              Ask about vault holdings, Hugging Face or DOI imports, overlaps, or what to procure next — the assistant
              searches, queries, collects, and archives via the research tools.
            </p>
          )
        ) : (
          messages.map((m, i) => (
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
      {status ? <p className="rd-v2-ask-status">{status}</p> : null}
      <div className="rd-v2-ask-input">
        <textarea
          ref={textareaRef}
          value={input}
          rows={3}
          placeholder={isProfile ? "Message…" : "Ask about coverage, overlaps, or procurement…"}
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
