import { useEffect, useRef, useState } from "react";
import { SettingsPage } from "@/v2/SettingsPage";
import { loadSettings, saveSettings } from "@/v2/settingsStore";
import { V2_WORKSPACE_TABS } from "@/v2/nav-config.jsx";
import { useFocusTrap } from "@/v2/useFocusTrap";

/**
 * Workspace Preferences overlay.
 * - mode "workspace" (account menu): compact local prefs only — default tab + on-select.
 * - mode "settings" (legacy ?tab=settings / Manage context): full Research context → Workspace → Advanced.
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
  const [settings, setSettings] = useState(() => loadSettings());

  useEffect(() => {
    if (!open) return undefined;
    setSettings(loadSettings());
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

  const fullSettings = mode === "settings" || initialAdvancedOpen;
  const activeGroup = initialAdvancedOpen ? "advanced" : "context";
  const title = "Workspace preferences";
  const panelClass = fullSettings
    ? "rd-v2-account-overlay-panel rd-v2-account-overlay-panel--prefs rd-v2-account-overlay-panel--settings"
    : "rd-v2-account-overlay-panel rd-v2-account-overlay-panel--prefs rd-v2-account-overlay-panel--compact";

  const patch = (p) => setSettings(saveSettings(p));

  return (
    <div
      className={`rd-v2-account-overlay${fullSettings ? "" : " is-compact"}`}
      data-testid="workspace-prefs-overlay"
      role="presentation"
    >
      <button
        type="button"
        className="rd-v2-account-overlay-backdrop"
        aria-label="Close workspace preferences"
        data-testid="workspace-prefs-backdrop"
        onClick={() => onClose?.()}
      />
      <div
        className={panelClass}
        role="dialog"
        aria-modal="true"
        aria-labelledby="workspace-prefs-title"
        ref={panelRef}
        data-advanced-open={initialAdvancedOpen ? "1" : "0"}
        data-prefs-mode={fullSettings ? "settings" : "workspace"}
      >
        <div className="rd-v2-account-overlay-chrome">
          <h1 id="workspace-prefs-title" className="rd-v2-account-overlay-title">
            {title}
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
          {fullSettings ? (
            <SettingsPage
              profile={profile}
              onProfileRefresh={onProfileRefresh}
              onToast={onToast}
              activeGroup={activeGroup}
              onClearContext={onClearContext}
              embedded
            />
          ) : (
            <div className="rd-v2-workspace-prefs-compact" data-testid="workspace-prefs-compact">
              <p className="rd-v2-workspace-prefs-lead">
                Browser-local defaults only. These do not sync to a remote account.
              </p>

              <div className="rd-v2-workspace-menu-row">
                <label htmlFor="workspace-default-tab">Default tab</label>
                <select
                  id="workspace-default-tab"
                  className="rd-v2-select"
                  value={settings.defaultTab}
                  data-testid="workspace-default-tab"
                  onChange={(e) => patch({ defaultTab: e.target.value })}
                >
                  {V2_WORKSPACE_TABS.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <p className="rd-v2-settings-hint">
                  Which page opens when you load Research Drive on this browser.
                </p>
              </div>

              <div className="rd-v2-workspace-menu-row">
                <label htmlFor="workspace-on-select">On select</label>
                <select
                  id="workspace-on-select"
                  className="rd-v2-select"
                  value={settings.onSelect}
                  data-testid="workspace-on-select"
                  onChange={(e) => patch({ onSelect: e.target.value })}
                >
                  <option value="detail">Show Detail</option>
                  <option value="ask">Open Ask</option>
                </select>
                <p className="rd-v2-settings-hint">
                  Whether selecting evidence opens Detail or Ask on this browser.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
