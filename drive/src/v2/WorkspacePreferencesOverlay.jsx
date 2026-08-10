import { useEffect, useRef } from "react";
import { SettingsPage } from "@/v2/SettingsPage";
import { useFocusTrap } from "@/v2/useFocusTrap";

/**
 * Workspace Preferences overlay — browser-local controls only
 * (research-context bind, default tab, on-select, advanced recovery).
 * Legacy ?tab=settings opens this instead of a page-level Settings route.
 */
export function WorkspacePreferencesOverlay({
  open,
  profile = null,
  onClose,
  onProfileRefresh,
  onToast,
  restoreFocusRef,
  mode = "workspace",
  initialAdvancedOpen = false,
  onClearContext,
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

  // mode is retained for callers; advanced recovery forces the Advanced group open.
  const activeGroup = initialAdvancedOpen || mode === "advanced" ? "advanced" : "context";

  return (
    <div className="rd-v2-account-overlay" data-testid="workspace-prefs-overlay" role="presentation">
      <button
        type="button"
        className="rd-v2-account-overlay-backdrop"
        aria-label="Close workspace preferences"
        data-testid="workspace-prefs-backdrop"
        onClick={() => onClose?.()}
      />
      <div
        className="rd-v2-account-overlay-panel rd-v2-account-overlay-panel--prefs"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workspace-prefs-title"
        ref={panelRef}
      >
        <div className="rd-v2-account-overlay-chrome">
          <h1 id="workspace-prefs-title" className="rd-v2-account-overlay-title">
            Workspace preferences
          </h1>
          <button
            type="button"
            className="rd-v2-account-overlay-close"
            data-testid="workspace-prefs-close"
            aria-label="Close"
            onClick={() => onClose?.()}
          >
            ×
          </button>
        </div>
        <div className="rd-v2-account-overlay-body" data-testid="workspace-preferences">
          <SettingsPage
            profile={profile}
            onProfileRefresh={onProfileRefresh}
            onToast={onToast}
            activeGroup={activeGroup}
            onClearContext={onClearContext}
            embedded
          />
        </div>
      </div>
    </div>
  );
}
