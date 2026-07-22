import { useEffect, useRef } from "react";
import { ProfilePage } from "@/v2/ProfilePage";
import { SettingsPage } from "@/v2/SettingsPage";
import { useFocusTrap } from "@/v2/useFocusTrap";

export const ACCOUNT_DIALOG_MODES = {
  research: "research",
  preferences: "preferences",
};

/**
 * One stable account dialog shell for Research context + Workspace preferences.
 * Desktop geometry is fixed (content may change; scale never does).
 * Mobile keeps the near-full sheet treatment via CSS.
 */
export function AccountDialogOverlay({
  open,
  mode = ACCOUNT_DIALOG_MODES.research,
  onModeChange,
  onClose,
  restoreFocusRef,
  profile,
  selectedWorkId = null,
  onSelectWork,
  onAskAboutContext,
  onAskAboutWork,
  onGoTab,
  onSuggestSearch,
  onProfileRefresh,
  onToast,
  onClearContext,
  preferencesActiveGroup = "workspace",
}) {
  const panelRef = useRef(null);
  useFocusTrap(open, { containerRef: panelRef, restoreFocusRef });
  const isResearch = mode === ACCOUNT_DIALOG_MODES.research;
  const panelTestId = isResearch ? "research-context-overlay" : "workspace-prefs-overlay";

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
      onModeChange?.(ACCOUNT_DIALOG_MODES.preferences);
      return;
    }
    onClose?.();
    onGoTab?.(tab);
  };

  return (
    <div
      className="rd-v2-account-overlay rd-v2-account-overlay--account"
      data-testid="account-dialog-overlay"
      data-mode={mode}
      role="presentation"
    >
      <button
        type="button"
        className="rd-v2-account-overlay-backdrop"
        aria-label={isResearch ? "Close research context" : "Close workspace preferences"}
        data-testid={isResearch ? "research-context-backdrop" : "workspace-prefs-backdrop"}
        onClick={() => onClose?.()}
      />
      <div
        className="rd-v2-account-overlay-panel rd-v2-account-overlay-panel--account"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-dialog-title"
        ref={panelRef}
        data-testid={panelTestId}
      >
        <div className="rd-v2-account-overlay-chrome rd-v2-account-dialog-chrome">
          <div className="rd-v2-account-dialog-chrome-main">
            <h1 id="account-dialog-title" className="rd-v2-account-overlay-title">
              {isResearch ? "Research context" : "Workspace preferences"}
            </h1>
            <div
              className="rd-v2-account-dialog-modes"
              role="tablist"
              aria-label="Account dialog mode"
              data-testid="account-dialog-modes"
            >
              <button
                type="button"
                role="tab"
                id="account-mode-research"
                className={`rd-v2-account-dialog-mode${isResearch ? " is-active" : ""}`}
                aria-selected={isResearch}
                data-testid="account-dialog-mode-research"
                onClick={() => onModeChange?.(ACCOUNT_DIALOG_MODES.research)}
              >
                Research context
              </button>
              <button
                type="button"
                role="tab"
                id="account-mode-preferences"
                className={`rd-v2-account-dialog-mode${!isResearch ? " is-active" : ""}`}
                aria-selected={!isResearch}
                data-testid="account-dialog-mode-preferences"
                onClick={() => onModeChange?.(ACCOUNT_DIALOG_MODES.preferences)}
              >
                Workspace preferences
              </button>
            </div>
          </div>
          <button
            type="button"
            className="rd-v2-account-overlay-close"
            data-testid={isResearch ? "research-context-close" : "workspace-prefs-close"}
            aria-label="Close"
            onClick={() => onClose?.()}
          >
            ×
          </button>
        </div>

        <div
          className="rd-v2-account-overlay-body"
          data-testid={isResearch ? undefined : "workspace-preferences"}
          role="tabpanel"
          aria-labelledby={isResearch ? "account-mode-research" : "account-mode-preferences"}
        >
          {isResearch ? (
            <ProfilePage
              profile={profile}
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
              onProfileRefresh={onProfileRefresh}
              onToast={onToast}
              onClearContext={onClearContext}
              embedded
            />
          ) : (
            <SettingsPage
              profile={profile}
              onProfileRefresh={onProfileRefresh}
              onToast={onToast}
              activeGroup={preferencesActiveGroup}
              onClearContext={onClearContext}
              embedded
            />
          )}
        </div>
      </div>
    </div>
  );
}
