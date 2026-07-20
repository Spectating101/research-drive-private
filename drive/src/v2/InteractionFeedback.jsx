import { useEffect, useMemo, useState } from "react";
import { Check, LoaderCircle } from "lucide-react";

const DEFAULT_ASK_STEPS = [
  "Preparing the active research context",
  "Searching lab holdings and connected evidence",
  "Checking provenance, readiness, and uncertainty",
  "Composing a grounded response",
];

export function useTimedProgress(active, steps = DEFAULT_ASK_STEPS, intervalMs = 1050) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setIndex(0);
      return undefined;
    }
    const timer = window.setInterval(() => {
      setIndex((current) => Math.min(current + 1, steps.length - 1));
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [active, intervalMs, steps.length]);

  return index;
}

export function ProgressSteps({
  active = false,
  activeText = "",
  steps = DEFAULT_ASK_STEPS,
  label = "Operation progress",
  className = "",
}) {
  const index = useTimedProgress(active, steps);
  const visibleSteps = useMemo(
    () => steps.map((text, stepIndex) => ({
      text: stepIndex === index && activeText ? activeText : text,
      state: stepIndex < index ? "done" : stepIndex === index ? "active" : "pending",
    })),
    [activeText, index, steps],
  );

  if (!active) return null;

  return (
    <section
      className={`rd-v2-progress-card${className ? ` ${className}` : ""}`}
      aria-label={label}
      aria-live="polite"
      data-testid="interaction-progress"
    >
      <div className="rd-v2-progress-card-head">
        <LoaderCircle aria-hidden="true" />
        <strong>{visibleSteps[index]?.text || "Working…"}</strong>
      </div>
      <ol>
        {visibleSteps.map((step, stepIndex) => (
          <li key={`${step.text}-${stepIndex}`} data-state={step.state}>
            <span className="rd-v2-progress-marker" aria-hidden="true">
              {step.state === "done" ? <Check /> : stepIndex + 1}
            </span>
            <span>{step.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Skeleton({ className = "", lines = 1, label = "Loading" }) {
  return (
    <div
      className={`rd-v2-skeleton${className ? ` ${className}` : ""}`}
      role="status"
      aria-label={label}
      data-testid="interaction-skeleton"
    >
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} className={index === lines - 1 ? "short" : ""} aria-hidden="true" />
      ))}
    </div>
  );
}

export function GuidedState({ eyebrow, title, detail, checks = [], actions, className = "" }) {
  return (
    <section className={`rd-v2-guided-state${className ? ` ${className}` : ""}`}>
      {eyebrow ? <p className="rd-v2-guided-state-eyebrow">{eyebrow}</p> : null}
      <h3>{title}</h3>
      {detail ? <p>{detail}</p> : null}
      {checks.length ? (
        <ul>
          {checks.map((item) => (
            <li key={item}>
              <Check aria-hidden="true" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {actions ? <div className="rd-v2-guided-state-actions">{actions}</div> : null}
    </section>
  );
}
