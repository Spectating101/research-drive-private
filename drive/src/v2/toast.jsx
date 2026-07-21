import { useCallback, useEffect, useRef, useState } from "react";

const TOAST_VISIBLE_MS = 4050;
const TOAST_EXIT_MS = 150;
let toastSequence = 0;

/**
 * Toast with optional scoping metadata for candidate-bound chrome.
 *
 * show(message, kind = "info")
 * show(message, { kind, scope, candidateKey })
 */
export function useToast() {
  const [toast, setToast] = useState(null);
  const hideTimerRef = useRef(null);
  const clearTimerRef = useRef(null);

  const clearTimers = useCallback(() => {
    window.clearTimeout(hideTimerRef.current);
    window.clearTimeout(clearTimerRef.current);
    hideTimerRef.current = null;
    clearTimerRef.current = null;
  }, []);

  const dismissAnimated = useCallback(() => {
    window.clearTimeout(clearTimerRef.current);
    setToast((current) => (current ? { ...current, phase: "exiting" } : current));
    clearTimerRef.current = window.setTimeout(() => setToast(null), TOAST_EXIT_MS);
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const show = useCallback((message, kindOrMeta = "info") => {
    const text = String(message || "").trim();
    if (!text) return;
    let kind = "info";
    let scope = undefined;
    let candidateKey = undefined;
    if (typeof kindOrMeta === "string") {
      kind = kindOrMeta;
    } else if (kindOrMeta && typeof kindOrMeta === "object") {
      kind = kindOrMeta.kind || "info";
      scope = kindOrMeta.scope || undefined;
      candidateKey = kindOrMeta.candidateKey || undefined;
    }

    clearTimers();
    setToast({
      id: ++toastSequence,
      message: text,
      kind,
      scope,
      candidateKey,
      phase: "entered",
    });
    hideTimerRef.current = window.setTimeout(dismissAnimated, TOAST_VISIBLE_MS);
  }, [clearTimers, dismissAnimated]);

  const dismissIf = useCallback((predicate) => {
    setToast((current) => {
      if (!current) return current;
      try {
        if (!predicate(current)) return current;
        clearTimers();
        return null;
      } catch {
        return current;
      }
    });
  }, [clearTimers]);

  const clear = useCallback(() => {
    clearTimers();
    setToast(null);
  }, [clearTimers]);

  return { toast, show, dismissIf, clear };
}

export function Toast({ toast }) {
  if (!toast) return null;
  const urgent = toast.kind === "error";
  return (
    <div
      key={toast.id}
      className={`rd-v2-toast ${toast.kind}${toast.phase === "exiting" ? " exiting" : ""}`}
      role={urgent ? "alert" : "status"}
      aria-live={urgent ? "assertive" : "polite"}
      aria-atomic="true"
      data-toast-scope={toast.scope || undefined}
      data-toast-candidate={toast.candidateKey || undefined}
    >
      {toast.message}
    </div>
  );
}
