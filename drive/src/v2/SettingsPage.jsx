import { useState } from "react";
import {
  clearDeskToken,
  deskSessionBootstrapped,
  hasDeskToken,
  saveDeskToken,
  saveUserEmail,
} from "@/v2/deskSession";
import { clearDeskSession, ensureDeskSession } from "@/v2/api";
import { loadSettings, saveSettings } from "@/v2/settingsStore";
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
  return { ok: true, label: "Connected", detail: "Research archive" };
}

function SummaryCard({ label, value, detail }) {
  return (
    <article className="rd-v2-settings-summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{detail}</em>
    </article>
  );
}

export function SettingsPage({ health, onProfileRefresh, onToast }) {
  const [settings, setSettings] = useState(() => loadSettings());
  const [emailDraft, setEmailDraft] = useState(() => settings.email || "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const desk = health?.desk || {};
  const access = deskAccessStatus(health);
  const archive = archiveStatus(desk);
  const assistantReady = Boolean(desk.composer_configured);

  const patch = (p) => setSettings(saveSettings(p));

  const saveEmail = () => {
    const email = saveUserEmail(emailDraft);
    patch({ email });
    onProfileRefresh?.();
    onToast?.(email ? `Research profile loaded for ${email}` : "Research profile email cleared");
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
    <PageShell title="Settings" lead="Identity, access, and research-desk preferences">
      <div className="rd-v2-settings-statement">
        <section className="rd-v2-settings-summary" aria-label="Research desk status">
          <SummaryCard label="Browser access" value={access.label} detail={access.detail} />
          <SummaryCard
            label="Research assistant"
            value={assistantReady ? "Ready" : "Needs setup"}
            detail={assistantReady ? "Ask and acquisition planning" : "Composer runtime unavailable"}
          />
          <SummaryCard label="Archive" value={archive.label} detail={archive.detail} />
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
          </div>
          <p className="rd-v2-settings-hint">
            Used to load research memory and improve source ranking, evidence-fit explanations, and Ask context.
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
            Authorized internal entry connects automatically. The fallback below is only for a browser that cannot establish that session.
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
            metric={assistantReady ? "Ready" : "Needs setup"}
            sublabel="Search holdings, explain gaps, and prepare reviewable collection plans"
            detail={assistantReady ? "OK" : "CHECK"}
            warn={!assistantReady}
          />
          <StatementRow
            label="Research archive"
            metric={archive.label}
            sublabel="Verified long-term storage for registered research assets"
            detail={archive.ok ? "OK" : "CHECK"}
            warn={!archive.ok}
          />
          <StatementRow
            label="Remote tables"
            metric="Available"
            sublabel="Dry-run protected access for large public datasets"
            detail="READY"
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
            <StatementRow label="Development desk" metric=":5178" sublabel="Local frontend preview" detail="DEV" />
            <StatementRow
              label="Assistant runtime"
              metric={desk.brain || desk.composer_model || "cursor_composer"}
              sublabel="Private orchestration authority"
              detail={assistantReady ? "READY" : "CHECK"}
              warn={!assistantReady}
            />
          </div>
        </details>
      </div>
    </PageShell>
  );
}
