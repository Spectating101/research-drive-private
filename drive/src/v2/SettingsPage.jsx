import { useState } from "react";
import {
  clearDeskToken,
  deskSessionBootstrapped,
  hasDeskToken,
  saveDeskToken,
  saveUserEmail,
} from "@/v2/deskSession";
import { clearDeskSession, ensureDeskSession } from "@/v2/api";
import { ContextHelp } from "@/v2/InteractionGuidance";
import { loadSettings, saveSettings } from "@/v2/settingsStore";
import { PILOT_PREVIEW_EMAIL } from "@/v2/profileViewModel";
import { PageShell, StatementRow, StatementSection } from "@/v2/ui";
import { V2_TABS } from "@/v2/nav-config.jsx";

function deskAccessStatus(health) {
  const desk = health?.desk || {};
  if (hasDeskToken()) return { ok: true, label: "Connected", detail: "Session fallback" };
  if (deskSessionBootstrapped() || desk.desk_session_cookie) {
    return { ok: true, label: "Connected", detail: "Browser session" };
  }
  if (desk.desk_token_required) return { ok: false, label: "Needs connection", detail: "Authorization required" };
  return { ok: true, label: "Open", detail: "No write token required" };
}

function archiveStatus(desk) {
  if (desk?.gdrive?.ok === false) return { ok: false, label: "Needs review", detail: "Archive connection" };
  if (desk?.gdrive?.ok === true) return { ok: true, label: "Connected", detail: "Research archive" };
  return { ok: null, label: "Not reported", detail: "No archive health on /health" };
}

function assistantStatus(health) {
  const desk = health?.desk || {};
  const explicit = desk.composer_configured;
  const legacy = desk.legacy_llm_configured;
  const model = String(desk.composer_model || desk.brain || "").trim();

  if (explicit === true || legacy === true) {
    return {
      ready: true,
      known: true,
      label: "Ready",
      detail: model ? `${model} runtime` : "Ask and acquisition planning",
    };
  }
  if (explicit === false && legacy !== true) {
    return { ready: false, known: true, label: "Needs setup", detail: "Assistant health reports offline" };
  }
  if (model) {
    return { ready: true, known: true, label: "Ready", detail: `${model} runtime signal` };
  }
  return { ready: false, known: false, label: "Not reported", detail: "No assistant signal on /health" };
}

function jobsStatus(health) {
  const jobs = health?.desk?.jobs || {};
  const failed = Number(jobs.failed_recent ?? jobs.failed ?? 0);
  const pending = Number(jobs.pending_approval ?? 0);
  const running = Number(jobs.running ?? 0);
  if (!health?.desk?.jobs) {
    return { label: "Not reported", detail: "Job counters missing from /health", warn: false };
  }
  if (pending > 0) return { label: `${pending} pending approval`, detail: "Discover owns approvals", warn: true };
  if (running > 0) return { label: `${running} running`, detail: "Active collection / execution", warn: false };
  if (failed > 0) return { label: `${failed} failed (recent)`, detail: "See Discover History / Resources Usage", warn: true };
  return { label: "Quiet", detail: "No pending or running jobs", warn: false };
}

function SummaryCard({ label, value, detail, help, warn }) {
  return (
    <article className={`rd-v2-settings-summary-card${warn ? " warn" : ""}`}>
      <span>
        {label}
        <ContextHelp content={help} label={`Explain ${label}`} side="bottom" align="start" />
      </span>
      <strong>{value}</strong>
      <em>{detail}</em>
    </article>
  );
}

