import { useEffect, useState } from "react";
import { deskHealth } from "@/v2/api";
import { saveUserEmail } from "@/v2/deskSession";
import { loadSettings, saveSettings } from "@/v2/settingsStore";
import { PageShell, StatementRow, StatementSection } from "@/v2/ui";
import { V2_TABS } from "@/v2/nav-config.jsx";

function StatusBadge({ ok, label }) {
  const tone = ok ? "ok" : "miss";
  return <span className={`rd-v2-status-badge ${tone}`}>{label}</span>;
}

export function SettingsPage({ health, onProfileRefresh, onToast }) {
  const [settings, setSettings] = useState(() => loadSettings());
  const [emailDraft, setEmailDraft] = useState(() => settings.email || "");
  const [liveHealth, setLiveHealth] = useState(null);
  const effectiveHealth = liveHealth || health;
  const desk = effectiveHealth?.desk || {};
  const healthLoaded = Boolean(
    effectiveHealth?.desk && (
      "composer_configured" in desk ||
      desk.mcp_tools?.total != null ||
      "gdrive" in desk ||
      "jobs" in desk
    ),
  );
  const hasGdriveSignal = Boolean(desk.gdrive);
  const gdriveReady =
    hasGdriveSignal && (
      desk.gdrive?.ready === true ||
      desk.gdrive?.ok === true ||
      desk.gdrive?.drive_list_ok === true
    );
  const gdriveConfigured = hasGdriveSignal && Boolean(
    desk.gdrive?.drive_root ||
    desk.gdrive?.gdrive_remote ||
    desk.gdrive?.rclone_installed,
  );
  const composerReady = desk.composer_configured === true;
  const pendingJobs = healthLoaded ? (desk.jobs?.pending_approval ?? 0) : null;
  const toolCount = desk.mcp_tools?.total ?? 0;
  const deskPort = typeof window !== "undefined" ? `:${window.location.port || "5179"}` : ":5179";

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

  const saveEmail = () => {
    const email = saveUserEmail(emailDraft);
    patch({ email });
    onProfileRefresh?.();
    onToast?.(email ? `Profile loaded for ${email}` : "Email cleared");
  };

  return (
    <PageShell title="Desk setup" lead="Identity, assistant readiness, vault archive, and display preferences.">
      <section className="rd-v2-settings-summary" aria-label="Desk setup summary">
        <div>
          <span>Faculty identity</span>
          <strong>{settings.email || "Not connected"}</strong>
          <StatusBadge ok={Boolean(settings.email)} label={settings.email ? "Profile routing" : "Generic mode"} />
        </div>
        <div>
          <span>Ask and procurement</span>
          <strong>{healthLoaded ? (composerReady ? "Ready" : "Needs key") : "Connecting…"}</strong>
          <StatusBadge ok={composerReady} label={healthLoaded ? (toolCount ? `${toolCount} tools` : "Needs review") : "Live status"} />
        </div>
        <div>
          <span>Vault archive</span>
          <strong>
            {hasGdriveSignal
              ? gdriveReady
                ? "Drive ready"
                : gdriveConfigured
                  ? "Route configured"
                  : "Needs review"
              : "Connecting…"}
          </strong>
          <StatusBadge
            ok={gdriveReady || gdriveConfigured}
            label={gdriveReady ? "verified" : gdriveConfigured ? "probe pending" : "archive route"}
          />
        </div>
        <div>
          <span>Decision queue</span>
          <strong>{pendingJobs == null ? "—" : pendingJobs}</strong>
          <StatusBadge
            ok={pendingJobs === 0}
            label={pendingJobs == null ? "Live status" : pendingJobs ? "Awaiting approval" : "Clear"}
          />
        </div>
      </section>

      <div className="rd-v2-settings-statement">
        <StatementSection title="Faculty identity">
          <div className="rd-v2-settings-row stack">
            <input
              type="email"
              className="rd-v2-input"
              placeholder="faculty@yzu.edu.tw"
              value={emailDraft}
              onChange={(e) => setEmailDraft(e.target.value)}
            />
            <button type="button" className="rd-v2-btn sm primary" onClick={saveEmail}>
              Save
            </button>
          </div>
          <p className="rd-v2-settings-hint">Used for profile-aware Discover ranking and procurement chat.</p>
        </StatementSection>

        <StatementSection title="Assistant and procurement">
          <StatementRow
            label="Ask / Composer"
            metric={healthLoaded ? (composerReady ? "Ready" : "Not configured") : "Connecting…"}
            sublabel={desk.brain || desk.composer_model || "cursor_composer"}
            detail={composerReady ? "OK" : "KEY"}
            warn={healthLoaded && !composerReady}
          />
          <StatementRow
            label="MCP tools"
            metric={healthLoaded ? (toolCount ? `${toolCount}` : "Not reported") : "Connecting…"}
            sublabel="Procurement + ops tool registry"
            detail={healthLoaded ? (toolCount ? "Loaded" : "Check API") : "Live status"}
            warn={healthLoaded && !toolCount}
          />
        </StatementSection>

        <StatementSection title="Credentials">
          <StatementRow label="BigQuery SA" metric="Configured" sublabel="Service account" detail="OK" />
          <StatementRow
            label="GDrive OAuth"
            metric={!healthLoaded ? "Connecting…" : desk.gdrive?.ok === false ? "Needs review" : "Configured"}
            sublabel="Archive vault"
            detail={!healthLoaded ? "Live status" : desk.gdrive?.ok === false ? "FAIL" : "OK"}
            warn={healthLoaded && desk.gdrive?.ok === false}
          />
          <StatementRow label="DataCite token" metric="Optional" sublabel="DOI collection" detail="Add when needed" />
        </StatementSection>

        <StatementSection title="Display preferences">
          <div className="rd-v2-settings-row">
            <span>Default tab</span>
            <select
              value={settings.defaultTab}
              onChange={(e) => patch({ defaultTab: e.target.value })}
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
            <span>On select</span>
            <select
              value={settings.onSelect}
              onChange={(e) => patch({ onSelect: e.target.value })}
              className="rd-v2-select"
            >
              <option value="detail">Detail</option>
              <option value="ask">Ask</option>
            </select>
          </div>
        </StatementSection>

        <StatementSection title="Diagnostics">
          <StatementRow label="Query engine" metric=":8765" sublabel="Research API" detail="Open /api/health" onClick={() => window.open("/api/health", "_blank")} />
          <StatementRow label="Vite desk" metric={deskPort} sublabel="Frontend" detail="Open app" onClick={() => window.open(window.location.origin, "_blank")} />
          <StatementRow
            label="Jobs"
            metric={pendingJobs == null ? "Connecting…" : `${pendingJobs} pending`}
            sublabel="Operations"
            detail="Review in Discover"
          />
        </StatementSection>
      </div>
    </PageShell>
  );
}
