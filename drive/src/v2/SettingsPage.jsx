import { useEffect, useMemo, useState } from "react";
import { deskHealth } from "@/v2/api";
import {
  clearDeskToken,
  hasDeskToken,
  loadDeskToken,
  saveDeskToken,
  saveUserEmail,
} from "@/v2/deskSession";
import { loadSettings, saveSettings } from "@/v2/settingsStore";
import { PageShell, StatementRow, StatementSection } from "@/v2/ui";
import { V2_TABS } from "@/v2/nav-config.jsx";
import {
  RailEntityHeader,
  RailField,
  RailFieldGrid,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";

export const SETTINGS_GROUPS = [
  { id: "identity", title: "Identity" },
  { id: "access", title: "Access" },
  { id: "defaults", title: "Defaults" },
  { id: "advanced", title: "Advanced recovery" },
];

function healthSignalsPresent(desk) {
  return Boolean(
    desk &&
      ("composer_configured" in desk ||
        desk.mcp_tools?.total != null ||
        "gdrive" in desk ||
        "jobs" in desk),
  );
}

function assistantLabel(desk, healthLoaded) {
  if (!healthLoaded) return { label: "Not reported", known: false, ready: false, detail: "No /health desk payload" };
  if (desk.composer_configured === true) {
    return {
      label: "Ready",
      known: true,
      ready: true,
      detail: desk.composer_model || desk.brain || "Composer runtime",
    };
  }
  if (desk.composer_configured === false) {
    return {
      label: "Needs setup",
      known: true,
      ready: false,
      detail: "Assistant health reports offline",
    };
  }
  return { label: "Not reported", known: false, ready: false, detail: "No composer flag on /health" };
}

function archiveLabel(desk, healthLoaded) {
  if (!healthLoaded || !desk.gdrive) {
    return { label: "Not reported", known: false, ok: null, detail: "No archive signal on /health" };
  }
  if (desk.gdrive.ok === true || desk.gdrive.ready === true || desk.gdrive.drive_list_ok === true) {
    return {
      label: "Connected",
      known: true,
      ok: true,
      detail: desk.gdrive.drive_root || desk.gdrive.gdrive_remote || "GDrive probe ok",
    };
  }
  if (desk.gdrive.ok === false) {
    return { label: "Needs review", known: true, ok: false, detail: "Archive probe failed" };
  }
  return { label: "Not reported", known: true, ok: null, detail: "Archive signal incomplete" };
}

/**
 * Settings centre — Identity → Access → Defaults → Advanced recovery (collapsed).
 * No top metric-card dashboard. Browser / bootstrap / fallback token stay in Advanced.
 */
export function SettingsPage({
  health,
  onProfileRefresh,
  onToast,
  activeGroup,
  selectedGroup,
  onSelectGroup,
  onActiveGroupChange,
}) {
  const groupId = activeGroup || selectedGroup || "identity";
  const selectGroup = (id) => {
    onSelectGroup?.(id);
    onActiveGroupChange?.(id);
  };
  const [settings, setSettings] = useState(() => loadSettings());
  const [emailDraft, setEmailDraft] = useState(() => settings.email || "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenPresent, setTokenPresent] = useState(() => hasDeskToken());
  const [liveHealth, setLiveHealth] = useState(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const effectiveHealth = liveHealth || health;
  const desk = effectiveHealth?.desk || {};
  const healthLoaded = healthSignalsPresent(desk);
  const assistant = assistantLabel(desk, healthLoaded);
  const archive = archiveLabel(desk, healthLoaded);
  const toolCount = desk.mcp_tools?.total;
  const pendingJobs =
    healthLoaded && desk.jobs && "pending_approval" in desk.jobs
      ? Number(desk.jobs.pending_approval ?? 0)
      : null;
  const deskPort =
    typeof window !== "undefined" ? `:${window.location.port || "8765"}` : ":8765";
  const browserOrigin = typeof window !== "undefined" ? window.location.origin : "—";

  const patch = (p) => setSettings(saveSettings(p));

  useEffect(() => {
    let cancelled = false;
    let liveApplied = false;
    deskHealth(false)
      .then((out) => {
        if (!cancelled && !liveApplied) setLiveHealth(out);
      })
      .catch(() => {});
    deskHealth(true)
      .then((live) => {
        liveApplied = true;
        if (!cancelled) setLiveHealth(live);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (groupId === "advanced") setAdvancedOpen(true);
  }, [groupId]);

  const saveEmail = () => {
    const email = saveUserEmail(emailDraft);
    patch({ email });
    onProfileRefresh?.();
    onToast?.(email ? `Profile loaded for ${email}` : "Email cleared");
    selectGroup("identity");
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

  return (
    <PageShell
      className="rd-v2-settings-page"
      title="Settings"
      lead="Identity, access, defaults, and recovery"
    >
      <div className="rd-v2-settings-statement" data-testid="settings-centre">
        <StatementSection
          title="Identity"
          className={groupId === "identity" ? "is-active-group" : ""}
          action={
            <button type="button" className="rd-v2-linkish" onClick={() => selectGroup("identity")}>
              Detail
            </button>
          }
        >
          <div
            className="rd-v2-settings-group"
            data-testid="settings-group-identity"
            onFocus={() => selectGroup("identity")}
          >
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
                onFocus={() => selectGroup("identity")}
                autoComplete="email"
              />
              <button type="button" className="rd-v2-btn sm primary" onClick={saveEmail}>
                Save identity
              </button>
            </div>
            <p className="rd-v2-settings-hint">
              Used for profile-aware Discover ranking and Ask context. Binding happens here — not on Profile.
            </p>
          </div>
        </StatementSection>

        <StatementSection
          title="Access"
          className={groupId === "access" ? "is-active-group" : ""}
          action={
            <button type="button" className="rd-v2-linkish" onClick={() => selectGroup("access")}>
              Detail
            </button>
          }
        >
          <div
            className="rd-v2-settings-group"
            data-testid="settings-group-access"
            onClick={() => selectGroup("access")}
          >
            <StatementRow
              label="Ask / Composer"
              metric={assistant.label}
              sublabel={assistant.detail}
              detail={assistant.ready ? "OK" : assistant.known ? "CHECK" : "UNKNOWN"}
              warn={assistant.known && !assistant.ready}
            />
            <StatementRow
              label="Research archive"
              metric={archive.label}
              sublabel={archive.detail}
              detail={archive.ok === true ? "OK" : archive.ok === false ? "CHECK" : "UNKNOWN"}
              warn={archive.ok === false}
            />
            {!healthLoaded ? (
              <p className="rd-v2-settings-hint">
                Desk health not loaded — Access stays Not reported until /health verifies.
              </p>
            ) : null}
          </div>
        </StatementSection>

        <StatementSection
          title="Defaults"
          className={groupId === "defaults" ? "is-active-group" : ""}
          action={
            <button type="button" className="rd-v2-linkish" onClick={() => selectGroup("defaults")}>
              Detail
            </button>
          }
        >
          <div
            className="rd-v2-settings-group"
            data-testid="settings-group-defaults"
            onFocus={() => selectGroup("defaults")}
          >
            <div className="rd-v2-settings-row">
              <label htmlFor="settings-default-tab">Default tab</label>
              <select
                id="settings-default-tab"
                value={settings.defaultTab}
                onChange={(e) => {
                  patch({ defaultTab: e.target.value });
                  selectGroup("defaults");
                }}
                onFocus={() => selectGroup("defaults")}
                className="rd-v2-select"
              >
                {V2_TABS.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="rd-v2-settings-row">
              <label htmlFor="settings-on-select">On select</label>
              <select
                id="settings-on-select"
                value={settings.onSelect}
                onChange={(e) => {
                  patch({ onSelect: e.target.value });
                  selectGroup("defaults");
                }}
                onFocus={() => selectGroup("defaults")}
                className="rd-v2-select"
              >
                <option value="detail">Show Detail</option>
                <option value="ask">Open Ask</option>
              </select>
            </div>
          </div>
        </StatementSection>

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
          <summary>Advanced recovery</summary>
          <div className="rd-v2-settings-advanced-body" data-testid="settings-advanced-body">
            <p className="rd-v2-settings-hint">
              Technical browser, bootstrap, and fallback-token diagnostics. Not faculty workflow.
            </p>
            <div className="rd-v2-settings-row">
              <span>Browser origin</span>
              <code>{browserOrigin}</code>
            </div>
            <div className="rd-v2-settings-row">
              <span>Vite desk port</span>
              <code>{deskPort}</code>
            </div>
            <div className="rd-v2-settings-row">
              <span>Bootstrap health</span>
              <code>{healthLoaded ? "desk health received" : "not received"}</code>
            </div>
            <div className="rd-v2-settings-row">
              <span>Fallback token</span>
              <code>{tokenPresent ? "present in sessionStorage" : "absent"}</code>
            </div>
            <StatementRow
              label="MCP tools"
              metric={toolCount != null ? String(toolCount) : "Not reported"}
              sublabel="From /health.desk.mcp_tools"
              detail={toolCount != null ? "REPORTED" : "UNKNOWN"}
            />
            <StatementRow
              label="Jobs pending approval"
              metric={pendingJobs == null ? "Not reported" : String(pendingJobs)}
              sublabel="From /health.desk.jobs"
              detail={pendingJobs == null ? "UNKNOWN" : "REPORTED"}
            />
            <div className="rd-v2-settings-row stack">
              <label className="rd-v2-settings-label" htmlFor="settings-fallback-token">
                Fallback access token
              </label>
              <input
                id="settings-fallback-token"
                type="password"
                className="rd-v2-input"
                placeholder="Only if same-origin session fails"
                value={tokenDraft}
                autoComplete="off"
                onChange={(e) => setTokenDraft(e.target.value)}
                onFocus={() => selectGroup("advanced")}
              />
              <div className="rd-v2-settings-actions">
                <button type="button" className="rd-v2-btn sm primary" onClick={saveToken}>
                  Save fallback
                </button>
                <button type="button" className="rd-v2-btn sm" onClick={clearToken}>
                  Clear
                </button>
                <button
                  type="button"
                  className="rd-v2-btn sm"
                  onClick={() => window.open("/api/health", "_blank")}
                >
                  Open /api/health
                </button>
              </div>
            </div>
          </div>
        </details>
      </div>
    </PageShell>
  );
}

const GROUP_COPY = {
  identity: {
    judgement: "Faculty email drives Profile memory, Discover ranking, and Ask context.",
    actionLabel: "Focus Identity",
  },
  access: {
    judgement: "Show only verified /health signals — never invent Ready.",
    actionLabel: "Focus Access",
  },
  defaults: {
    judgement: "Landing tab and selection behaviour for this browser only.",
    actionLabel: "Focus Defaults",
  },
  advanced: {
    judgement: "Browser, bootstrap, and fallback-token repair stay off the normal path.",
    actionLabel: "Open Advanced recovery",
  },
};

/** DETAIL rail — current Settings group, ≤5 facts, one action. Never Loading / blank. */
export function SettingsDetailPanel({
  health = null,
  settings: settingsProp = null,
  activeGroup = "identity",
  group: groupProp = null,
  onSelectGroup,
  onFocusGroup,
}) {
  const settings = settingsProp || loadSettings();
  const desk = health?.desk || {};
  const healthLoaded = healthSignalsPresent(desk);
  const groupId = groupProp || activeGroup || "identity";
  const group = SETTINGS_GROUPS.find((g) => g.id === groupId) || SETTINGS_GROUPS[0];
  const selectGroup = onSelectGroup || onFocusGroup;
  const copy = GROUP_COPY[group.id] || GROUP_COPY.identity;
  const assistant = assistantLabel(desk, healthLoaded);
  const archive = archiveLabel(desk, healthLoaded);
  const email = settings.email || "";
  const deskPort =
    typeof window !== "undefined" ? `:${window.location.port || "8765"}` : ":8765";

  const facts = useMemo(() => {
    if (group.id === "identity") {
      return [
        ["Faculty email", email || "Not set"],
        ["Profile routing", email ? "Bound" : "Unbound"],
        ["Edit surface", "Centre Identity group"],
      ];
    }
    if (group.id === "access") {
      const rows = [
        ["Ask / Composer", assistant.label],
        ["Archive", archive.label],
      ];
      if (desk.mcp_tools?.total != null) rows.push(["MCP tools", String(desk.mcp_tools.total)]);
      if (healthLoaded && desk.jobs && "pending_approval" in desk.jobs) {
        rows.push(["Jobs pending", String(desk.jobs.pending_approval ?? 0)]);
      }
      rows.push(["Health payload", healthLoaded ? health?.status || "received" : "Not reported"]);
      return rows.slice(0, 5);
    }
    if (group.id === "defaults") {
      return [
        ["Default tab", settings.defaultTab || "home"],
        ["On select", settings.onSelect === "ask" ? "Open Ask" : "Show Detail"],
        ["Scope", "This browser only"],
      ];
    }
    return [
      ["Fallback token", hasDeskToken() ? "Present" : "Absent"],
      ["Token length", hasDeskToken() ? String(loadDeskToken().length) : "—"],
      ["Bootstrap", healthLoaded ? "Health received" : "Not received"],
      ["Port", deskPort],
    ].slice(0, 5);
  }, [
    group.id,
    email,
    assistant.label,
    archive.label,
    healthLoaded,
    health,
    settings.defaultTab,
    settings.onSelect,
    desk.mcp_tools?.total,
    desk.jobs,
    deskPort,
  ]);

  return (
    <RailFrame>
      <RailEntityHeader
        id={`settings-${group.id}`}
        title={group.title}
        description={copy.judgement}
      />
      <div className="rd-v2-rail-scroll" data-testid="settings-detail-rail">
        <p className="rd-v2-rail-section-label">Judgement</p>
        <p className="rd-v2-settings-rail-judgement">{copy.judgement}</p>
        <p className="rd-v2-rail-section-label">Facts</p>
        <RailFieldGrid>
          {facts.map(([label, value]) => (
            <RailField key={label} label={label} value={value} />
          ))}
        </RailFieldGrid>
      </div>
      <RailStickyFooter>
        <button
          type="button"
          className="rd-v2-btn sm primary"
          data-testid="settings-detail-action"
          onClick={() => selectGroup?.(group.id)}
        >
          {copy.actionLabel}
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}