export function SettingsPage({ health, resourcesRollup, onProfileRefresh, onToast }) {
  const [settings, setSettings] = useState(() => loadSettings());
  const [emailDraft, setEmailDraft] = useState(() => settings.email || "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const desk = health?.desk || {};
  const access = deskAccessStatus(health);
  const archive = archiveStatus(desk);
  const assistant = assistantStatus(health);
  const jobs = jobsStatus(health);
  const mcpTools = resourcesRollup?.ai?.mcp_tools?.total ?? resourcesRollup?.hero?.mcp_tools ?? null;
  const healthOk = health?.status === "ok";

  const patch = (p) => setSettings(saveSettings(p));

  const saveEmail = () => {
    const email = saveUserEmail(emailDraft);
    patch({ email });
    onProfileRefresh?.();
    onToast?.(email ? `Research profile loaded for ${email}` : "Research profile email cleared");
  };

  const bindPilot = () => {
    setEmailDraft(PILOT_PREVIEW_EMAIL);
    const email = saveUserEmail(PILOT_PREVIEW_EMAIL);
    patch({ email });
    onProfileRefresh?.();
    onToast?.(`Bound EXAMPLE identity ${email}`);
  };

  const connectSession = async () => {
    setBusy(true);
    try {
      const out = await ensureDeskSession({ force: true });
      if (out.ok) onToast?.("Research desk connected for this browser");
      else onToast?.(out.error || "Desk connection failed");
      onProfileRefresh?.();
    } finally {
      setBusy(false);
    }
  };

  const saveToken = () => {
    const saved = saveDeskToken(tokenDraft);
    setTokenDraft("");
    onToast?.(saved ? "Fallback access saved for this browser session" : "Fallback access cleared");
    onProfileRefresh?.();
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      clearDeskToken();
      await clearDeskSession();
      onToast?.("Research desk disconnected");
      onProfileRefresh?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageShell title="Settings" lead="Identity, access, and research-desk preferences — status from live /health only">
      <div className="rd-v2-settings-statement">
        <section className="rd-v2-settings-summary" aria-label="Research desk status">
          <SummaryCard
            label="Desk API"
            value={healthOk ? "Live" : health?.status || "Unknown"}
            detail={healthOk ? "Catalog · Ask · jobs reachable" : "Health payload missing or degraded"}
            help="Truth from GET /health on the Tailscale desk."
            warn={!healthOk}
          />
          <SummaryCard
            label="Research assistant"
            value={assistant.label}
            detail={assistant.detail}
            help="Composer / legacy assistant flags from /health.desk — never invents Ready."
            warn={!assistant.ready}
          />
          <SummaryCard
            label="Jobs"
            value={jobs.label}
            detail={jobs.detail}
            help="Pending / running / recent failed counters from /health.desk.jobs."
            warn={jobs.warn}
          />
        </section>

        <StatementSection title="Research identity">
          <div className="rd-v2-settings-row stack">
            <input
              type="email"
              className="rd-v2-input"
              placeholder="faculty@yzu.edu.tw"
              value={emailDraft}
              onChange={(e) => setEmailDraft(e.target.value)}
            />
            <button type="button" className="rd-v2-btn sm primary" onClick={saveEmail}>
              Save identity
            </button>
            <button type="button" className="rd-v2-btn sm" onClick={bindPilot}>
              Use EXAMPLE (Kong)
            </button>
          </div>
          <p className="rd-v2-settings-hint">
            Loads Memory / Works / Lab from the faculty registry. Unbound desks preview EXAMPLE only until an email is saved.
          </p>
        </StatementSection>

        <StatementSection title="Desk access">
          <StatementRow
            label="This browser"
            metric={access.label}
            sublabel={access.detail}
            detail={access.ok ? "OK" : "NEED"}
            warn={!access.ok}
          />
          <div className="rd-v2-settings-row stack">
            <button type="button" className="rd-v2-btn sm primary" disabled={busy} onClick={connectSession}>
              Connect browser
            </button>
            <button type="button" className="rd-v2-btn sm" disabled={busy} onClick={disconnect}>
              Disconnect
            </button>
          </div>
          <p className="rd-v2-settings-hint">
            Authorized internal entry connects automatically. Fallback token is only for browsers that cannot mint a session cookie.
          </p>
          <div className="rd-v2-settings-row stack">
            <input
              type="password"
              className="rd-v2-input"
              placeholder="Fallback access token"
              value={tokenDraft}
              autoComplete="off"
              onChange={(e) => setTokenDraft(e.target.value)}
            />
            <button type="button" className="rd-v2-btn sm" disabled={busy || !tokenDraft.trim()} onClick={saveToken}>
              Save fallback
            </button>
          </div>
        </StatementSection>

        <StatementSection title="Research services">
          <StatementRow
            label="Ask and acquisition planning"
            metric={assistant.label}
            sublabel={assistant.detail}
            detail={assistant.ready ? "OK" : assistant.known ? "CHECK" : "UNKNOWN"}
            warn={!assistant.ready}
          />
          <StatementRow
            label="Research archive"
            metric={archive.label}
            sublabel={archive.detail}
            detail={archive.ok === true ? "OK" : archive.ok === false ? "CHECK" : "UNKNOWN"}
            warn={archive.ok === false}
          />
          <StatementRow
            label="Desk equipment"
            metric={mcpTools != null ? `${mcpTools} MCP tools` : "Not reported"}
            sublabel="From desk resources rollup when available — not a faculty ops console"
            detail={mcpTools != null ? "REPORTED" : "UNKNOWN"}
          />
          <StatementRow
            label="Browser access"
            metric={access.label}
            sublabel={access.detail}
            detail={access.ok ? "OK" : "NEED"}
            warn={!access.ok}
          />
        </StatementSection>

        <StatementSection title="Display">
          <div className="rd-v2-settings-row">
            <span>Open Research Drive on</span>
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
            <span>When an object is selected</span>
            <select
              value={settings.onSelect}
              onChange={(e) => patch({ onSelect: e.target.value })}
              className="rd-v2-select"
            >
              <option value="detail">Show Detail</option>
              <option value="ask">Open Ask</option>
            </select>
          </div>
        </StatementSection>

        <details className="rd-v2-settings-advanced">
          <summary>Advanced connection details</summary>
          <div className="rd-v2-settings-advanced-body">
            <StatementRow label="Research API" metric=":8765" sublabel="Catalog, Ask, jobs, and query service" detail="INTERNAL" />
            <StatementRow
              label="Assistant runtime"
              metric={desk.brain || desk.composer_model || "Not reported"}
              sublabel="Private orchestration authority from /health"
              detail={assistant.ready ? "READY" : assistant.known ? "CHECK" : "UNKNOWN"}
              warn={!assistant.ready}
            />
          </div>
        </details>
      </div>
    </PageShell>
  );
}
