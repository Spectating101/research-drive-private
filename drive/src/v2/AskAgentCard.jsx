import { LoaderCircle } from "lucide-react";
import {
  formatAskText,
  humanizeAction,
  parseAskReply,
  readinessLabel,
  readinessTone,
} from "@/v2/askText.jsx";
import { statusPillKind } from "@/v2/datasetMeta";

function nextStepLabel(step) {
  if (!step) return "";
  if (typeof step === "string") return step;
  return String(step.label || step.prompt || "").trim();
}

function nextStepPrompt(step) {
  if (!step) return "";
  if (typeof step === "string") return step;
  return String(step.prompt || step.label || "").trim();
}

function heldMetaBits(row) {
  const bits = [];
  const readiness = String(row?.analysis_readiness || row?.readiness || "").trim();
  if (readiness) {
    const pill = statusPillKind({ analysis_readiness: readiness });
    bits.push(pill?.label || readiness.replace(/_/g, " "));
  }
  if (row?.grain) bits.push(`grain ${row.grain}`);
  if (row?.coverage) bits.push(String(row.coverage).slice(0, 48));
  if (row?.local_ready) bits.push("local ready");
  return bits;
}

export function AskAgentCard({
  message,
  busy = false,
  approval = "",
  proposalState = "",
  onSend,
  onApprove,
  onDecideProposal,
  onRequestExecution,
}) {
  const streaming = Boolean(message?.streaming);
  const parsed = parseAskReply(message?.text || "");
  const readiness = readinessLabel(parsed.readiness);
  const tone = readinessTone(parsed.readiness);
  const action = humanizeAction(message?.action);
  const steps = Array.isArray(message?.nextSteps) && message.nextSteps.length
    ? message.nextSteps
    : (message?.suggestedPrompts || []).map((prompt) => ({ label: prompt, prompt }));
  const proposal =
    message?.synthesisProposal && typeof message.synthesisProposal === "object"
      ? message.synthesisProposal
      : null;
  const proposalTitle = String(proposal?.title || proposal?.summary || "").trim();
  const secondaryQuery = String(message?.deskFacts?.secondary_query || "").trim();
  const allowRequestExecution = Boolean(
    proposal || message?.allowRequestExecution || message?.canRequestExecution,
  );
  const methodNotExecutable = Boolean(message?.methodNotExecutable);
  const synthesisThreadId = String(message?.synthesisThreadId || "").trim();

  return (
    <article
      className={`rd-v2-ask-card${streaming ? " is-streaming" : ""}`}
      data-testid="ask-agent-card"
      aria-busy={streaming || undefined}
    >
      <header className="rd-v2-ask-card-head">
        <div className="rd-v2-ask-card-kicker">
          <span className="rd-v2-ask-card-eyebrow">
            {streaming ? "Working" : "Grounded answer"}
          </span>
          {readiness ? (
            <span className={`rd-v2-ask-card-pill rd-v2-ask-card-pill-${tone}`}>
              <span className="rd-v2-status-dot" aria-hidden="true" />
              {readiness}
            </span>
          ) : null}
        </div>
        {parsed.title ? <h3 className="rd-v2-ask-card-title">{parsed.title}</h3> : null}
        {parsed.datasetId ? (
          <p className="rd-v2-ask-card-id">
            <code>{parsed.datasetId}</code>
          </p>
        ) : null}
      </header>

      <div className="rd-v2-ask-card-body">
        {message?.deskFacts ? (
          <div className="rd-v2-ask-desk-facts" data-testid="ask-desk-facts">
            <p className="rd-v2-ask-desk-facts-label">Desk measure</p>
            {message.deskFacts.query ? (
              <p className="rd-v2-ask-desk-facts-query">
                Primary · {message.deskFacts.query}
              </p>
            ) : null}
            {secondaryQuery ? (
              <p className="rd-v2-ask-desk-facts-query" data-testid="ask-desk-facts-secondary">
                Also measured · {secondaryQuery}
              </p>
            ) : null}
            {Array.isArray(message.deskFacts.held) && message.deskFacts.held.length ? (
              <ul className="rd-v2-ask-desk-facts-list">
                {message.deskFacts.held.map((row, i) => {
                  const meta = heldMetaBits(row);
                  return (
                    <li key={`held-${row.dataset_id || i}`}>
                      <span className="rd-v2-ask-desk-facts-kind">held</span>
                      {row.title || row.dataset_id}
                      {row.dataset_id ? <code>{row.dataset_id}</code> : null}
                      {meta.length ? (
                        <span className="rd-v2-ask-desk-facts-meta">{meta.join(" · ")}</span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="rd-v2-ask-desk-facts-empty">No Library holdings measured.</p>
            )}
            {Array.isArray(message.deskFacts.routes) && message.deskFacts.routes.length ? (
              <ul className="rd-v2-ask-desk-facts-list">
                {message.deskFacts.routes.map((row, i) => (
                  <li key={`route-${row.source_id || i}`}>
                    <span className="rd-v2-ask-desk-facts-kind">route</span>
                    {row.title || row.source_id}
                    {row.source_id ? <code>{row.source_id}</code> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {message?.composerPending || message?.backgroundWatch || message?.action === "composer_pending" ? (
          <p className="rd-v2-ask-card-pending" data-testid="ask-composer-pending">
            Composer may still be finishing this turn in the background. This card will update when it lands.
          </p>
        ) : null}
        {streaming && !message?.text ? (
          <p className="rd-v2-ask-card-pending">
            {message?.deskFacts ? "Composer drafting…" : "Gathering grounded context…"}
          </p>
        ) : null}
        {parsed.paragraphs.map((para, i) => (
          <p key={`p-${i}`} className="rd-v2-ask-card-para">
            {formatAskText(para)}
          </p>
        ))}
        {parsed.bullets.length ? (
          <ul className="rd-v2-ask-card-bullets">
            {parsed.bullets.map((item, i) => (
              <li key={`b-${i}`}>{formatAskText(item)}</li>
            ))}
          </ul>
        ) : null}
        {!parsed.title && !parsed.paragraphs.length && message?.text ? (
          <div className="rd-v2-ask-card-para">{formatAskText(message.text)}</div>
        ) : null}
      </div>

      {message?.pendingJobId &&
      (message?.jobStatus === "pending_approval" || String(message?.jobStatus || "").includes("pending")) ? (
        <div className="rd-v2-ask-card-actions" data-testid="ask-job-approve">
          <button
            type="button"
            className="rd-v2-btn sm primary"
            disabled={busy || approval === "working"}
            aria-busy={approval === "working"}
            onClick={() => onApprove?.(message.pendingJobId)}
          >
            {approval === "working" ? (
              <>
                <LoaderCircle className="rd-v2-inline-spinner" aria-hidden="true" /> Approving…
              </>
            ) : (
              "Approve collection job"
            )}
          </button>
        </div>
      ) : null}

      {methodNotExecutable && !allowRequestExecution ? (
        <div className="rd-v2-ask-card-actions" data-testid="ask-synthesis-method-note">
          <p className="rd-v2-ask-desk-facts-label">Accepted method · not registry-executable yet</p>
        </div>
      ) : null}

      {allowRequestExecution && synthesisThreadId ? (
        <div className="rd-v2-ask-card-actions" data-testid="ask-synthesis-proposal">
          <p className="rd-v2-ask-desk-facts-label">
            {proposal
              ? `Synthesis proposal${proposalTitle ? ` · ${proposalTitle.slice(0, 72)}` : ""}`
              : "Accepted method — request execution when ready"}
          </p>
          {proposal ? (
            <>
              <button
                type="button"
                className="rd-v2-btn sm primary"
                disabled={busy || proposalState === "working"}
                onClick={() =>
                  onDecideProposal?.({
                    decision: "accept",
                    threadId: synthesisThreadId,
                    proposal,
                  })
                }
              >
                Accept proposal
              </button>
              <button
                type="button"
                className="rd-v2-btn sm"
                disabled={busy || proposalState === "working"}
                onClick={() =>
                  onDecideProposal?.({
                    decision: "reject",
                    threadId: synthesisThreadId,
                    proposal,
                  })
                }
              >
                Reject
              </button>
            </>
          ) : null}
          <button
            type="button"
            className="rd-v2-btn sm primary"
            disabled={busy || proposalState === "working"}
            onClick={() => onRequestExecution?.(synthesisThreadId)}
          >
            Request execution
          </button>
        </div>
      ) : null}

      {!streaming && steps.length ? (
        <div className="rd-v2-ask-card-next" aria-label="Suggested next steps">
          <p className="rd-v2-ask-card-next-label">Next steps</p>
          <div className="rd-v2-ask-card-next-list">
            {steps.slice(0, 4).map((step, idx) => {
              const label = nextStepLabel(step);
              const prompt = nextStepPrompt(step);
              if (!label || !prompt) return null;
              return (
                <button
                  key={`${idx}-${prompt}`}
                  type="button"
                  className="rd-v2-ask-card-next-btn"
                  disabled={busy}
                  onClick={() => onSend?.(prompt)}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {!streaming && action ? (
        <footer className="rd-v2-ask-card-foot">
          <span>Evidence-bound</span>
          <span aria-hidden="true">·</span>
          <span>{action}</span>
        </footer>
      ) : null}
    </article>
  );
}
