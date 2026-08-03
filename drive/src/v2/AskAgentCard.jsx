import { LoaderCircle } from "lucide-react";
import {
  formatAskText,
  humanizeAction,
  parseAskReply,
  readinessLabel,
  readinessTone,
} from "@/v2/askText.jsx";

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

export function AskAgentCard({
  message,
  busy = false,
  approval = "",
  onSend,
  onApprove,
}) {
  const streaming = Boolean(message?.streaming);
  const parsed = parseAskReply(message?.text || "");
  const readiness = readinessLabel(parsed.readiness);
  const tone = readinessTone(parsed.readiness);
  const action = humanizeAction(message?.action);
  const steps = Array.isArray(message?.nextSteps) && message.nextSteps.length
    ? message.nextSteps
    : (message?.suggestedPrompts || []).map((prompt) => ({ label: prompt, prompt }));

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
        {streaming && !message?.text ? (
          <p className="rd-v2-ask-card-pending">Gathering grounded context…</p>
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

      {message?.pendingJobId && message?.jobStatus === "pending_approval" ? (
        <div className="rd-v2-ask-card-actions">
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
              "Approve job"
            )}
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
