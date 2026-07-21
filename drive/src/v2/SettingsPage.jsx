import { useEffect, useMemo, useState } from "react";
import { facultyProfile } from "@/v2/api";
import {
  clearDeskToken,
  hasDeskToken,
  saveDeskToken,
  saveUserEmail,
} from "@/v2/deskSession";
import { loadSettings, resetLocalPreferences, saveSettings } from "@/v2/settingsStore";
import {
  SETTINGS_GROUP_LABELS,
  buildSettingsRailState,
  settingsAdvancedDefaultOpen,
} from "@/v2/settingsPresentation";
import { PageShell } from "@/v2/ui";
import { V2_WORKSPACE_TABS } from "@/v2/nav-config.jsx";
import {
  RailEntityHeader,
  RailField,
  RailFieldGrid,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";

export const SETTINGS_GROUPS = [
  { id: "context", title: "Research context" },
  { id: "workspace", title: "Workspace" },
  { id: "advanced", title: "Advanced" },
];

/**
 * Settings — compact personal workspace controls.
 * Research context → Workspace → Advanced (collapsed).
 * No operational health rows; Research context overlay owns understanding.
 */
export function SettingsPage({
  profile = null,
  onProfileRefresh,
  onToast,
  activeGroup,
  selectedGroup,
  onSelectGroup,
  onActiveGroupChange,
  onClearContext,
  embedded = false,
}) {
  const groupId = activeGroup || selectedGroup || "context";
  const selectGroup = (id) => {
    onSelectGroup?.(id);
    onActiveGroupChange?.(id);
  };
  const [settings, setSettings] = useState(() => loadSettings());
  const [emailDraft, setEmailDraft] = useState(() => settings.email || "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenPresent, setTokenPresent] = useState(() => hasDeskToken());
  const [advancedOpen, setAdvancedOpen] = useState(() => settingsAdvancedDefaultOpen());
  const [bindStatus, setBindStatus] = useState(null);
  const [savingIdentity, setSavingIdentity] = useState(false);

  const patch = (p) => setSettings(saveSettings(p));

  useEffect(() => {
    if (groupId === "advanced") setAdvancedOpen(true);
  }, [groupId]);

  useEffect(() => {
    if (!settings.email) {
      setBindStatus(null);
      return;
    }
    if (profile && !profile.unknown && (profile.name_en || profile.name)) {
      setBindStatus({
        ok: true,
        name: profile.name_en || profile.name,
      });
    } else if (profile?.unknown && profile?.email) {
      setBindStatus({ ok: false, email: profile.email });
    }
  }, [profile, settings.email]);

  const applyBoundProfile = (email, data) => {
    if (data?.found && data.profile) {
      const name = data.profile.name_en || data.profile.name || "";
      setBindStatus({ ok: true, name: name || email });
      return name;
    }
    setBindStatus({ ok: false, email });
    return "";
  };

  const saveEmail = async () => {
    const email = saveUserEmail(emailDraft);
    patch({ email });
    selectGroup("context");
    setSavingIdentity(true);
    setBindStatus(null);

    try {
      if (!email) {
        onProfileRefresh?.();
        setBindStatus(null);
        onToast?.("Research context cleared on this browser");
        return;
      }

      const data = await facultyProfile(email);
      onProfileRefresh?.();
      const name = applyBoundProfile(email, data);
      if (name) {
        onToast?.(`Context bound to ${name} on this browser`);
      } else if (data?.found) {
        onToast?.(`Context bound for ${email} on this browser`);
      } else {
        onToast?.(`No faculty profile resolved for ${email}`);
      }
    } catch {
      onProfileRefresh?.();
      setBindStatus({ ok: false, email });
      onToast?.(`Could not resolve faculty profile for ${email}`);
    } finally {
      setSavingIdentity(false);
    }
  };

  const clearContext = () => {
    if (onClearContext) {
      onClearContext();
    } else {
      saveUserEmail("");
      saveSettings({ email: "" });
      onProfileRefresh?.();
      onToast?.("Research context cleared on this browser");
    }
    setEmailDraft("");
    setBindStatus(null);
    setSettings(loadSettings());
    selectGroup("context");
  };

  const saveToken = () => {
    const saved = saveDeskToken(tokenDraft);
    setTokenPresent(Boolean(saved));
    setTokenDraft("");
    onToast?.(saved ? "Fallback token saved for this browser session" : "Fallback token cleared");
    selectGroup("advanced");
  };

  const clearToken = () => {
    clearDeskToken();
    setTokenPresent(false);
    setTokenDraft("");
    onToast?.("Fallback token cleared");
    selectGroup("advanced");
  };

  const resetLocal = () => {
    clearDeskToken();
    setTokenPresent(false);
    setTokenDraft("");
    const next = resetLocalPreferences();
    setSettings(next);
    setEmailDraft("");
    setBindStatus(null);
    onProfileRefresh?.();
    selectGroup("advanced");
    onToast?.("Browser-local research context and preferences reset");
  };

  const boundName =
    bindStatus?.ok && bindStatus.name
      ? bindStatus.name
      : profile && !profile.unknown
        ? profile.name_en || profile.name || ""
        : "";

  return (
    <PageShell
      className={`rd-v2-settings-page${embedded ? " is-embedded" : ""}`}
      title={embedded ? null : "Settings"}
      lead={embedded ? null : "Browser-local research context and workspace preferences"}
    >
      <div className="rd-v2-settings-panel" data-testid="settings-centre">
        <section
          className={`rd-v2-settings-block${groupId === "context" ? " is-active-group" : ""}`}
          data-testid="settings-group-context"
          onFocus={() => selectGroup("context")}
        >
          <header className="rd-v2-settings-block-head">
            <h2>Research context</h2>
          </header>
          <p className="rd-v2-settings-scope" data-testid="settings-context-scope">
            This browser only — not sign-in or access control.
          </p>

          {boundName ? (
            <p className="rd-v2-settings-bound-person" data-testid="settings-bound-person">
              Currently bound to <strong>{boundName}</strong>
            </p>
          ) : settings.email ? (
            <p className="rd-v2-settings-bound-person muted" data-testid="settings-bound-person">
              Email saved · profile unresolved
            </p>
          ) : (
            <p className="rd-v2-settings-bound-person muted" data-testid="settings-bound-person">
              No research context on this browser
            </p>
          )}

          <div className="rd-v2-settings-row stack">
            <label className="rd-v2-settings-label" htmlFor="settings-email">
              Faculty email
            </label>
            <input
              id="settings-email"
              type="email"
              className="rd-v2-input"
              placeholder="name@yzu.edu.tw"
              value={emailDraft}
              onChange={(e) => setEmailDraft(e.target.value)}
              onFocus={() => selectGroup("context")}
              autoComplete="email"
              data-testid="settings-email-input"
            />
            <p className="rd-v2-settings-hint" data-testid="settings-email-hint">
              Contextual preference for this browser — used for Research context, Discover ranking, and Ask.
              Not a sign-in. Binding happens here — not in the Research context overlay.
            </p>
            <div className="rd-v2-settings-actions">
              <button
                type="button"
                className="rd-v2-btn sm primary"
                data-testid="settings-save-identity"
                disabled={savingIdentity}
                onClick={saveEmail}
              >
                {savingIdentity ? "Saving…" : "Save context"}
              </button>
              <button
                type="button"
                className="rd-v2-btn sm"
                data-testid="settings-clear-context"
                disabled={!settings.email && !emailDraft}
                onClick={clearContext}
              >
                Clear context
              </button>
            </div>
          </div>

          {bindStatus?.ok ? (
            <p className="rd-v2-settings-bind-ok" data-testid="settings-bind-status">
              Context bound to {bindStatus.name} on this browser. Research context updates from this
              selection; Discover ranking and Ask use it here only.
            </p>
          ) : null}
          {bindStatus && !bindStatus.ok ? (
            <p className="rd-v2-settings-bind-fail" data-testid="settings-bind-status">
              No faculty profile resolved for {bindStatus.email}. The email is saved on this
              browser; ranking stays on generic defaults until a known profile resolves.
            </p>
          ) : null}
        </section>

        <section
          className={`rd-v2-settings-block${groupId === "workspace" ? " is-active-group" : ""}`}
          data-testid="settings-group-workspace"
          onFocus={() => selectGroup("workspace")}
        >
          <header className="rd-v2-settings-block-head">
            <h2>Workspace</h2>
          </header>

          <div className="rd-v2-settings-row stack">
            <label htmlFor="settings-default-tab">Default tab</label>
            <select
              id="settings-default-tab"
              value={settings.defaultTab}
              onChange={(e) => {
                patch({ defaultTab: e.target.value });
                selectGroup("workspace");
              }}
              onFocus={() => selectGroup("workspace")}
              className="rd-v2-select"
              data-testid="settings-default-tab"
            >
              {V2_WORKSPACE_TABS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
            <p className="rd-v2-settings-hint">
              Chooses which page opens when you load Research Drive on this browser.
            </p>
          </div>

          <div className="rd-v2-settings-row stack">
            <label htmlFor="settings-on-select">On select</label>
            <select
              id="settings-on-select"
              value={settings.onSelect}
              onChange={(e) => {
                patch({ onSelect: e.target.value });
                selectGroup("workspace");
              }}
              onFocus={() => selectGroup("workspace")}
              className="rd-v2-select"
              data-testid="settings-on-select"
            >
              <option value="detail">Show Detail</option>
              <option value="ask">Open Ask</option>
            </select>
            <p className="rd-v2-settings-hint">
              Chooses whether selecting evidence opens Detail or Ask on this browser.
            </p>
          </div>
        </section>

        <details
          className={`rd-v2-settings-advanced${groupId === "advanced" ? " is-active-group" : ""}`}
          data-testid="settings-group-advanced"
          open={advancedOpen}
          onToggle={(e) => {
            const next = e.currentTarget.open;
            setAdvancedOpen(next);
            if (next) selectGroup("advanced");
          }}
        >
          <summary>Advanced</summary>
          <div className="rd-v2-settings-advanced-body" data-testid="settings-advanced-body">
            <p className="rd-v2-settings-hint">
              Maintenance for this browser only. Not faculty workflow and not operational health.
            </p>

            <div className="rd-v2-settings-row stack">
              <span className="rd-v2-settings-label">Fallback access token</span>
              <code data-testid="settings-token-status">
                {tokenPresent ? "present in sessionStorage" : "absent"}
              </code>
              <input
                id="settings-fallback-token"
                type="password"
                className="rd-v2-input"
                placeholder="Only if same-origin session fails"
                value={tokenDraft}
                autoComplete="off"
                onChange={(e) => setTokenDraft(e.target.value)}
                onFocus={() => selectGroup("advanced")}
                aria-label="Fallback access token"
              />
              <div className="rd-v2-settings-actions">
                <button type="button" className="rd-v2-btn sm primary" onClick={saveToken}>
                  Save fallback
                </button>
                <button
                  type="button"
                  className="rd-v2-btn sm"
                  data-testid="settings-clear-token"
                  onClick={clearToken}
                >
                  Clear fallback token
                </button>
              </div>
            </div>

            <div className="rd-v2-settings-row stack">
              <span className="rd-v2-settings-label">Reset local state</span>
              <p className="rd-v2-settings-hint">
                Clears research-context email and workspace preferences on this browser.
              </p>
              <button
                type="button"
                className="rd-v2-btn sm"
                data-testid="settings-reset-local"
                onClick={resetLocal}
              >
                Reset browser-local context and preferences
              </button>
            </div>
          </div>
        </details>
      </div>
    </PageShell>
  );
}

/** DETAIL rail — quiet local values; Clear context only when it works. */
export function SettingsDetailPanel({
  settings: settingsProp = null,
  profile = null,
  activeGroup = "context",
  group: groupProp = null,
  onClearContext,
}) {
  const settings = settingsProp || loadSettings();
  const groupId = groupProp || activeGroup || "context";
  const group = SETTINGS_GROUPS.find((g) => g.id === groupId) || SETTINGS_GROUPS[0];

  const rail = useMemo(
    () =>
      buildSettingsRailState({
        group: group.id,
        settings,
        profile,
        tokenPresent: hasDeskToken(),
      }),
    [group.id, settings, profile],
  );

  const title = SETTINGS_GROUP_LABELS[group.id] || group.title;

  return (
    <RailFrame>
      <RailEntityHeader id={`settings-${group.id}`} title={title} />
      <div className="rd-v2-rail-scroll" data-testid="settings-detail-rail">
        <p className="rd-v2-rail-section-label">This browser</p>
        <RailFieldGrid>
          {rail.facts.map(([label, value]) => (
            <RailField key={label} label={label} value={value} />
          ))}
        </RailFieldGrid>
      </div>
      {rail.primaryAction?.id === "clear-context" && onClearContext ? (
        <RailStickyFooter>
          <button
            type="button"
            className="rd-v2-btn sm primary"
            data-testid="settings-detail-clear-context"
            onClick={() => onClearContext()}
          >
            {rail.primaryAction.label}
          </button>
        </RailStickyFooter>
      ) : null}
    </RailFrame>
  );
}
