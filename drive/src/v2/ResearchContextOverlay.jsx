import { useEffect, useRef } from "react";
import { ProfilePage } from "@/v2/ProfilePage";
import { useFocusTrap } from "@/v2/useFocusTrap";

/**
 * Research Context overlay — what Drive understands for this browser.
 * Legacy ?tab=profile opens this instead of a page-level Profile route.
 */
export function ResearchContextOverlay({
  open,
  profile,
  onClose,
  onProfileRefresh,
  restoreFocusRef,
  onAskAboutContext,
  onAskAboutWork,
  onChangeContext,
  onGoTab,
  onSuggestSearch,
  selectedWorkId = null,
  onSelectWork,
}) {
  const panelRef = useRef(null);
  useFocusTrap(open, { containerRef: panelRef, restoreFocusRef });

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose?.();
      }
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  const handleGoTab = (tab) => {
    if (tab === "settings") {
      onChangeContext?.();
      return;
    }
    onClose?.();
    onGoTab?.(tab);
  };

  return (
    <div className="rd-v2-account-overlay" data-testid="research-context-overlay" role="presentation">
      <button
        type="button"
        className="rd-v2-account-overlay-backdrop"
        aria-label="Close research context"
        data-testid="research-context-backdrop"
        onClick={() => onClose?.()}
      />
      <div
        className="rd-v2-account-overlay-panel rd-v2-account-overlay-panel--research"
        role="dialog"
        aria-modal="true"
        aria-labelledby="research-context-title"
        ref={panelRef}
      >
        <div className="rd-v2-account-overlay-chrome">
          <h1 id="research-context-title" className="rd-v2-account-overlay-title">
            Research context
          </h1>
          <button
            type="button"
            className="rd-v2-account-overlay-close"
            data-testid="research-context-close"
            aria-label="Close"
            onClick={() => onClose?.()}
          >
            ×
          </button>
        </div>
        <div className="rd-v2-account-overlay-body">
          <ProfilePage
            profile={profile}
            onProfileRefresh={onProfileRefresh}
            selectedWorkId={selectedWorkId}
            onSelectWork={onSelectWork}
            onGoTab={handleGoTab}
            onSuggestSearch={onSuggestSearch}
            onAskAboutContext={(ctx) => {
              onAskAboutContext?.(ctx);
              onClose?.();
            }}
            onAskAboutWork={(work) => {
              onAskAboutWork?.(work);
              onClose?.();
            }}
            embedded
          />
        </div>
      </div>
    </div>
  );
}
