import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./styles.css";
import "./drive-visual.css";
import { DeskHeader } from "@/app/DeskHeader";
import { DeskInspector } from "@/app/DeskInspector";
import { DeskSidebar } from "@/app/DeskSidebar";
import { cn } from "@/lib/utils";
import {
  consumerDatasetPath,
  DRIVE_LAB,
  DRIVE_MY,
  datasetDriveScope,
  driveRootName,
  filterDatasetsByScope,
  folderLabel,
} from "./driveTree.js";
import { filterDatasetsForProfile, pickProfileShowcase } from "./profileDrive.js";
import {
  clusterRecommendations,
  primaryTrackTitle,
  profileStarterClickables,
  recommendationClickAction,
} from "./profileRecommendations.js";

const API = import.meta.env.DEV ? "/api" : "";
const EMAIL_KEY = "procure_user_email";
const TOKEN_KEY = "desk_access_token";
const YZU_EMAIL_RE = /@((saturn|staff|student)\.)?yzu\.edu\.tw$/i;

function deskHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) headers["X-Desk-Token"] = token;
  return headers;
}

const DESK_VIEW = "home";
const DRIVE_VIEW = "drive";
const MY_DRIVE_VIEW = "my-drive";
const LAB_DRIVE_VIEW = "lab-drive";
const RECENT_VIEW = "recent";
const STARRED_VIEW = "starred";
const CLUSTER_VIEW = "cluster";
const CHAT_VIEW = "chat";
const BROWSE_VIEW = "browse";
const DATASET_VIEW = "dataset";
const DRIVE_VIEWS = new Set([DRIVE_VIEW, MY_DRIVE_VIEW, LAB_DRIVE_VIEW]);

const RECENT_KEY = "rd_recent_datasets";
const STARRED_KEY = "rd_starred_datasets";

const NAV_SECTIONS = [
  {
    label: "Internal",
    items: [
      [DESK_VIEW, "Home", "start", "home"],
      [RECENT_VIEW, "Recent", "recent", "recent"],
      [STARRED_VIEW, "Starred", "starred", "star"],
      [DRIVE_VIEW, "Drive", "drive", "folder-drive"],
      [CLUSTER_VIEW, "Cluster", "cluster", "cluster"],
    ],
  },
  {
    label: "Procure",
    items: [
      ["recommended", "Discover", "rec", "spark"],
    ],
  },
  {
    label: "Tools",
    items: [
      [CHAT_VIEW, "Chat", "chat", "chat"],
      ["dashboard", "Activity", "live", "pulse"],
    ],
  },
];

const NAV_ICONS = {
  home: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  ),
  "folder-user": (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 8a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Z" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  ),
  "folder-lab": (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 7a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3 10h18" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  ),
  spark: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m12 3 1.6 4.9L18 9.4l-4.4 1.5L12 16l-1.6-5.1L6 9.4l4.4-1.5L12 3Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  ),
  pulse: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 12h3l2-5 4 10 2-5h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  recent: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 8v4l3 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  ),
  star: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m12 4 2.2 4.5 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5L5 9.2l5-.7L12 4Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  ),
  "folder-drive": (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 8a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Z" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  ),
  cluster: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="7" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="17" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="17" r="2.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 8.5 11 14M15 8.5 13 14M9.5 8.5h5" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  ),
  chat: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9l-4 3V6Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  ),
};

function loadRecentEntries() {
  try {
    const raw = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

function touchRecentDataset(datasetId) {
  if (!datasetId) return;
  const cur = loadRecentEntries().filter((e) => (e.id || e) !== datasetId);
  cur.unshift({ id: datasetId, at: Date.now() });
  localStorage.setItem(RECENT_KEY, JSON.stringify(cur.slice(0, 40)));
}

function loadStarredIds() {
  try {
    const raw = JSON.parse(localStorage.getItem(STARRED_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw : []);
  } catch {
    return new Set();
  }
}

function saveStarredIds(ids) {
  localStorage.setItem(STARRED_KEY, JSON.stringify([...ids]));
}

const SIDEBAR_FILTERS = [
  ["all", "All", "all"],
  ["available", "Available", "ready"],
  ["connected", "Connected", "query"],
  ["archived", "Archived", "drive"],
];

const ADMIN_VIEWS = [
  ["jobs", "Jobs"],
  ["credentials", "Vault"],
  ["workers", "Workers"],
];

const SHOWCASE_ORDER = [
  "coingecko_simple_price",
  "gdelt_asia_daily_country_panel",
  "gdelt_high_priority_urls",
  "ethereum_usdt_transfers",
  "cross_asset_fused_primary_panel",
  "ticker_week_country_broadcast_panel",
];

const FACULTY_KIND_LABELS = {
  coingecko_simple_price: "SQLite database + panels",
  gdelt_asia_daily_country_panel: "Country-day panel",
  gdelt_high_priority_urls: "Monthly event partitions",
  ethereum_usdt_transfers: "Remote table + planned panels",
  cross_asset_fused_primary_panel: "Country-week panel",
  ticker_week_country_broadcast_panel: "Ticker-week panel",
};

const FACULTY_SUMMARIES = {
  coingecko_simple_price: "Historical crypto prices, market caps, volumes, categories, exchanges, and daily update reports.",
  gdelt_asia_daily_country_panel: "Country-level macro, trade, governance, political, geopolitical, financial stress, health, and environmental news-risk measures.",
  gdelt_high_priority_urls: "High-priority market-relevant URL samples for article discovery and event explanations.",
  ethereum_usdt_transfers: "USDT-on-Ethereum transfer data accessed through BigQuery for historical panels and RPC for live updates.",
  cross_asset_fused_primary_panel: "Fused country-week panel joining news, market, and cross-asset signals for event studies.",
  ticker_week_country_broadcast_panel: "Ticker-week news and market panel with country broadcast attribution.",
};

const GENERIC_STARTERS = [
  "What datasets does the lab already have?",
  "Source a dataset we do not have yet",
];

function buildAssistantActions({ selectedDataset, view, profile }) {
  if (selectedDataset) {
    const name = datasetDisplayName(selectedDataset);
    return [
      { label: "Preview", prompt: `Preview ${name} and summarize columns` },
      { label: "Research uses", prompt: `How can I use ${name} in my research?` },
      { label: "Find related", prompt: `Find datasets related to ${name}` },
    ];
  }
  if (view === "recommended") {
    if (profile && !profile.unknown) {
      const { chatStarters } = profileStarterClickables(profile);
      return (chatStarters.length ? chatStarters : []).slice(0, 4).map((s) => ({
        label: s.label,
        prompt: s.prompt,
      }));
    }
    return [
      { label: "Search the web", prompt: "Help me find and acquire external datasets for my topic" },
      { label: "Browse the library", prompt: "What datasets does the lab already have?" },
    ];
  }
  const discipline = profile?.discipline || profile?.domain_tags?.[0];
  if (discipline && !profile?.unknown) {
    return [
      { label: `Browse ${discipline}`, prompt: `What datasets do we have for ${discipline}?` },
      { label: "Source new data", prompt: "Help me source a dataset we do not have yet" },
    ];
  }
  return GENERIC_STARTERS.map((prompt) => ({
    label: prompt.endsWith("?") ? prompt.replace(/\?$/, "") : prompt,
    prompt,
  }));
}

const SOURCE_STARTERS = [
  "Source a dataset we do not have yet",
  "Find open data for my research topic",
  "Acquire and collect from the web",
];

function useResearchSession() {
  const [email, setEmail] = useState(() => localStorage.getItem(EMAIL_KEY) || "");
  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);

  const loadProfile = useCallback(async (addr) => {
    const normalized = (addr || "").trim().toLowerCase();
    if (!normalized) {
      setProfile(null);
      return;
    }
    setProfileLoading(true);
    try {
      const data = await fetch(`${API}/library/faculty/profile?email=${encodeURIComponent(normalized)}`).then((r) => r.json());
      setProfile(data.found ? data.profile : { email: normalized, unknown: true });
    } catch {
      setProfile({ email: normalized, unknown: true });
    } finally {
      setProfileLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile(email);
  }, [email, loadProfile]);

  const signIn = useCallback((addr) => {
    const normalized = (addr || "").trim().toLowerCase();
    if (!normalized.includes("@") || !YZU_EMAIL_RE.test(normalized)) return false;
    localStorage.setItem(EMAIL_KEY, normalized);
    setEmail(normalized);
    return true;
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(EMAIL_KEY);
    localStorage.removeItem("procure_session_id");
    setEmail("");
    setProfile(null);
  }, []);

  return { email, profile, profileLoading, signIn, signOut };
}

function accountInitials(profile, email) {
  const name = (profile?.name_en || "").trim();
  if (name.includes(",")) return name.split(",")[0].slice(0, 2).toUpperCase();
  if (name) return name.split(/\s+/).pop().slice(0, 2).toUpperCase();
  return (email || "?").slice(0, 2).toUpperCase();
}

function SidebarAccount({ session, deskHealth, loginError, setLoginError, onSignIn, onSignOut }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(() => localStorage.getItem(EMAIL_KEY) || "");
  const [tokenDraft, setTokenDraft] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const label = session.profile ? facultyFormalLabel(session.profile) : session.email || "Sign in";
  const tokenRequired = Boolean(deskHealth?.desk?.desk_token_required);

  function submitSignIn() {
    onSignIn(draft, tokenDraft);
  }

  return (
    <div className="yzu-account-wrap">
      <button type="button" className="yzu-account-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="yzu-account-avatar">{session.email ? accountInitials(session.profile, session.email) : "YZ"}</span>
        <span className="yzu-account-copy">
          <strong>{session.email ? label : "Sign in"}</strong>
          <small>{session.email ? session.email : "Personalize your desk"}</small>
        </span>
      </button>
      {open && (
        <div className="yzu-account-panel">
          {session.email ? (
            <>
              <p className="muted small">{session.email}</p>
              <button type="button" className="yzu-chip small" onClick={() => { onSignOut(); setOpen(false); }}>
                Sign out
              </button>
            </>
          ) : (
            <>
              <p className="muted small">YZU faculty email for personalized starters and collect approvals.</p>
              {loginError && <p className="yzu-login-error">{loginError}</p>}
              <label className="yzu-login-label">
                <span>Email</span>
                <input
                  type="email"
                  value={draft}
                  onChange={(e) => { setDraft(e.target.value); setLoginError(""); }}
                  placeholder="you@saturn.yzu.edu.tw"
                  onKeyDown={(e) => e.key === "Enter" && submitSignIn()}
                />
              </label>
              {tokenRequired && (
                <label className="yzu-login-label">
                  <span>Desk token</span>
                  <input
                    type="password"
                    value={tokenDraft}
                    onChange={(e) => setTokenDraft(e.target.value)}
                    placeholder="Optional shared token"
                    onKeyDown={(e) => e.key === "Enter" && submitSignIn()}
                  />
                </label>
              )}
              <button type="button" className="primary" disabled={session.profileLoading} onClick={submitSignIn}>
                {session.profileLoading ? "Loading…" : "Continue"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function NavIcon({ kind }) {
  return <span className="rd-nav-icon">{NAV_ICONS[kind] || NAV_ICONS.home}</span>;
}

function scopeDisplayLabel(scope) {
  if (scope === DRIVE_MY) return "Uploads";
  if (scope === DRIVE_LAB) return "Lab";
  return "Drive";
}

function PageBar({ title, subtitle, children, compact = false, kicker }) {
  return (
    <header className={`rd-page-bar ${compact ? "rd-page-bar-workspace" : ""} ${kicker ? "rd-page-bar--kicker" : ""}`}>
      <div className="rd-page-bar-copy">
        {kicker ? <p className="rd-kicker">{kicker}</p> : null}
        <h1>{title}</h1>
        {subtitle ? <p className="rd-page-sub">{subtitle}</p> : null}
      </div>
      {children ? <div className="rd-page-actions">{children}</div> : null}
    </header>
  );
}

function HeaderStatus({ datasetCount = 0, connectedCount = 0, workCount = 0 }) {
  return (
    <div className="rd-header-status" aria-label="Desk status">
      <span><strong>{datasetCount}</strong> datasets</span>
      <span><strong>{connectedCount}</strong> query links</span>
      <span className={workCount > 0 ? "active" : ""}><strong>{workCount}</strong> jobs</span>
    </div>
  );
}

function HomeCapabilityStrip({ totalCount = 0, verifiedCount = 0, connectedCount = 0, workCount = 0, reviewCount = 0 }) {
  const cells = [
    ["Library", totalCount, "cataloged datasets"],
    ["Verified", verifiedCount, "ready for analysis"],
    ["Connected", connectedCount, "remote/query sources"],
    ["Review", reviewCount + workCount, "jobs and intake checks"],
  ];
  return (
    <div className="rd-home-capability" aria-label="Library status">
      {cells.map(([label, value, note]) => (
        <div className="rd-home-capability-cell" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{note}</small>
        </div>
      ))}
    </div>
  );
}

function AssistantActionChips({ actions = [], onAction, className = "" }) {
  if (!actions.length) return null;
  return (
    <div className={`rd-assistant-chips ${className}`.trim()} role="group" aria-label="Assistant suggestions">
      {actions.map((action) => (
        <button
          key={action.prompt}
          type="button"
          className="rd-chip subtle"
          onClick={() => onAction?.(action.prompt)}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}

function SmartProcureBar({ placeholder, actions = [], onSubmit, onAction }) {
  const [draft, setDraft] = useState("");
  const hint = placeholder || "Describe a dataset, DOI, URL, or source to procure...";

  function submit() {
    const q = draft.trim();
    if (!q) return;
    onSubmit?.(q);
    setDraft("");
  }

  return (
    <section className="rd-smart-procure" aria-label="Smart procurement">
      <div className="rd-smart-procure-head">
        <strong>Source with Composer</strong>
        <span className="muted">Local index, web probe, queued collection, vault promotion</span>
      </div>
      <div className="rd-smart-procure-compose">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={hint}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button type="button" className="primary" onClick={submit} disabled={!draft.trim()}>
          Source
        </button>
      </div>
      <AssistantActionChips actions={actions} onAction={onAction} />
    </section>
  );
}

function SelectionToolbar({ dataset, onOpen, onClear, onSourcePrompt }) {
  if (!dataset) return null;
  const name = datasetDisplayName(dataset);
  return (
    <div className="rd-selection-bar" role="toolbar" aria-label="Selected dataset">
      <span className="rd-selection-name">{name}</span>
      <div className="rd-selection-actions">
        <button type="button" className="yzu-chip small" onClick={() => onOpen?.(dataset)}>
          Open
        </button>
        <button
          type="button"
          className="yzu-chip small"
          onClick={() => onSourcePrompt?.(`Preview ${name} and summarize columns`)}
        >
          Preview
        </button>
        <button
          type="button"
          className="yzu-chip small"
          onClick={() => onSourcePrompt?.(`Find datasets related to ${name}`)}
        >
          Find related
        </button>
        <button type="button" className="rd-scope-clear" onClick={onClear}>
          Clear
        </button>
      </div>
    </div>
  );
}

function SignInBanner({ onSignIn }) {
  return (
    <div className="rd-signin-banner" role="region" aria-label="Sign in">
      <div>
        <strong>Sign in with your YZU email</strong>
        <p>Personalized dataset matches and collect approvals.</p>
      </div>
      <button type="button" className="primary" onClick={onSignIn}>Sign in</button>
    </div>
  );
}

function NewActionSheet({ open, onClose, onSource, onOpenMyDrive }) {
  if (!open) return null;
  return (
    <div className="rd-sheet-backdrop" role="presentation" onClick={onClose}>
      <div className="rd-sheet" role="dialog" aria-labelledby="new-sheet-title" onClick={(e) => e.stopPropagation()}>
        <header className="rd-sheet-head">
          <h2 id="new-sheet-title">New</h2>
          <button type="button" className="rd-sheet-close" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <div className="rd-sheet-menu">
          <button type="button" className="rd-sheet-menu-item" onClick={() => { onClose(); onSource(); }}>
            <span className="rd-sheet-menu-label">Source dataset</span>
            <span className="rd-sheet-menu-hint">Ask the assistant to find and collect</span>
          </button>
          <button type="button" className="rd-sheet-menu-item" onClick={() => { onClose(); onOpenMyDrive(); }}>
            <span className="rd-sheet-menu-label">Upload file</span>
            <span className="rd-sheet-menu-hint">Add to My Drive</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function StorageStrip({ tiers }) {
  if (!tiers) return null;
  const cache = tiers.cache || {};
  const hot = tiers.hot || {};
  return (
    <div className="rd-storage-strip" aria-label="Storage status">
      <span className="rd-storage-pill vault" title={tiers.canonical?.drive_root}>Vault · GDrive</span>
      <span className={`rd-storage-pill cache ${cache.mounted ? "ok" : "off"}`}>
        {cache.mounted ? `Cache · ${cache.free_gb ?? "?"} GB free` : "Cache offline"}
      </span>
      <span className={`rd-storage-pill hot ${hot.headroom_ok === false ? "warn" : ""}`}>
        Desk · {hot.free_gb ?? "?"} GB
      </span>
    </div>
  );
}

function facultyFormalLabel(profile) {
  if (!profile) return "";
  const titleRaw = (profile.title || "Professor").split(",")[0].trim();
  let titleShort = "Prof.";
  if (/assistant professor/i.test(titleRaw)) titleShort = "Asst. Prof.";
  else if (/associate professor/i.test(titleRaw)) titleShort = "Assoc. Prof.";
  else if (/professor/i.test(titleRaw)) titleShort = "Prof.";

  const name = (profile.name_en || "").trim();
  let surname = "";
  if (name.includes(",")) surname = name.split(",")[0].trim();
  else if (name) surname = name.split(/\s+/).pop() || "";

  return surname ? `${titleShort} ${surname}` : titleShort;
}

function fmtTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value.slice(0, 19) : d.toLocaleString();
}

function slugLabel(v) {
  return String(v || "").toLowerCase().replace(/\s+/g, "-");
}

function datasetAvailability(d) {
  const access = `${d.access_shape || ""} ${d.backend || ""}`.toLowerCase();
  if (access.includes("remote") || access.includes("bigquery") || access.includes("query")) return "Connected";
  if (access.includes("archive")) return "Archived";
  return "Stored";
}

function datasetTrust(d) {
  const readiness = String(d.analysis_readiness || "").toLowerCase();
  if (readiness === "instant" || readiness === "instant_or_minutes") return "Verified";
  if (readiness === "metadata_search" || readiness === "metadata_only") return "Catalog only";
  if (readiness === "sample_now_full_later") return "Sample";
  if (readiness === "dry_run_before_execution") return "Needs approval";
  if (readiness === "procurement_planning") return "Plan needed";
  if (d.domain === "web_scrape") return "Needs review";
  return "Ready";
}

function datasetStatus(d) {
  const readiness = String(d.analysis_readiness || "").toLowerCase();
  if (readiness === "instant" || readiness === "instant_or_minutes") return "Query-ready";
  if (readiness === "metadata_search" || readiness === "metadata_only") return "Needs collection";
  if (readiness === "sample_now_full_later") return "Sample ready";
  if (readiness === "dry_run_before_execution") return "Approval gated";
  if (readiness === "procurement_planning") return "Plan first";
  if (readiness === "minutes_rate_limited") return "Rate-limited";
  return "Updating";
}

const FACULTY_HIDDEN_DATASETS = new Set([
  "collection_queue_status",
  "datacite_local_harvest_status",
  "procurement_source_registry",
  "external_dataset_catalog",
  "external_dataset_catalog_curated",
  "test_sec",
  "procured_sec_tickers_test",
]);

const FACULTY_DISPLAY_NAMES = {
  gdelt_asia_daily_country_panel: "Asia daily news-risk panel",
  gdelt_high_priority_urls: "GDELT article samples",
  coingecko_simple_price: "CoinGecko crypto market archive",
  ethereum_usdt_transfers: "Ethereum USDT transfer catalogue",
  cross_asset_fused_primary_panel: "Cross-asset country-week panel",
  ticker_week_country_broadcast_panel: "Asia ticker news-market panel",
  ticker_week_entity_market_panel: "Ticker-level news-market panel",
  ticker_week_entity_long_panel: "Ticker long panel",
  ticker_week_entity_residual_panel: "Ticker residual panel",
  sec_company_tickers: "SEC company tickers",
  sec_sp500_submissions: "SEC EDGAR filings (S&P 500)",
  asia_entity_ticker_mapping_layer: "Asia entity-to-ticker mapping",
};

const DATASET_KIND_LABELS = {
  country_day: "Country-day panel",
  url_event: "URL index",
  dataset_record: "Catalogue",
  week_country: "Country-week panel",
  week_ticker: "Ticker-week panel",
};

function isFacultyFacingDataset(d) {
  if (!d?.dataset_id) return false;
  if (FACULTY_HIDDEN_DATASETS.has(d.dataset_id)) return false;
  if (d.dataset_id.startsWith("scrape_") && datasetTrust(d) === "Needs review") return false;
  return true;
}

function datasetDisplayName(d) {
  if (FACULTY_DISPLAY_NAMES[d.dataset_id]) return FACULTY_DISPLAY_NAMES[d.dataset_id];
  const name = d.name || d.dataset_id || "";
  if (/^web scrape/i.test(name)) return "Uploaded web sample";
  if (name.length > 52) return `${name.slice(0, 49)}…`;
  return name;
}

function datasetOwner(d) {
  if (d.dataset_id === "ethereum_usdt_transfers") return "Google Blockchain Analytics";
  const name = `${d.name || ""} ${d.dataset_id || ""}`;
  if (/coingecko/i.test(name)) return "CoinGecko API";
  if (/gdelt/i.test(name)) return "GDELT + classifier";
  if (/bigquery|usdt|ethereum/i.test(name)) return "BigQuery";
  if (/sec/i.test(name)) return "SEC";
  if (d.domain === "web_scrape") return "Lab upload";
  return "Lab";
}

function datasetKind(d) {
  if (DATASET_KIND_LABELS[d.grain]) return DATASET_KIND_LABELS[d.grain];
  const backend = String(d.backend || "");
  if (backend.includes("sqlite")) return "Database";
  if (backend.includes("csv")) return "CSV panels";
  if (backend.includes("bigquery")) return "Remote table";
  if (backend.includes("jsonl")) return "Metadata index";
  if (d.domain === "web_scrape") return "Uploaded CSV";
  return "Research dataset";
}

function pickShowcaseRegistry(rows) {
  const byId = new Map(rows.map((d) => [d.dataset_id, d]));
  return SHOWCASE_ORDER.map((id) => byId.get(id)).filter(Boolean);
}

function datasetKindLabel(d) {
  return FACULTY_KIND_LABELS[d.dataset_id] || datasetKind(d);
}

function datasetSubtitle(d) {
  if (FACULTY_SUMMARIES[d.dataset_id]) {
    const s = FACULTY_SUMMARIES[d.dataset_id];
    return s.length > 96 ? `${s.slice(0, 93)}…` : s;
  }
  if (FACULTY_KIND_LABELS[d.dataset_id]) return FACULTY_KIND_LABELS[d.dataset_id];
  const use = (d.recommended_use || d.description || "").split(/[.;]/)[0];
  if (use && use.length < 88) return use;
  return datasetKind(d);
}

function datasetSummary(d) {
  if (FACULTY_SUMMARIES[d.dataset_id]) return FACULTY_SUMMARIES[d.dataset_id];
  return d.description || d.recommended_use || d.dataset_id || "";
}

function datasetModified(d) {
  if (d.procurement?.promoted_at) return "Recent";
  if (datasetStatus(d) === "Query-ready") return "Ready";
  return "Maintained";
}

const COLLECTION_LABELS = {
  research_panels: "Research panels",
  procured: "Imported",
  connections: "Connections",
  lab_pipelines: "Automated feeds",
  reference: "Reference",
  uploads: "Uploads",
  other: "Other",
};

function datasetCollectionKey(d, scope = datasetDriveScope(d)) {
  const path = consumerDatasetPath(d, scope);
  return path[0] || "other";
}

function datasetCollectionLabel(d, scope = datasetDriveScope(d)) {
  const key = datasetCollectionKey(d, scope);
  return COLLECTION_LABELS[key] || folderLabel(key);
}

function datasetUpdatedLabel(d) {
  const promoted = d.procurement?.promoted_at;
  if (promoted) {
    const dt = new Date(promoted);
    if (!Number.isNaN(dt.getTime())) {
      return dt.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    }
  }
  if (d.updated_at) {
    const dt = new Date(d.updated_at);
    if (!Number.isNaN(dt.getTime())) {
      return dt.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    }
  }
  if (datasetAvailability(d) === "Connected") return "Live";
  return "Maintained";
}

function datasetShapeLabel(d) {
  const grain = DATASET_KIND_LABELS[d.grain] || datasetKind(d);
  if (d.time_field) return `${grain} · ${d.time_field}`;
  return grain;
}

function datasetIntakeKey(d) {
  const trust = datasetTrust(d);
  if (trust === "Needs review" || trust === "Unverified") return "needs_review";
  if (datasetStatus(d) !== "Query-ready") return "draft";
  return "ready";
}

function datasetIntakeLabel(d) {
  const key = datasetIntakeKey(d);
  if (key === "needs_review") return "Needs review";
  if (key === "draft") return "Draft";
  return "Ready";
}

function datasetMatchesFilter(d, filter) {
  if (filter === "all") return true;
  const availability = datasetAvailability(d).toLowerCase();
  if (filter === "available") return datasetTrust(d) === "Verified" && availability === "stored";
  if (filter === "connected") return availability === "connected";
  if (filter === "archived") return availability === "archived";
  return true;
}

function sortFacultyRegistry(rows) {
  const rank = new Map(SHOWCASE_ORDER.map((id, i) => [id, i]));
  return [...rows].sort((a, b) => {
    const ra = rank.has(a.dataset_id) ? rank.get(a.dataset_id) : 999;
    const rb = rank.has(b.dataset_id) ? rank.get(b.dataset_id) : 999;
    if (ra !== rb) return ra - rb;
    return (a.name || "").localeCompare(b.name || "");
  });
}

function datasetAccessLabel(d) {
  if (d.local_root || d.local_path) return "Local panels + Drive archive";
  if (datasetAvailability(d) === "Connected") return "Remote query; optional archive";
  if (datasetAvailability(d) === "Archived") return "Drive archive";
  return d.access_shape?.replace(/_/g, " ") || "Lab library";
}

function datasetCoverage(d) {
  if (d.time_field) return `From ${d.time_field} field`;
  return "Varies by table";
}

function datasetMatchesSearch(d, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return true;
  const hay = [
    d.name,
    d.dataset_id,
    d.domain,
    d.backend,
    d.description,
    d.recommended_use,
    d.grain,
  ].join(" ").toLowerCase();
  return hay.includes(q);
}

/** Token match for Discover local hits — any word in the query may match. */
function discoverLocalMatches(d, query) {
  const tokens = (query || "").trim().toLowerCase().split(/\s+/).filter((t) => t.length > 1);
  if (!tokens.length) return true;
  const hay = [
    d.name,
    d.dataset_id,
    d.domain,
    d.backend,
    d.description,
    d.recommended_use,
    d.grain,
    d.collection,
  ].join(" ").toLowerCase();
  return tokens.some((t) => hay.includes(t));
}

function StatusPill({ label }) {
  return <span className={`rd-pill ${slugLabel(label)}`}>{label}</span>;
}

function fileIconVariant(dataset) {
  const id = dataset?.dataset_id || "";
  const backend = String(dataset?.backend || "");
  if (/sqlite|database/i.test(backend)) return "db";
  if (/bigquery|remote/i.test(backend)) return "remote";
  if (dataset?.domain === "web_scrape") return "upload";
  if (/jsonl|catalog|index/i.test(backend)) return "meta";
  return "panel";
}

function FileIcon({ live, dataset }) {
  const variant = fileIconVariant(dataset);
  return <div className={`rd-file rd-file-${variant} ${live ? "live" : ""}`} aria-hidden="true" />;
}

function CatalogDatasetRow({
  dataset,
  selected,
  onSelect,
  onOpen,
  scope,
  variant = "lab",
  rowScope,
  starred,
  onToggleStar,
}) {
  const live = datasetStatus(dataset) === "Updating" || datasetAvailability(dataset) === "Connected";
  const trust = datasetTrust(dataset);
  const showTrustWarning = trust === "Needs review" || trust === "Unverified";
  const effectiveScope = rowScope || scope;
  const isMy = effectiveScope === DRIVE_MY;
  const isFeatured = variant === "featured";
  const isMixed = variant === "mixed";
  const subtitle = isFeatured ? datasetSummary(dataset) : datasetSubtitle(dataset);

  return (
    <tr
      className={selected ? "selected" : ""}
      onClick={() => onSelect?.(dataset)}
      onDoubleClick={() => onOpen?.(dataset)}
    >
      <td>
        <div className="rd-name">
          <FileIcon live={live} dataset={dataset} />
          <div>
            <div className="rd-title">{datasetDisplayName(dataset)}</div>
            <div className="rd-sub">{subtitle}</div>
          </div>
          {onToggleStar && (
            <button
              type="button"
              className={`rd-row-star ${starred ? "active" : ""}`}
              aria-label={starred ? "Unstar" : "Star"}
              onClick={(e) => {
                e.stopPropagation();
                onToggleStar(dataset.dataset_id);
              }}
            >
              ★
            </button>
          )}
        </div>
      </td>
      {isFeatured ? (
        <>
          <td className="rd-col-kind rd-col-md muted">{datasetKindLabel(dataset)}</td>
          <td className="rd-col-access">
            <StatusPill label={datasetAvailability(dataset)} />
          </td>
        </>
      ) : isMixed ? (
        <>
          <td className="rd-col-kind rd-col-md muted">{datasetKindLabel(dataset)}</td>
          <td className="rd-col-scope rd-col-md muted">{scopeDisplayLabel(datasetDriveScope(dataset))}</td>
          <td className="rd-col-collection rd-col-md muted">{datasetCollectionLabel(dataset, datasetDriveScope(dataset))}</td>
          <td className="rd-col-updated rd-col-lg muted">{datasetUpdatedLabel(dataset)}</td>
          <td className="rd-col-access">
            <StatusPill label={datasetAvailability(dataset)} />
            {showTrustWarning && <StatusPill label={trust} />}
          </td>
        </>
      ) : isMy ? (
        <>
          <td className="rd-col-status rd-col-md">
            <StatusPill label={datasetIntakeLabel(dataset)} />
          </td>
          <td className="rd-col-updated rd-col-md muted">{datasetUpdatedLabel(dataset)}</td>
          <td className="rd-col-access">
            <StatusPill label={datasetAvailability(dataset)} />
            {showTrustWarning && <StatusPill label={trust} />}
          </td>
        </>
      ) : (
        <>
          <td className="rd-col-kind rd-col-md muted">{datasetKindLabel(dataset)}</td>
          <td className="rd-col-collection rd-col-md muted">{datasetCollectionLabel(dataset, scope)}</td>
          <td className="rd-col-source rd-col-lg muted">{datasetOwner(dataset)}</td>
          <td className="rd-col-updated rd-col-lg muted">{datasetUpdatedLabel(dataset)}</td>
          <td className="rd-col-access">
            <StatusPill label={datasetAvailability(dataset)} />
            {showTrustWarning && <StatusPill label={trust} />}
          </td>
        </>
      )}
    </tr>
  );
}

/** @deprecated use CatalogDatasetRow */
function DatasetTableRow(props) {
  return (
    <CatalogDatasetRow
      dataset={props.dataset}
      selected={props.selected}
      onSelect={props.onSelect}
      onOpen={props.onOpen}
      scope={DRIVE_LAB}
      variant={props.showKind ? "featured" : "lab"}
    />
  );
}

function CatalogTable({
  rows,
  scope,
  selectedDataset,
  onSelectDataset,
  onOpenDataset,
  loading = false,
  variant = "lab",
  emptyMessage = "No datasets match these filters.",
  showScopeColumn = false,
  starredIds,
  onToggleStar,
}) {
  const isMy = scope === DRIVE_MY && !showScopeColumn;
  const isMixed = showScopeColumn;
  const isFeatured = variant === "featured";
  const colCount = isFeatured ? 3 : isMixed ? 6 : isMy ? 4 : 6;
  const tableClass = `rd-catalog-table rd-catalog-table--${isMixed ? "mixed" : variant}${isMy ? " rd-catalog-table--my" : ""}`;

  return (
    <div className="yzu-drive-table rd-catalog-wrap">
      <table className={tableClass}>
        <thead>
          <tr>
            <th>Name</th>
            {isFeatured ? (
              <>
                <th className="rd-col-md">Kind</th>
              </>
            ) : isMixed ? (
              <>
                <th className="rd-col-md">Kind</th>
                <th className="rd-col-md">Scope</th>
                <th className="rd-col-md">Collection</th>
                <th className="rd-col-lg">Updated</th>
              </>
            ) : isMy ? (
              <>
                <th className="rd-col-md">Status</th>
                <th className="rd-col-md">Uploaded</th>
              </>
            ) : (
              <>
                <th className="rd-col-md">Kind</th>
                <th className="rd-col-md">Collection</th>
                <th className="rd-col-lg">Source</th>
                <th className="rd-col-lg">Updated</th>
              </>
            )}
            <th>Access</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr className="rd-skeleton-row">
              <td colSpan={colCount}>
                <div className="rd-skeleton-block wide" />
                <div className="rd-skeleton-block mid" />
              </td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr><td colSpan={colCount} className="muted">{emptyMessage}</td></tr>
          )}
          {!loading && rows.map((d) => (
            <CatalogDatasetRow
              key={d.dataset_id}
              dataset={d}
              selected={selectedDataset?.dataset_id === d.dataset_id}
              onSelect={onSelectDataset}
              onOpen={onOpenDataset}
              scope={scope}
              variant={isMixed ? "mixed" : variant}
              rowScope={showScopeColumn ? datasetDriveScope(d) : undefined}
              starred={starredIds?.has(d.dataset_id)}
              onToggleStar={onToggleStar}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CatalogFacetBar({ children, count, total, loading }) {
  return (
    <div className="rd-catalog-toolbar">
      <div className="rd-catalog-facets">{children}</div>
      <span className="rd-catalog-count muted">
        {loading ? "Loading…" : total != null && count < total ? `Showing ${count} of ${total}` : `${count} items`}
      </span>
    </div>
  );
}

function parseStoredMessage(m, sessionState, isLastAssistant) {
  const artifacts = m.artifacts || {};
  const statePatch = artifacts.state_patch || {};
  return {
    role: m.role,
    text: m.content,
    action: artifacts.action,
    campaignId: statePatch.campaign_id || artifacts.campaign_id || sessionState?.campaign_id,
    preview: artifacts.preview || null,
    candidates: isLastAssistant ? (sessionState?.candidates || artifacts.candidates || []) : [],
    suggestedPrompts: artifacts.suggestions || artifacts.suggested_prompts || [],
    artifacts,
    blocked: artifacts.blocked,
    gate: artifacts.gate,
    pendingJobId: artifacts.job?.id || statePatch.pending_job_id || sessionState?.pending_job_id,
    registryPromotion: artifacts.registry_promotion,
    procuredFiles: artifacts.procured_files || [],
    jobStatus: artifacts.job?.status,
    nextSteps: isLastAssistant ? (artifacts.next_steps || []) : [],
    compareTable: artifacts.compare_table || null,
  };
}

function App() {
  const session = useResearchSession();
  const [view, setView] = useState(DESK_VIEW);
  const [navOpen, setNavOpen] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [deskHealth, setDeskHealth] = useState(null);
  const [status, setStatus] = useState(null);
  const [acquisitions, setAcquisitions] = useState([]);
  const [workers, setWorkers] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [pins, setPins] = useState([]);
  const [activity, setActivity] = useState([]);
  const [registry, setRegistry] = useState([]);
  const [selectedDataset, setSelectedDataset] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [libraryFilter, setLibraryFilter] = useState("all");
  const [adminOpen, setAdminOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [liveLoading, setLiveLoading] = useState(false);
  const [showAllLabData, setShowAllLabData] = useState(false);
  const [driveScope, setDriveScope] = useState("all");
  const [starredIds, setStarredIds] = useState(() => loadStarredIds());
  const [recentTick, setRecentTick] = useState(0);
  const [pendingAskPrompt, setPendingAskPrompt] = useState("");
  const [pendingRailPrompt, setPendingRailPrompt] = useState("");
  const [browseTarget, setBrowseTarget] = useState(null);
  const [inspectorTab, setInspectorTab] = useState("details");
  const [newSheetOpen, setNewSheetOpen] = useState(false);
  const [explicitSelection, setExplicitSelection] = useState(false);
  const [selectionAnchor, setSelectionAnchor] = useState(null);
  const askChatRef = useRef(null);
  const askRailRef = useRef(null);

  const refreshFast = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [s, a, j, ds, pinData] = await Promise.all([
        fetch(`${API}/yzu/status`).then((r) => r.json()),
        fetch(`${API}/yzu/acquisitions`).then((r) => r.json()),
        fetch(`${API}/yzu/jobs?limit=40`).then((r) => r.json()),
        fetch(`${API}/datasets`).then((r) => r.json()),
        fetch(`${API}/library/pins?limit=12`).then((r) => r.json()).catch(() => ({ pins: [] })),
      ]);
      setStatus(s);
      setAcquisitions(a.acquisitions || []);
      setJobs(j.jobs || []);
      setPins(pinData.pins || []);
      const rows = ds.datasets || [];
      setRegistry(rows);
      setSelectedDataset((cur) => {
        if (cur && rows.some((d) => d.dataset_id === cur.dataset_id)) return cur;
        return null;
      });
    } catch (err) {
      setError(err.message || "API unavailable — start scripts/run_yzu_cluster.sh");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshLive = useCallback(async () => {
    setLiveLoading(true);
    try {
      const [w, act] = await Promise.all([
        fetch(`${API}/yzu/workers?live=1`).then((r) => r.json()),
        fetch(`${API}/yzu/activity?live=1`).then((r) => r.json()),
      ]);
      setWorkers(w);
      setActivity(act.events || []);
      const s = await fetch(`${API}/yzu/status?live=1`).then((r) => r.json());
      setStatus(s);
      const a = await fetch(`${API}/yzu/acquisitions?live=1`).then((r) => r.json());
      setAcquisitions(a.acquisitions || []);
    } catch {
      /* keep cached dashboard if live probe fails */
    } finally {
      setLiveLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    await refreshFast();
    refreshLive();
  }, [refreshFast, refreshLive]);

  useEffect(() => {
    refreshFast().then(() => refreshLive());
    const timer = setInterval(refresh, 60000);
    return () => clearInterval(timer);
  }, [refresh, refreshFast, refreshLive]);

  useEffect(() => {
    fetch(`${API}/health?live=1`)
      .then((r) => (r.ok ? r.json() : null))
      .then((h) => h && setDeskHealth(h))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (view === "workers" && !workers && !liveLoading) refreshLive();
  }, [view, workers, liveLoading, refreshLive]);

  useEffect(() => {
    if (!pendingAskPrompt) return;
    const timer = window.setTimeout(() => {
      setView(CHAT_VIEW);
      askChatRef.current?.sendChat(pendingAskPrompt);
      setPendingAskPrompt("");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [pendingAskPrompt]);

  useEffect(() => {
    if (!pendingRailPrompt) return;
    const timer = window.setTimeout(() => {
      setInspectorTab("assistant");
      askRailRef.current?.sendChat(pendingRailPrompt);
      setPendingRailPrompt("");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [pendingRailPrompt]);

  const pendingJobs = status?.jobs?.pending_approval ?? deskHealth?.desk?.jobs?.pending_approval ?? 0;
  const archiveQuota = deskHealth?.desk?.archive?.quota_tb ?? 3;
  const archivePool = deskHealth?.desk?.archive?.pool_tb ?? 5;
  const myDriveRegistry = useMemo(
    () => registry.filter((d) => filterDatasetsByScope([d], DRIVE_MY).length > 0),
    [registry],
  );
  const labDriveRegistry = useMemo(
    () => sortFacultyRegistry(registry.filter((d) => filterDatasetsByScope([d], DRIVE_LAB).length > 0 && isFacultyFacingDataset(d))),
    [registry],
  );
  const facultyRegistry = labDriveRegistry;
  const showcaseRegistry = useMemo(() => {
    if (session.profile && !session.profile.unknown) {
      const picked = pickProfileShowcase(labDriveRegistry, session.profile, 6);
      if (picked.length) return picked;
    }
    return pickShowcaseRegistry(labDriveRegistry);
  }, [labDriveRegistry, session.profile]);
  const labDriveVisible = useMemo(() => {
    if (showAllLabData) return labDriveRegistry;
    if (session.profile && !session.profile.unknown) {
      return filterDatasetsForProfile(labDriveRegistry, session.profile);
    }
    return showcaseRegistry;
  }, [labDriveRegistry, session.profile, showAllLabData, showcaseRegistry]);
  const navDriveCount = labDriveVisible.length + myDriveRegistry.length;
  const recentDatasets = useMemo(() => {
    void recentTick;
    const byId = new Map(registry.map((d) => [d.dataset_id, d]));
    return loadRecentEntries()
      .map((e) => byId.get(e.id || e))
      .filter(Boolean)
      .slice(0, 40);
  }, [registry, recentTick]);
  const starredDatasets = useMemo(
    () => registry.filter((d) => starredIds.has(d.dataset_id)),
    [registry, starredIds],
  );
  const filteredRegistry = useMemo(
    () => labDriveVisible.filter((d) => datasetMatchesFilter(d, libraryFilter) && datasetMatchesSearch(d, searchQuery)),
    [labDriveVisible, libraryFilter, searchQuery],
  );
  const homeRecent = useMemo(
    () => recentDatasets.filter((d) => datasetMatchesSearch(d, searchQuery)).slice(0, 5),
    [recentDatasets, searchQuery],
  );
  const homeSuggested = useMemo(() => {
    const recentIds = new Set(homeRecent.map((d) => d.dataset_id));
    const pool = searchQuery.trim()
      ? filteredRegistry
      : showcaseRegistry;
    return pool.filter((d) => !recentIds.has(d.dataset_id)).slice(0, 6);
  }, [homeRecent, searchQuery, filteredRegistry, showcaseRegistry]);
  const scrapeReviewCount = useMemo(
    () => registry.filter((d) => d.domain === "web_scrape" || datasetTrust(d) === "Needs review").length,
    [registry],
  );
  const isOpsView = ["jobs", "credentials", "workers"].includes(view);
  const hideInspectorViews = new Set([CHAT_VIEW, BROWSE_VIEW, CLUSTER_VIEW, "recommended", "dashboard", ...["jobs", "credentials", "workers"]]);
  const showInspector = !hideInspectorViews.has(view);
  const showStorageStrip = view === "dashboard" || isOpsView;
  const assistantDataset = useMemo(() => {
    if (!selectedDataset || !explicitSelection) return null;
    if (view === DATASET_VIEW) return selectedDataset;
    if (view === selectionAnchor) return selectedDataset;
    return null;
  }, [view, selectedDataset, explicitSelection, selectionAnchor]);
  const isLibraryView = [DESK_VIEW, DRIVE_VIEW, RECENT_VIEW, STARRED_VIEW, DATASET_VIEW].includes(view);
  const assistantContextHint = useMemo(() => {
    if (assistantDataset) {
      return `About ${datasetDisplayName(assistantDataset)}.`;
    }
    if (view === "recommended") return "Describe what to find or acquire from the catalog and open web.";
    if (view === CHAT_VIEW) return "";
    return "Describe a dataset to find, compare, and collect into the lab library.";
  }, [view, assistantDataset]);
  const assistantActions = useMemo(
    () => buildAssistantActions({ selectedDataset: assistantDataset, view, profile: session.profile }),
    [assistantDataset, view, session.profile],
  );
  const runningCount = useMemo(() => acquisitions.filter((r) => r.stage === "running").length, [acquisitions]);
  const headerInitials = session.email ? accountInitials(session.profile, session.email) : "YZ";
  const totalDatasetCount = labDriveRegistry.length + myDriveRegistry.length;
  const connectedDatasetCount = useMemo(
    () => registry.filter((d) => datasetAvailability(d) === "Connected").length,
    [registry],
  );
  const verifiedDatasetCount = useMemo(
    () => registry.filter((d) => datasetTrust(d) === "Verified").length,
    [registry],
  );
  const activeWorkCount = pendingJobs + runningCount;

  useEffect(() => {
    if (isLibraryView) setInspectorTab("details");
  }, [view, isLibraryView]);

  function toggleStar(datasetId) {
    setStarredIds((cur) => {
      const next = new Set(cur);
      if (next.has(datasetId)) next.delete(datasetId);
      else next.add(datasetId);
      saveStarredIds(next);
      return next;
    });
  }

  function openSignIn() {
    document.querySelector(".yzu-account-btn")?.click();
  }

  function openNewSheet() {
    setNewSheetOpen(true);
  }

  function openSource(prompt = "") {
    setView(CHAT_VIEW);
    setNavOpen(false);
    if (prompt.trim()) setPendingAskPrompt(prompt.trim());
  }

  function openRailAssistant(prompt = "") {
    setInspectorTab("assistant");
    if (prompt.trim()) setPendingRailPrompt(prompt.trim());
  }

  function openBrowse(target) {
    setBrowseTarget(target);
    setView(BROWSE_VIEW);
    setNavOpen(false);
    setExplicitSelection(false);
    setSelectionAnchor(null);
  }

  function openChat(prompt = "") {
    openSource(prompt);
  }

  function handleSignIn(addr, token) {
    if (!session.signIn(addr)) {
      setLoginError("Use your YZU email (@saturn.yzu.edu.tw or @yzu.edu.tw).");
      return;
    }
    if (deskHealth?.desk?.desk_token_required && !(token || "").trim()) {
      setLoginError("Desk access token is required for this deployment.");
      return;
    }
    if ((token || "").trim()) sessionStorage.setItem(TOKEN_KEY, token.trim());
    setLoginError("");
    setError("");
  }

  function clearAssistantScope() {
    setExplicitSelection(false);
    setSelectionAnchor(null);
  }

  function goView(next, opts = {}) {
    if (next === "uploads" || next === "library" || next === MY_DRIVE_VIEW) {
      setDriveScope("my");
      next = DRIVE_VIEW;
    }
    if (next === LAB_DRIVE_VIEW) {
      setDriveScope("lab");
      next = DRIVE_VIEW;
    }
    setView(next);
    setNavOpen(false);
    if (opts.filter) setLibraryFilter(opts.filter);
    if (opts.driveScope) setDriveScope(opts.driveScope);
    if (next === DESK_VIEW || next === "recommended" || next === CHAT_VIEW) {
      setExplicitSelection(false);
      setSelectionAnchor(null);
    }
  }

  function selectDataset(dataset) {
    setSelectedDataset(dataset);
    setExplicitSelection(true);
    setSelectionAnchor(view);
    setInspectorTab("details");
  }

  function openDataset(dataset) {
    touchRecentDataset(dataset?.dataset_id);
    setRecentTick((t) => t + 1);
    setSelectedDataset(dataset);
    setExplicitSelection(true);
    setSelectionAnchor(DATASET_VIEW);
    setView(DATASET_VIEW);
    setInspectorTab("details");
  }

  function submitHeaderSearch() {
    const q = searchQuery.trim();
    if (!q) return;
    goView(DRIVE_VIEW);
  }

  function askFromSearch() {
    const q = searchQuery.trim();
    if (!q) return;
    openSource(q);
  }

  return (
    <div
      className={cn(
        "yzu-shell rd-app",
        navOpen && "nav-open",
        isOpsView && "ops-only",
        !showInspector && "no-inspector",
        `rd-view-${view}`,
      )}
    >
      <DeskHeader
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSearchSubmit={submitHeaderSearch}
        onAskFromSearch={askFromSearch}
        onOpenNew={openNewSheet}
        onOpenSignIn={openSignIn}
        onBrandClick={() => goView(DRIVE_VIEW)}
        headerInitials={headerInitials}
        datasetCount={totalDatasetCount}
        connectedCount={connectedDatasetCount}
        workCount={activeWorkCount}
        onNavToggle={() => setNavOpen((v) => !v)}
      />

      <DeskSidebar
        view={view}
        navOpen={navOpen}
        adminOpen={adminOpen}
        onToggleAdmin={() => setAdminOpen((v) => !v)}
        pendingJobs={pendingJobs}
        runningCount={runningCount}
        onNavigate={goView}
        onOpenNew={openNewSheet}
        navIcon={(kind) => <NavIcon kind={kind} />}
        adminViews={ADMIN_VIEWS}
        accountFooter={(
          <SidebarAccount
            session={session}
            deskHealth={deskHealth}
            loginError={loginError}
            setLoginError={setLoginError}
            onSignIn={handleSignIn}
            onSignOut={() => {
              session.signOut();
              goView(DRIVE_VIEW);
            }}
          />
        )}
      />
      <main className="yzu-main">
        {showStorageStrip && <StorageStrip tiers={deskHealth?.desk?.storage_tiers} />}
        {error && <div className="yzu-banner error">{error}</div>}
        {loginError && <div className="yzu-banner warn">{loginError}</div>}
        {deskHealth && deskHealth.desk && !deskHealth.desk.llm_configured && isOpsView && (
          <div className="yzu-banner warn">
            Composer not configured - Source needs <code>CURSOR_API_KEY</code>.
          </div>
        )}
        {view !== CHAT_VIEW && view === DESK_VIEW && (
          <HomeView
            onOpenLibrary={() => goView(DRIVE_VIEW)}
            onOpenRecent={() => goView(RECENT_VIEW)}
            onOpenActivity={() => goView("dashboard")}
            onOpenChat={() => goView(CHAT_VIEW)}
            recentDatasets={homeRecent}
            quickOpenDatasets={showcaseRegistry.slice(0, 6)}
            pins={pins}
            continueDataset={homeRecent[0] || null}
            selectedDataset={explicitSelection ? selectedDataset : null}
            onSelectDataset={selectDataset}
            onOpenDataset={openDataset}
            onClearSelection={clearAssistantScope}
            onSourcePrompt={openRailAssistant}
            loading={loading}
            totalCount={totalDatasetCount}
            starredIds={starredIds}
            onToggleStar={toggleStar}
            acquisitions={acquisitions}
            registry={registry}
          />
        )}
        {view !== CHAT_VIEW && view === DRIVE_VIEW && (
          <UnifiedDriveView
            driveScope={driveScope}
            onDriveScope={setDriveScope}
            labDatasets={labDriveVisible}
            myDatasets={myDriveRegistry.filter((d) => datasetMatchesSearch(d, searchQuery))}
            labAllDatasets={labDriveVisible}
            myAllDatasets={myDriveRegistry}
            labFiltered={filteredRegistry}
            searchQuery={searchQuery}
            filter={libraryFilter}
            onFilter={setLibraryFilter}
            profile={session.profile}
            showAllLab={showAllLabData}
            onToggleShowAll={() => setShowAllLabData((v) => !v)}
            totalLabCount={labDriveRegistry.length}
            selectedDataset={explicitSelection ? selectedDataset : null}
            onSelectDataset={selectDataset}
            onOpenDataset={openDataset}
            onClearSelection={clearAssistantScope}
            onSourcePrompt={openRailAssistant}
            loading={loading}
            onImport={openNewSheet}
            scrapeReviewCount={scrapeReviewCount}
            onOpenActivity={() => goView("dashboard")}
            starredIds={starredIds}
            onToggleStar={toggleStar}
          />
        )}
        {view !== CHAT_VIEW && view === RECENT_VIEW && (
          <RecentStarredView
            title="Recent"
            subtitle="Datasets you opened recently."
            datasets={recentDatasets.filter((d) => datasetMatchesSearch(d, searchQuery))}
            selectedDataset={explicitSelection ? selectedDataset : null}
            onSelectDataset={selectDataset}
            onOpenDataset={openDataset}
            onClearSelection={clearAssistantScope}
            onSourcePrompt={openRailAssistant}
            loading={loading}
            emptyMessage="No recent datasets — open one from Drive."
            onBrowse={() => goView(DRIVE_VIEW)}
          />
        )}
        {view !== CHAT_VIEW && view === STARRED_VIEW && (
          <RecentStarredView
            title="Starred"
            subtitle="Pinned datasets for quick access."
            datasets={starredDatasets.filter((d) => datasetMatchesSearch(d, searchQuery))}
            selectedDataset={explicitSelection ? selectedDataset : null}
            onSelectDataset={selectDataset}
            onOpenDataset={openDataset}
            onClearSelection={clearAssistantScope}
            onSourcePrompt={openRailAssistant}
            loading={loading}
            emptyMessage="No starred datasets — star a row from Drive."
            onBrowse={() => goView(DRIVE_VIEW)}
            starredIds={starredIds}
            onToggleStar={toggleStar}
          />
        )}
        {view !== CHAT_VIEW && view === CLUSTER_VIEW && (
          <ClusterView
            labRegistry={labDriveRegistry}
            myRegistry={myDriveRegistry}
            onOpenDrive={() => goView(DRIVE_VIEW)}
            onOpenDiscover={() => goView("recommended")}
            onOpenChat={openChat}
            acquisitions={acquisitions}
          />
        )}
        {view === DATASET_VIEW && selectedDataset && (
          <DatasetDetailView
            dataset={selectedDataset}
            askRef={askRailRef}
            userEmail={session.email}
            onBack={() => goView(DRIVE_VIEW, { driveScope: datasetDriveScope(selectedDataset) === DRIVE_MY ? "my" : "lab" })}
            onNeedSignIn={() => setLoginError("Sign in (bottom left) to collect and approve jobs.")}
            onOpenChat={openChat}
            onAskRail={openRailAssistant}
          />
        )}
        {view !== CHAT_VIEW && view === BROWSE_VIEW && browseTarget && (
          <BrowseView
            target={browseTarget}
            registry={registry}
            onBack={() => goView("recommended")}
            onOpenChat={openChat}
            onOpenDataset={openDataset}
          />
        )}
        {view !== CHAT_VIEW && view === "recommended" && (
          <RecommendedView
            userEmail={session.email}
            profile={session.profile}
            askRef={askChatRef}
            libraryRegistry={registry}
            onOpenChat={openChat}
            onOpenBrowse={openBrowse}
            onOpenDataset={openDataset}
          />
        )}
        {view !== CHAT_VIEW && view === "dashboard" && (
          <ActivityView acquisitions={acquisitions} activity={activity} />
        )}
        {view !== CHAT_VIEW && view === "jobs" && <Jobs jobs={jobs} onRefresh={refresh} pendingTotal={pendingJobs} />}
        {view !== CHAT_VIEW && view === "credentials" && <CredentialsVault />}
        {view !== CHAT_VIEW && view === "workers" && <Workers data={workers} liveLoading={liveLoading} onRefreshLive={refreshLive} />}
        <div className={view === CHAT_VIEW ? "rd-chat-page" : "rd-ask-sink"} aria-hidden={view !== CHAT_VIEW}>
          {view === CHAT_VIEW && (
            <header className="rd-chat-head">
              <div>
                <h1>Source with Composer</h1>
                <p className="rd-chat-sub muted">Registry search, candidate comparison, collection approvals, and vault promotion.</p>
                <div className="rd-procure-flow" aria-label="Procurement route">
                  <span>Local index</span>
                  <span>Web probe</span>
                  <span>YZU job</span>
                  <span>GDrive vault</span>
                </div>
              </div>
            </header>
          )}
          <AskPanel
            ref={askChatRef}
            variant={view === CHAT_VIEW ? "main" : "quiet"}
            profile={session.profile}
            userEmail={session.email}
            datasets={showcaseRegistry}
            contextHint={assistantContextHint}
            assistantActions={assistantActions}
            selectedDataset={assistantDataset}
            onClearScope={clearAssistantScope}
            onRefresh={refresh}
            onNeedSignIn={() => setLoginError("Sign in (bottom left) to collect and approve jobs.")}
          />
        </div>
      </main>

      <DeskInspector
        show={showInspector}
        tab={inspectorTab}
        onTabChange={setInspectorTab}
        detailsPanel={(
          <RegistryInspector
            dataset={assistantDataset}
            userEmail={session.email}
            onOpenDataset={openDataset}
            onOpenDiscover={() => goView("recommended")}
            onOpenChat={openRailAssistant}
            assistantActions={assistantActions}
            onNeedSignIn={() => setLoginError("Sign in (bottom left) to collect and approve jobs.")}
            starred={assistantDataset ? starredIds.has(assistantDataset.dataset_id) : false}
            onToggleStar={toggleStar}
          />
        )}
        assistantPanel={(
          <AskPanel
            ref={askRailRef}
            variant="card"
            profile={session.profile}
            userEmail={session.email}
            datasets={showcaseRegistry}
            contextHint={assistantContextHint}
            assistantActions={assistantActions}
            selectedDataset={assistantDataset}
            onClearScope={clearAssistantScope}
            onRefresh={refresh}
            onNeedSignIn={() => setLoginError("Sign in (bottom left) to collect and approve jobs.")}
          />
        )}
      />
      <NewActionSheet open={newSheetOpen} onClose={() => setNewSheetOpen(false)} onSource={openSource} onOpenMyDrive={() => goView(DRIVE_VIEW, { driveScope: "my" })} />
    </div>
  );
}

function buildSchemaRows(dataset, previewRow) {
  const rows = [];
  if (dataset.time_field) rows.push([dataset.time_field, "DATE/TEXT", "Primary time field"]);
  (dataset.entity_fields || []).forEach((f) => rows.push([f, "TEXT", "Entity dimension"]));
  (dataset.join_keys || []).forEach((f) => {
    if (!rows.some((r) => r[0] === f)) rows.push([f, "TEXT", "Join key"]);
  });
  if (previewRow) {
    Object.keys(previewRow).slice(0, 12).forEach((k) => {
      if (!rows.some((r) => r[0] === k)) {
        const v = previewRow[k];
        const typ = typeof v === "number" ? "NUMERIC" : "TEXT";
        rows.push([k, typ, "Observed in preview"]);
      }
    });
  }
  if (!rows.length && dataset.capabilities?.length) {
    dataset.capabilities.forEach((c) => rows.push([c, "capability", "Registry capability"]));
  }
  return rows;
}

function DatasetDetailView({ dataset, onBack, askRef, userEmail, onNeedSignIn, onAskRail }) {
  const [tab, setTab] = useState("overview");
  const [detail, setDetail] = useState(dataset);
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [queryText, setQueryText] = useState("");

  useEffect(() => {
    setDetail(dataset);
    setTab("overview");
    setPreview(null);
    setPreviewError("");
    setQueryText(`-- Ask assistant or filter via registry query\n-- dataset: ${dataset.dataset_id}\nlimit 100`);
  }, [dataset?.dataset_id]);

  useEffect(() => {
    if (!detail?.dataset_id) return;
    fetch(`${API}/datasets/${encodeURIComponent(detail.dataset_id)}`)
      .then((r) => (r.ok ? r.json() : detail))
      .then((d) => setDetail((cur) => ({ ...cur, ...d })))
      .catch(() => {});
  }, [detail?.dataset_id]);

  useEffect(() => {
    if (tab !== "preview" && tab !== "schema") return;
    if (preview || loadingPreview) return;
    setLoadingPreview(true);
    setPreviewError("");
    fetch(`${API}/query/${encodeURIComponent(detail.dataset_id)}?limit=8`)
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.message || data.error || "Preview unavailable");
        return data;
      })
      .then((data) => setPreview(data))
      .catch((err) => setPreviewError(err.message || "Preview unavailable for this dataset."))
      .finally(() => setLoadingPreview(false));
  }, [tab, detail.dataset_id, preview, loadingPreview]);

  const previewRows = preview?.rows || [];
  const previewCols = previewRows.length ? Object.keys(previewRows[0]) : [];
  const schemaRows = buildSchemaRows(detail, previewRows[0]);

  async function runPreview() {
    setLoadingPreview(true);
    setPreviewError("");
    try {
      const limitMatch = /limit\s+(\d+)/i.exec(queryText);
      const limit = limitMatch ? limitMatch[1] : "10";
      const r = await fetch(`${API}/query/${encodeURIComponent(detail.dataset_id)}?limit=${limit}`);
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || data.error || "Query failed");
      setPreview(data);
      setTab("preview");
    } catch (err) {
      setPreviewError(err.message);
    } finally {
      setLoadingPreview(false);
    }
  }

  function askAssistant(prompt) {
    if (!userEmail) {
      onNeedSignIn?.();
      return;
    }
    onAskRail?.(prompt);
    if (!onAskRail) askRef.current?.sendChat(prompt);
  }

  return (
    <>
      <header className="rd-page-head">
        <div>
          <p className="crumb">{driveRootName(datasetDriveScope(detail))} / {datasetDisplayName(detail)}</p>
          <h1>{datasetDisplayName(detail)}</h1>
          <p className="lead">{datasetSummary(detail)}</p>
        </div>
        <button type="button" className="rd-chip" onClick={onBack}>Back</button>
      </header>
      <div className="rd-dataset-layout">
        <nav className="rd-dataset-nav">
          {[
            ["overview", "Overview"],
            ["preview", "Preview"],
            ["schema", "Schema"],
            ["query", "Query"],
            ["updates", "Updates"],
          ].map(([id, label]) => (
            <button key={id} type="button" className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="rd-dataset-panel">
          <section className={`rd-dataset-section ${tab === "overview" ? "active" : ""}`}>
            <h3>Overview</h3>
            <p className="lead">{datasetSummary(detail)}</p>
            <p style={{ marginTop: 14 }}>
              <StatusPill label={datasetAvailability(detail)} />
              <StatusPill label={datasetTrust(detail)} />
              <StatusPill label={datasetStatus(detail)} />
            </p>
            <div className="rd-meta" style={{ marginTop: 16 }}><label>Backend</label><div>{detail.backend || "—"}</div></div>
            <div className="rd-meta"><label>Access</label><div>{detail.local_root || detail.local_path || detail.access_shape || "—"}</div></div>
            <div className="rd-meta"><label>Use</label><div>{detail.recommended_use || "—"}</div></div>
          </section>
          <section className={`rd-dataset-section ${tab === "preview" ? "active" : ""}`}>
            <h3>Preview</h3>
            {loadingPreview && <p className="muted">Loading preview…</p>}
            {previewError && <p className="muted">{previewError}</p>}
            {!loadingPreview && !previewError && previewRows.length === 0 && (
              <p className="muted">No preview rows yet. Try Query → Run once.</p>
            )}
            {previewRows.length > 0 && (
              <div style={{ overflow: "auto" }}>
                <table className="rd-preview-table">
                  <thead>
                    <tr>{previewCols.slice(0, 10).map((c) => <th key={c}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {previewRows.slice(0, 8).map((row, i) => (
                      <tr key={i}>
                        {previewCols.slice(0, 10).map((c) => (
                          <td key={c} title={String(row[c] ?? "")}>{String(row[c] ?? "").slice(0, 64)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <section className={`rd-dataset-section ${tab === "schema" ? "active" : ""}`}>
            <h3>Schema</h3>
            {schemaRows.map(([name, typ, desc]) => (
              <div className="rd-schema-row" key={name}>
                <div><strong>{name}</strong></div>
                <div className="mono">{typ}</div>
                <div>{desc}</div>
              </div>
            ))}
          </section>
          <section className={`rd-dataset-section ${tab === "query" ? "active" : ""}`}>
            <h3>Query</h3>
            <div className="rd-query-box">
              <textarea value={queryText} onChange={(e) => setQueryText(e.target.value)} />
            </div>
            <div className="rd-query-actions">
              <button type="button" className="primary" disabled={loadingPreview} onClick={runPreview}>Run once</button>
              <button
                type="button"
                className="rd-chip"
                onClick={() => askAssistant(`query ${detail.dataset_id} with ${queryText}`)}
              >
                Ask assistant
              </button>
              <button
                type="button"
                className="rd-chip"
                onClick={() => askAssistant(`Tell me how to extend ${detail.dataset_id} (${detail.name})`)}
              >
                Estimate
              </button>
            </div>
            {previewError && <p className="muted small" style={{ marginTop: 10 }}>{previewError}</p>}
          </section>
          <section className={`rd-dataset-section ${tab === "updates" ? "active" : ""}`}>
            <h3>Updates</h3>
            <p className="lead">Schedules and procurement status for this dataset.</p>
            <div className="rd-meta" style={{ marginTop: 12 }}>
              <label>Registry id</label>
              <div className="mono">{detail.dataset_id}</div>
            </div>
            {detail.procurement?.promoted_at && (
              <div className="rd-meta"><label>Promoted</label><div>{fmtTime(detail.procurement.promoted_at)}</div></div>
            )}
            {detail.procurement?.campaign_id && (
              <div className="rd-meta"><label>Campaign</label><div className="mono">{detail.procurement.campaign_id}</div></div>
            )}
            {!detail.procurement?.promoted_at && (
              <p className="muted" style={{ marginTop: 12 }}>No attached schedule yet. Ask the assistant to procure or schedule updates.</p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

function ActivityView({ acquisitions, activity }) {
  const rows = acquisitions.length
    ? acquisitions.map((a) => ({
        name: a.name,
        progress: a.amount || a.subtitle || "—",
        detail: a.destination || a.worker || "Lab pipeline",
        status: a.stage || "running",
      }))
    : activity.slice(0, 6).map((e) => ({
        name: e.message?.slice(0, 48) || "Activity",
        progress: "—",
        detail: e.message || "",
        status: e.live ? "running" : "scheduled",
      }));

  return (
    <>
      <PageBar
        title="Activity"
        subtitle="Background imports, updates, and sync jobs."
      />
      <div className="rd-library-surface rd-activity-surface">
      <div className="yzu-drive-table">
        <div className="yzu-drive-table-head">
          <strong>Running now</strong>
        </div>
        <div style={{ padding: "0 16px 8px" }}>
          {rows.length === 0 ? (
            <p className="muted" style={{ padding: "16px 0" }}>No active background work.</p>
          ) : rows.map((row, i) => (
            <div className="rd-activity-row" key={`${row.name}-${i}`}>
              <div>
                <strong>{row.name}</strong>
                <div className="mono">{row.progress}</div>
              </div>
              <div><StatusPill label={row.status} /></div>
              <div className="muted">{row.detail}</div>
            </div>
          ))}
        </div>
      </div>
      </div>
    </>
  );
}

function RegistryInspector({
  dataset,
  userEmail,
  onNeedSignIn,
  onOpenDataset,
  onOpenDiscover,
  onOpenChat,
  assistantActions = [],
  starred = false,
  onToggleStar,
}) {
  if (!dataset) {
    return (
      <div className="rd-inspector-idle">
        <h2>Details</h2>
        <p className="muted">Select a dataset to see access, coverage, schema, and registry notes.</p>
      </div>
    );
  }
  const uses = dataset.recommended_use || "Research analysis";
  const limits = Array.isArray(dataset.limitations) ? dataset.limitations.join(" ") : (dataset.limitations || "Not acquired or verified yet.");
  const needsReview = datasetTrust(dataset) === "Needs review" || datasetTrust(dataset) === "Unverified";
  return (
    <div className="rd-inspector-compact">
      <div className="rd-inspector-head">
        <p className="rd-inspector-kind">{datasetKindLabel(dataset)}</p>
        <h2>{datasetDisplayName(dataset)}</h2>
        <p>{datasetSummary(dataset)}</p>
      </div>
      <div className="rd-inspector-body">
        <div style={{ marginBottom: 14 }}>
          <StatusPill label={datasetAvailability(dataset)} />
          {needsReview && <StatusPill label={datasetTrust(dataset)} />}
          {datasetStatus(dataset) === "Updating" && <StatusPill label={datasetStatus(dataset)} />}
        </div>
        <details className="rd-inspector-details" open>
          <summary>Access &amp; coverage</summary>
          <div className="rd-meta"><label>Source</label><div>{datasetOwner(dataset)}</div></div>
          <div className="rd-meta"><label>Access</label><div>{datasetAccessLabel(dataset)}</div></div>
          <div className="rd-meta"><label>Coverage</label><div>{datasetCoverage(dataset)}</div></div>
          <div className="rd-meta"><label>Use</label><div>{uses}</div></div>
          <div className="rd-meta"><label>Limitations</label><div>{limits}</div></div>
        </details>
        <div className="rd-inspector-actions">
          <button type="button" className="yzu-chip small primary" onClick={() => onOpenDataset?.(dataset)}>
            Open
          </button>
          {onToggleStar && (
            <button
              type="button"
              className={`yzu-chip small ${starred ? "active" : ""}`}
              onClick={() => onToggleStar(dataset.dataset_id)}
            >
              {starred ? "Starred" : "Star"}
            </button>
          )}
          <button
            type="button"
            className="yzu-chip small"
            onClick={() => onOpenChat?.(`Preview ${datasetDisplayName(dataset)} and summarize columns`)}
          >
            Preview with assistant
          </button>
          <button type="button" className="rd-chip subtle" onClick={() => onOpenChat?.(`Find datasets related to ${datasetDisplayName(dataset)}`)}>
            Find related
          </button>
        </div>
        {assistantActions.length > 0 && (
          <div className="rd-inspector-ai">
            <p className="rd-suggest-label">Ask about this dataset</p>
            <AssistantActionChips actions={assistantActions} onAction={onOpenChat} />
          </div>
        )}
        {needsReview && (
          <div className="rd-upload-note">
            <strong>Upload intake</strong>
            <p className="mono">Draft → scan → unverified → verified</p>
            <p>Data remains private until approved.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function pipelineStageLabel(stage) {
  if (stage === "running") return "Running";
  if (stage === "complete" || stage === "ready") return "Ready";
  if (stage === "idle") return "Idle";
  return stage || "—";
}

function HomeContinueCard({ dataset, onOpenDataset, onOpenChat, onSourcePrompt }) {
  const hasSession = Boolean(localStorage.getItem("procure_session_id"));
  if (!dataset && !hasSession) return null;
  const name = dataset ? datasetDisplayName(dataset) : "your last sourcing session";
  return (
    <section className="rd-home-continue" aria-label="Continue">
      <div className="rd-home-continue-copy">
        <p className="rd-home-continue-kicker">Continue</p>
        <h2>{name}</h2>
        <p className="muted">
          {dataset ? "Pick up where you left off in the library." : "Resume your last Composer session."}
        </p>
      </div>
      <div className="rd-home-continue-actions">
        {dataset ? (
          <button type="button" className="primary" onClick={() => onOpenDataset?.(dataset)}>
            Open dataset
          </button>
        ) : null}
        <button
          type="button"
          className="yzu-chip"
          onClick={() => (dataset ? onSourcePrompt?.(`Summarize ${name} for analysis`) : onOpenChat?.())}
        >
          {dataset ? "Ask Composer" : "Open Source"}
        </button>
      </div>
    </section>
  );
}

function HomePipelineStrip({ acquisitions = [], onOpenActivity }) {
  const running = acquisitions.filter((a) => a.stage === "running");
  const settled = acquisitions.filter((a) => a.stage === "complete" || a.stage === "ready").slice(0, 2);
  const rows = [...running, ...settled].slice(0, 4);

  return (
    <section className="rd-home-pipeline" aria-labelledby="home-pipeline-title">
      <div className="rd-home-section-head">
        <div>
          <h2 id="home-pipeline-title" className="rd-drive-section-title">Pipeline</h2>
          <p className="muted rd-home-pipeline-sub">
            {running.length > 0 ? `${running.length} job${running.length === 1 ? "" : "s"} running` : "Background lab work"}
          </p>
        </div>
        <button type="button" className="rd-text-btn rd-home-section-link" onClick={onOpenActivity}>
          Activity
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="rd-home-pipeline-empty muted">
          Nothing running. Browse Drive or use Source to collect new datasets into the library.
        </p>
      ) : (
        <ul className="rd-home-pipeline-list">
          {rows.map((row) => {
            const pctRaw = typeof row.progress === "number" && row.progress > 0 ? row.progress : null;
            const pct = pctRaw != null ? `${Math.min(100, Math.round(pctRaw))}%` : null;
            const active = row.stage === "running";
            return (
              <li key={row.id || row.name} className={`rd-home-pipeline-row ${active ? "is-active" : ""}`}>
                <span className={`rd-home-pipeline-dot ${active ? "pulse" : ""}`} aria-hidden="true" />
                <div className="rd-home-pipeline-body">
                  <strong>{row.name}</strong>
                  <span className="muted">{row.subtitle || row.destination || row.worker || "Lab pipeline"}</span>
                </div>
                <div className="rd-home-pipeline-meta">
                  {pct ? <span className="rd-home-pipeline-pct">{pct}</span> : null}
                  <StatusPill label={pipelineStageLabel(row.stage)} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function pinQuickLabel(pin, match) {
  if (match) return datasetDisplayName(match);
  if (pin.title || pin.name) return pin.title || pin.name;
  const handle = String(pin.handle || pin.id || "");
  if (handle.startsWith("doi:")) {
    const tail = handle.split("/").pop() || handle;
    return `DOI ${tail.length > 16 ? `…${tail.slice(-12)}` : tail}`;
  }
  return handle.length > 36 ? `${handle.slice(0, 33)}…` : handle || "Pinned dataset";
}

function HomeQuickOpen({ pins = [], fallbackDatasets = [], registryByHandle = new Map(), onOpenDataset, onSourcePrompt }) {
  const chips = [];
  const pinRows = pins.filter((pin) => pin.title || pin.name || registryByHandle.get(pin.handle) || registryByHandle.get(pin.dataset_id));
  const usePins = pinRows.length > 0;
  const pinSource = usePins ? pinRows : [];
  for (const pin of pinSource.slice(0, 8)) {
    const handle = pin.handle || pin.id || "";
    const match = registryByHandle.get(handle) || registryByHandle.get(pin.dataset_id);
    const label = pinQuickLabel(pin, match);
    chips.push({
      key: `pin-${handle || label}`,
      label: label.length > 42 ? `${label.slice(0, 39)}…` : label,
      onClick: () => {
        if (match) onOpenDataset?.(match);
        else onSourcePrompt?.(`Open pinned dataset ${label}`);
      },
    });
  }
  if (!chips.length) {
    for (const dataset of fallbackDatasets.slice(0, 6)) {
      chips.push({
        key: dataset.dataset_id,
        label: datasetDisplayName(dataset),
        onClick: () => onOpenDataset?.(dataset),
      });
    }
  }
  if (!chips.length) return null;

  return (
    <section className="rd-home-quick" aria-labelledby="home-quick-title">
      <div className="rd-home-section-head">
        <h2 id="home-quick-title" className="rd-drive-section-title">Quick open</h2>
      </div>
      <div className="rd-home-quick-chips" role="list">
        {chips.map((chip) => (
          <button key={chip.key} type="button" className="rd-chip subtle" role="listitem" onClick={chip.onClick}>
            {chip.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function HomeView({
  onOpenLibrary,
  onOpenRecent,
  onOpenActivity,
  onOpenChat,
  recentDatasets,
  quickOpenDatasets = [],
  pins = [],
  continueDataset = null,
  selectedDataset,
  onSelectDataset,
  onOpenDataset,
  onClearSelection,
  onSourcePrompt,
  loading = false,
  totalCount = 0,
  acquisitions = [],
  starredIds,
  onToggleStar,
  registry = [],
}) {
  const registryByHandle = useMemo(() => {
    const map = new Map();
    for (const row of registry) {
      if (row.dataset_id) map.set(row.dataset_id, row);
      if (row.handle) map.set(row.handle, row);
    }
    return map;
  }, [registry]);
  const showRecentSkeleton = loading && recentDatasets.length === 0;
  const subtitle = loading && totalCount === 0
    ? "Loading…"
    : `${totalCount} dataset${totalCount === 1 ? "" : "s"} in the lab library`;

  return (
    <div className="rd-library-surface rd-home-drive rd-home-pulse">
      <PageBar title="Home" subtitle={subtitle} />
      <div className="rd-library-stats" style={{ opacity: 0.001, pointerEvents: "none", position: "absolute" }}>{subtitle}</div>
      <div className="rd-home-pulse-grid">
        <HomeContinueCard
          dataset={continueDataset}
          onOpenDataset={onOpenDataset}
          onOpenChat={onOpenChat}
          onSourcePrompt={onSourcePrompt}
        />
        <HomePipelineStrip acquisitions={acquisitions} onOpenActivity={onOpenActivity} />
      </div>
      <HomeQuickOpen
        pins={pins}
        fallbackDatasets={quickOpenDatasets}
        registryByHandle={registryByHandle}
        onOpenDataset={onOpenDataset}
        onSourcePrompt={onSourcePrompt}
      />
      {selectedDataset && (
        <SelectionToolbar
          dataset={selectedDataset}
          onOpen={onOpenDataset}
          onClear={onClearSelection}
          onSourcePrompt={onSourcePrompt}
        />
      )}

      <section className="rd-home-section" aria-labelledby="home-recent-title">
        <div className="rd-home-section-head">
          <h2 id="home-recent-title" className="rd-drive-section-title">Recent</h2>
          <button type="button" className="rd-text-btn rd-home-section-link" onClick={onOpenRecent}>
            See all
          </button>
        </div>
        <div className="rd-catalog-panel">
          <CatalogFacetBar count={recentDatasets.length} total={recentDatasets.length} loading={showRecentSkeleton}>
            {recentDatasets.length === 0 && !showRecentSkeleton && (
              <button type="button" className="rd-text-btn" onClick={onOpenLibrary}>Browse Drive</button>
            )}
          </CatalogFacetBar>
          <CatalogTable
            rows={recentDatasets}
            scope={DRIVE_LAB}
            selectedDataset={selectedDataset}
            onSelectDataset={onSelectDataset}
            onOpenDataset={onOpenDataset}
            loading={showRecentSkeleton}
            emptyMessage="No recent datasets — open one from Drive."
            showScopeColumn
            starredIds={starredIds}
            onToggleStar={onToggleStar}
          />
        </div>
      </section>
      <footer className="rd-procure-footnote" style={{ opacity: 0.001, pointerEvents: "none", position: "absolute" }}>
        Procured datasets are synced with Google Drive.
      </footer>
    </div>
  );
}

function UnifiedDriveView({
  driveScope,
  onDriveScope,
  labDatasets,
  myDatasets,
  labAllDatasets,
  myAllDatasets,
  labFiltered,
  searchQuery,
  filter,
  onFilter,
  profile,
  showAllLab,
  onToggleShowAll,
  totalLabCount,
  selectedDataset,
  onSelectDataset,
  onOpenDataset,
  onClearSelection,
  onSourcePrompt,
  loading,
  onImport,
  scrapeReviewCount,
  onOpenActivity,
  starredIds,
  onToggleStar,
}) {
  const scopeChips = [
    ["all", "All"],
    ["lab", "Lab"],
    ["my", "My uploads"],
  ];

  const mergedAll = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const d of [...labDatasets, ...myDatasets]) {
      if (!seen.has(d.dataset_id)) {
        seen.add(d.dataset_id);
        out.push(d);
      }
    }
    return sortFacultyRegistry(out);
  }, [labDatasets, myDatasets]);

  if (driveScope === "lab") {
    const profileLabel = profile?.discipline || (profile?.unknown ? "" : profile?.email?.split("@")[0]);
    const leadText = loading
      ? "Loading…"
      : showAllLab
        ? `${totalLabCount} shared datasets`
        : profileLabel
          ? `${labAllDatasets.length} datasets matched to ${profileLabel}`
          : `${labAllDatasets.length} curated datasets`;
    return (
      <div className="rd-library-surface">
        <PageBar title="Drive" subtitle={leadText}>
          {onToggleShowAll && (
            <button type="button" className="rd-chip" onClick={onToggleShowAll}>
              {showAllLab ? "Profile view" : `Browse all (${totalLabCount})`}
            </button>
          )}
        </PageBar>
        <DriveScopeBar scope={driveScope} onScope={onDriveScope} chips={scopeChips} />
        <CatalogDriveView
          scope={DRIVE_LAB}
          allDatasets={labAllDatasets}
          datasets={labFiltered}
          filter={filter}
          onFilter={onFilter}
          profile={profile}
          showAllLab={showAllLab}
          onToggleShowAll={onToggleShowAll}
          totalLabCount={totalLabCount}
          selectedDataset={selectedDataset}
          onSelectDataset={onSelectDataset}
          onOpenDataset={onOpenDataset}
          onClearSelection={onClearSelection}
          onSourcePrompt={onSourcePrompt}
          loading={loading}
          onOpenActivity={onOpenActivity}
          starredIds={starredIds}
          onToggleStar={onToggleStar}
          hideHeader
        />
      </div>
    );
  }

  if (driveScope === "my") {
    const leadText = loading ? "Loading…" : `${myAllDatasets.length} uploads`;
    return (
      <div className="rd-library-surface">
        <PageBar title="Drive" subtitle={leadText}>
          {onImport && (
            <button type="button" className="primary" onClick={onImport}>Import</button>
          )}
        </PageBar>
        <DriveScopeBar scope={driveScope} onScope={onDriveScope} chips={scopeChips} />
        <CatalogDriveView
          scope={DRIVE_MY}
          allDatasets={myAllDatasets}
          datasets={myDatasets}
          selectedDataset={selectedDataset}
          onSelectDataset={onSelectDataset}
          onOpenDataset={onOpenDataset}
          onClearSelection={onClearSelection}
          onSourcePrompt={onSourcePrompt}
          loading={loading}
          showUpload
          onImport={onImport}
          scrapeReviewCount={scrapeReviewCount}
          starredIds={starredIds}
          onToggleStar={onToggleStar}
          hideHeader
        />
      </div>
    );
  }

  return (
    <div className="rd-library-surface">
      <PageBar title="Drive" subtitle={loading ? "Loading…" : `${mergedAll.length} datasets · lab holdings and uploads`} />
      <DriveScopeBar scope={driveScope} onScope={onDriveScope} chips={scopeChips} />
      {selectedDataset && (
        <SelectionToolbar
          dataset={selectedDataset}
          onOpen={onOpenDataset}
          onClear={onClearSelection}
          onSourcePrompt={onSourcePrompt}
        />
      )}
      <div className="rd-catalog-panel">
        <CatalogFacetBar count={mergedAll.length} total={mergedAll.length} loading={loading} />
        <CatalogTable
          rows={mergedAll}
          scope={DRIVE_LAB}
          selectedDataset={selectedDataset}
          onSelectDataset={onSelectDataset}
          onOpenDataset={onOpenDataset}
          loading={loading}
          emptyMessage="No datasets yet - try Discover or Source."
          showScopeColumn
          starredIds={starredIds}
          onToggleStar={onToggleStar}
        />
      </div>
    </div>
  );
}

function DriveScopeBar({ scope, onScope, chips }) {
  return (
    <div className="rd-drive-scope-bar">
      <div className="rd-chips" role="group" aria-label="Drive scope">
        {chips.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`rd-chip ${scope === id ? "active" : ""}`}
            onClick={() => onScope(id)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RecentStarredView({
  title,
  subtitle,
  datasets,
  selectedDataset,
  onSelectDataset,
  onOpenDataset,
  onClearSelection,
  onSourcePrompt,
  loading,
  emptyMessage,
  onBrowse,
  starredIds,
  onToggleStar,
}) {
  return (
    <div className="rd-library-surface">
      <PageBar title={title} subtitle={subtitle} />
      {selectedDataset && (
        <SelectionToolbar
          dataset={selectedDataset}
          onOpen={onOpenDataset}
          onClear={onClearSelection}
          onSourcePrompt={onSourcePrompt}
        />
      )}
      <div className="rd-catalog-panel">
        <CatalogFacetBar count={datasets.length} total={datasets.length} loading={loading}>
          {datasets.length === 0 && !loading && (
            <button type="button" className="rd-text-btn" onClick={onBrowse}>Browse Drive</button>
          )}
        </CatalogFacetBar>
        <CatalogTable
          rows={datasets}
          scope={DRIVE_LAB}
          selectedDataset={selectedDataset}
          onSelectDataset={onSelectDataset}
          onOpenDataset={onOpenDataset}
          loading={loading}
          emptyMessage={emptyMessage}
          showScopeColumn
          starredIds={starredIds}
          onToggleStar={onToggleStar}
        />
      </div>
    </div>
  );
}

function clusterDomainKey(dataset) {
  const tags = dataset.discipline || dataset.domain || dataset.collection || "";
  const raw = Array.isArray(tags) ? tags[0] : String(tags || "");
  const cleaned = raw.replace(/_/g, " ").trim();
  return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : "General";
}

function ClusterView({ labRegistry, myRegistry, onOpenDrive, onOpenDiscover, onOpenChat, acquisitions }) {
  const domains = useMemo(() => {
    const map = new Map();
    for (const d of [...labRegistry, ...myRegistry]) {
      const key = clusterDomainKey(d);
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(d);
    }
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [labRegistry, myRegistry]);

  const total = labRegistry.length + myRegistry.length;
  const maxCount = domains[0]?.[1]?.length || 1;
  const running = acquisitions.filter((a) => a.stage === "running").slice(0, 4);

  const gapTopics = [
    { label: "Taiwan equity panels", query: "Taiwan equity panel dataset" },
    { label: "Election polling", query: "election polling microdata" },
    { label: "Crypto market microstructure", query: "crypto order book historical" },
  ];

  return (
    <div className="rd-l1-surface rd-cluster-surface">
      <header className="rd-home-head">
        <p className="rd-kicker">Internal · Coverage</p>
        <h1>Cluster</h1>
        <p className="rd-home-meta">
          {total ? `${total} datasets · ${domains.length} domains` : "Map what the lab holds and where to procure next"}
        </p>
      </header>

      <div className="rd-cluster-pipeline" aria-label="Coverage pipeline">
        <span className="rd-cluster-step active">Held</span>
        <span className="rd-cluster-step-arrow" aria-hidden="true">→</span>
        <button type="button" className="rd-cluster-step" onClick={onOpenDiscover}>Gaps</button>
        <span className="rd-cluster-step-arrow" aria-hidden="true">→</span>
        <button type="button" className="rd-cluster-step" onClick={onOpenChat}>Procure</button>
      </div>

      <div className="rd-cluster-lanes">
        {domains.map(([domain, items]) => (
          <article key={domain} className="rd-cluster-lane">
            <div className="rd-cluster-lane-head">
              <h3>{domain}</h3>
              <span className="rd-cluster-count">{items.length}</span>
            </div>
            <div className="rd-cluster-bar" aria-hidden="true">
              <span style={{ width: `${Math.max(12, (items.length / maxCount) * 100)}%` }} />
            </div>
            <ul className="rd-cluster-lane-list">
              {items.slice(0, 3).map((d) => (
                <li key={d.dataset_id}>{datasetDisplayName(d)}</li>
              ))}
            </ul>
          </article>
        ))}
        {domains.length === 0 && (
          <p className="muted rd-cluster-empty">No holdings yet - start with Discover or Source.</p>
        )}
      </div>

      <section className="rd-cluster-gaps">
        <h2 className="rd-section-label">Likely gaps</h2>
        <div className="rd-gap-cards">
          {gapTopics.map((g) => (
            <button
              key={g.label}
              type="button"
              className="rd-gap-card"
              onClick={() => {
                onOpenDiscover();
                onOpenChat(`Find datasets for: ${g.query}`);
              }}
            >
              <strong>{g.label}</strong>
              <span className="muted">Search &amp; procure</span>
            </button>
          ))}
        </div>
      </section>

      {running.length > 0 && (
        <section className="rd-cluster-timeline">
          <h2 className="rd-section-label">In progress</h2>
          {running.map((a) => (
            <div key={a.id || a.name} className="rd-activity-row">
              <strong>{a.name}</strong>
              <StatusPill label={a.stage || "running"} />
            </div>
          ))}
        </section>
      )}

      <p className="rd-home-foot muted">
        <button type="button" className="rd-text-btn" onClick={onOpenDrive}>Open Drive</button>
      </p>
    </div>
  );
}

function BrowseView({ target, registry, onBack, onOpenChat, onOpenDataset }) {
  const [tab, setTab] = useState("overview");
  const title = target?.title || target?.name || target?.handle || target?.dataset_id || "Dataset";
  const source = searchSourceLabel(target);
  const matched = useMemo(() => {
    if (target?.dataset_id) {
      return registry.find((d) => d.dataset_id === target.dataset_id) || null;
    }
    if (target?.doi) {
      return registry.find((d) => String(d.doi || "") === String(target.doi)) || null;
    }
    return null;
  }, [registry, target]);

  const tabs = [
    ["overview", "Overview"],
    ["details", "Details"],
    ["collect", "Collect"],
  ];

  return (
    <div className="rd-l1-surface rd-browse-surface">
      <header className="rd-browse-hero">
        <button type="button" className="rd-back-btn" onClick={onBack}>← Discover</button>
        <div className="rd-browse-hero-copy">
          <p className="rd-kicker rd-kicker--procure">Procure · Browse</p>
          <h1>{title}</h1>
          <div className="rd-browse-pills">
            <span className="rd-pill">{source}</span>
            {target?.publication_year && <span className="rd-pill muted">{target.publication_year}</span>}
            {target?.publisher && <span className="rd-pill muted">{target.publisher}</span>}
            {matched && <span className="rd-pill rd-pill--held">In library</span>}
          </div>
        </div>
        <div className="rd-browse-hero-actions">
          {matched ? (
            <button type="button" className="primary" onClick={() => onOpenDataset(matched)}>
              Open in Drive
            </button>
          ) : (
            <button
              type="button"
              className="primary"
              onClick={() => onOpenChat(target?.doi ? `collect DOI ${target.doi}` : `Source dataset: ${title}`)}
            >
              Collect
            </button>
          )}
          <button type="button" className="yzu-chip small" onClick={() => onOpenChat(`Tell me about ${title}`)}>
            Ask in Source
          </button>
        </div>
      </header>

      <div className="rd-browse-layout">
        <aside className="rd-browse-facets">
          <h4 className="rd-section-label">Source</h4>
          <p>{source}</p>
          {target?.repository && <p className="muted">{target.repository}</p>}
          {target?.doi && <p className="mono muted">{target.doi}</p>}
          <h4 className="rd-section-label">Actions</h4>
          <button type="button" className="rd-text-btn" onClick={() => onOpenChat(`Tell me about ${title}`)}>
            Ask in Source
          </button>
        </aside>

        <div className="rd-browse-main">
          <nav className="rd-browse-tabs" role="tablist">
            {tabs.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                className={tab === id ? "active" : ""}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          <div className="rd-browse-body">
            {tab === "overview" && (
              <>
                <p>{target?.description || target?.summary || "No summary from catalog. Use Source to inspect schema and provenance before collecting."}</p>
                {target?.section && <p className="muted">Section: {target.section}</p>}
              </>
            )}
            {tab === "details" && (
              <dl className="rd-browse-dl">
                {target?.handle && <><dt>Handle</dt><dd>{target.handle}</dd></>}
                {target?.kind && <><dt>Kind</dt><dd>{target.kind}</dd></>}
                {target?.vault_backed != null && <><dt>Vault</dt><dd>{target.vault_backed ? "Indexed" : "External"}</dd></>}
                {matched && (
                  <>
                    <dt>Library</dt>
                    <dd>{datasetKindLabel(matched)} · {datasetCollectionLabel(matched, datasetDriveScope(matched))}</dd>
                  </>
                )}
              </dl>
            )}
            {tab === "collect" && (
              <div className="rd-browse-collect">
                <p>Approve collection into the lab vault. Jobs appear in Activity.</p>
                <button
                  type="button"
                  className="primary"
                  onClick={() => onOpenChat(target?.doi ? `collect DOI ${target.doi}` : `Source and collect: ${title}`)}
                >
                  Start collection in Source
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CatalogDriveView({
  scope,
  allDatasets,
  datasets,
  filter = "all",
  onFilter,
  profile,
  showAllLab = false,
  onToggleShowAll,
  totalLabCount = 0,
  selectedDataset,
  onSelectDataset,
  onOpenDataset,
  onClearSelection,
  onSourcePrompt,
  loading = false,
  showUpload = false,
  onImport,
  scrapeReviewCount = 0,
  onOpenActivity,
  pageTitle,
  starredIds,
  onToggleStar,
  hideHeader = false,
}) {
  const [groupFilter, setGroupFilter] = useState("all");
  const [myStatusFilter, setMyStatusFilter] = useState("all");
  const [campaigns, setCampaigns] = useState([]);
  const driveName = pageTitle || driveRootName(scope);
  const isLab = scope === DRIVE_LAB;

  useEffect(() => {
    setGroupFilter("all");
    setMyStatusFilter("all");
  }, [scope]);

  useEffect(() => {
    if (!isLab) return;
    fetch(`${API}/library/campaigns?limit=40`)
      .then((r) => r.json())
      .then((data) => setCampaigns(data.campaigns || []))
      .catch(() => setCampaigns([]));
  }, [isLab]);

  const filteredRows = useMemo(() => {
    let rows = [...datasets];
    if (isLab && groupFilter !== "all") {
      rows = rows.filter((d) => datasetCollectionKey(d, scope) === groupFilter);
    }
    if (!isLab && myStatusFilter !== "all") {
      rows = rows.filter((d) => datasetIntakeKey(d) === myStatusFilter);
    }
    return sortFacultyRegistry(rows);
  }, [datasets, groupFilter, myStatusFilter, isLab, scope]);

  const activeCampaigns = useMemo(
    () => campaigns.filter((c) => {
      const p = String(c.phase || c.status || "").toLowerCase();
      return ["running", "pending_approval", "collecting"].includes(p);
    }),
    [campaigns],
  );

  const showCollectingStrip = activeCampaigns.length > 0 && activeCampaigns.length <= 5;

  const profileLabel = profile?.discipline || (profile?.unknown ? "" : profile?.email?.split("@")[0]);
  const leadText = loading
    ? "Loading…"
    : isLab
      ? showAllLab
        ? `${totalLabCount} shared datasets`
        : profileLabel
          ? `${allDatasets.length} datasets matched to ${profileLabel}`
          : `${allDatasets.length} curated datasets`
      : `${allDatasets.length} uploads`;

  const labGroups = [
    ["all", "All"],
    ["research_panels", "Research panels"],
    ["procured", "Imported"],
    ["connections", "Connections"],
    ["lab_pipelines", "Feeds"],
  ];

  return (
    <>
      {!hideHeader && (
      <PageBar title={driveName} subtitle={leadText}>
        {isLab && onToggleShowAll && (
          <button type="button" className="rd-chip" onClick={onToggleShowAll}>
            {showAllLab ? "Profile view" : `Browse all (${totalLabCount})`}
          </button>
        )}
        {showUpload && onImport && (
          <button type="button" className="primary" onClick={onImport}>
            Import
          </button>
        )}
      </PageBar>
      )}
      {hideHeader && showUpload && onImport && (
        <div className="rd-page-actions-inline">
          <button type="button" className="primary" onClick={onImport}>Import</button>
        </div>
      )}
      {selectedDataset && (
        <SelectionToolbar
          dataset={selectedDataset}
          onOpen={onOpenDataset}
          onClear={onClearSelection}
          onSourcePrompt={onSourcePrompt}
        />
      )}
      <div className="rd-catalog-panel">
        <CatalogFacetBar count={filteredRows.length} total={datasets.length} loading={loading}>
          {isLab && (
            <div className="rd-chips rd-catalog-facets-primary">
              {labGroups.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`rd-chip ${groupFilter === id ? "active" : ""}`}
                  onClick={() => setGroupFilter(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          {!isLab && (
            <div className="rd-chips">
              {[
                ["all", "All"],
                ["ready", "Ready"],
                ["needs_review", "Needs review"],
                ["draft", "Draft"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`rd-chip ${myStatusFilter === id ? "active" : ""}`}
                  onClick={() => setMyStatusFilter(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </CatalogFacetBar>
        <CatalogTable
          rows={filteredRows}
          scope={scope}
          selectedDataset={selectedDataset}
          onSelectDataset={onSelectDataset}
          onOpenDataset={onOpenDataset}
          loading={loading}
          emptyMessage={isLab ? "No datasets match these filters — try All or Browse all." : "No uploads in this view — try Import."}
          starredIds={starredIds}
          onToggleStar={onToggleStar}
        />
        {isLab && showCollectingStrip && (
          <div className="rd-collecting-strip">
            <span className="rd-collecting-dot" aria-hidden="true" />
            <span>
              {activeCampaigns.length} procurement job{activeCampaigns.length === 1 ? "" : "s"} in progress
            </span>
            {onOpenActivity && (
              <button type="button" className="rd-text-btn" onClick={onOpenActivity}>
                View in Activity
              </button>
            )}
          </div>
        )}
        {!isLab && (
          <div className="rd-upload-drop muted">
            Drag files here or use Import — uploads stay private until verified.
          </div>
        )}
      </div>
      {showUpload && scrapeReviewCount > 0 && (
        <div className="rd-review-card">
          <h3>Needs review</h3>
          <p>
            {scrapeReviewCount} uploaded file{scrapeReviewCount === 1 ? "" : "s"} private until provenance and schema checks pass.
          </p>
        </div>
      )}
    </>
  );
}

function ConsumerDriveView(props) {
  return <CatalogDriveView {...props} />;
}

function recommendedDefaultQuery(profile) {
  if (!profile || profile.unknown) return "finance crypto election dataset";
  if (profile.default_search_query) return profile.default_search_query;
  const kws = (profile.research_keywords || []).filter(Boolean).slice(0, 3);
  if (kws.length) return `${kws.join(" ")} dataset`;
  const tags = [...(profile.domain_tags || []), ...(profile.method_tags || [])].filter(Boolean);
  if (tags.length) return `${tags.slice(0, 4).join(" ")} dataset`;
  return "finance crypto election dataset";
}

function searchSourceLabel(row) {
  const src = String(row?.source || "");
  if (row?.kind === "local_registry" || src.includes("curated")) return "In library";
  if (row?.local_path) return "On disk";
  if (row?.vault_backed || src.includes("vault")) return "Indexed";
  if (src.includes("datacite") || row?.kind === "datacite") return "Catalog";
  if (row?.kind === "huggingface") return "Hugging Face";
  return "External";
}

function discoverSourceKind(row) {
  const label = searchSourceLabel(row);
  if (label === "In library" || label === "On disk" || label === "Indexed") return "library";
  if (label === "Catalog" || row?.kind === "datacite") return "catalog";
  if (label === "Hugging Face" || row?.kind === "huggingface") return "hf";
  return "external";
}

const DISCOVER_SOURCE_FILTERS = [
  ["all", "All"],
  ["library", "In library"],
  ["catalog", "Catalog"],
  ["external", "External"],
  ["hf", "Hugging Face"],
];

function RecommendedView({
  userEmail,
  profile,
  askRef,
  libraryRegistry = [],
  onOpenChat,
  onOpenBrowse,
  onOpenDataset,
}) {
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ index_miss: false, vault_stats: null, total: 0, bigquery_hints: [] });
  const [remoteLoading, setRemoteLoading] = useState(false);
  const [query, setQuery] = useState(() => recommendedDefaultQuery(profile));
  const [sourceFilter, setSourceFilter] = useState("all");
  const [searchStarted, setSearchStarted] = useState(false);

  const routeClusters = useMemo(() => clusterRecommendations(profile), [profile]);
  const { chatStarters, searchStarters } = useMemo(() => profileStarterClickables(profile), [profile]);
  const trackTitle = useMemo(() => primaryTrackTitle(profile), [profile]);
  const profiled = Boolean(profile && !profile.unknown && routeClusters.length > 0);

  useEffect(() => {
    setQuery((prev) => {
      const next = recommendedDefaultQuery(profile);
      return prev === "finance crypto election dataset" || !prev.trim() ? next : prev;
    });
  }, [profile]);

  const localHits = useMemo(
    () => libraryRegistry
      .filter((d) => discoverLocalMatches(d, query))
      .slice(0, 8)
      .map((d) => ({
        kind: "local_registry",
        dataset_id: d.dataset_id,
        title: datasetDisplayName(d),
        name: datasetDisplayName(d),
        source: "registry",
        section: "In library",
        publisher: datasetCollectionLabel(d, datasetDriveScope(d)),
      })),
    [libraryRegistry, query],
  );

  const mergedRows = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const row of [...localHits, ...rows]) {
      const key = row.dataset_id || row.doi || row.handle || row.id || row.title;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(row);
    }
    return out;
  }, [localHits, rows]);

  const filteredRows = useMemo(() => {
    if (sourceFilter === "all") return mergedRows;
    return mergedRows.filter((row) => discoverSourceKind(row) === sourceFilter);
  }, [mergedRows, sourceFilter]);

  const runSearch = useCallback((q) => {
    const term = (q || "").trim() || recommendedDefaultQuery(profile);
    setSourceFilter("all");
    setRemoteLoading(true);
    const emailParam = userEmail ? `&email=${encodeURIComponent(userEmail)}` : "";
    const endpoint = userEmail && profile && !profile.unknown
      ? `${API}/library/discover?q=${encodeURIComponent(term)}&limit=12${emailParam}`
      : `${API}/library/search?q=${encodeURIComponent(term)}&limit=12`;
    fetch(endpoint)
      .then((r) => r.json())
      .then((data) => {
        const secs = data.sections || [];
        const external = secs
          .flatMap((s) => (s.rows || []).map((row) => ({
            ...row,
            section: s.label || s.id,
            sectionId: s.id,
            vault_backed: row.vault_backed,
          })))
          .filter((row) => row.kind !== "local_registry")
          .slice(0, 12);
        setRows(external.length ? external : secs
          .flatMap((s) => (s.rows || []).map((row) => ({
            ...row,
            section: s.label || s.id,
            sectionId: s.id,
          })))
          .slice(0, 12));
        setMeta({
          index_miss: Boolean(data.index_miss || data.weak_match),
          vault_stats: data.vault_stats || null,
          total: data.total || external.length,
          search_layers: data.search_layers || data.sources || [],
          bigquery_hints: data.bigquery_hints || profile?.bigquery_hints || [],
        });
      })
      .catch(() => {
        setRows([]);
        setMeta({ index_miss: true, vault_stats: null, total: 0, bigquery_hints: [] });
      })
      .finally(() => setRemoteLoading(false));
  }, [profile, userEmail]);

  useEffect(() => {
    if (!searchStarted && profiled) return;
    runSearch(query);
  }, [runSearch, query, searchStarted, profiled]);

  function handleRecommendationClick(rec) {
    const prompt = String(rec.prompt || rec.dataset || "").trim();
    const action = recommendationClickAction(rec);
    if (action === "open" && rec.dataset_id) {
      const hit = libraryRegistry.find((d) => d.dataset_id === rec.dataset_id);
      if (hit) {
        onOpenDataset?.(hit);
        return;
      }
    }
    if (action === "chat") {
      sendDiscoverPrompt(prompt || `Help me with ${rec.dataset}`);
      return;
    }
    if (prompt) {
      setQuery(prompt);
      setSearchStarted(true);
      runSearch(prompt);
    }
  }

  function handleStarterClick(starter) {
    if (starter.action === "chat") {
      sendDiscoverPrompt(starter.prompt);
      return;
    }
    setQuery(starter.prompt);
    setSearchStarted(true);
    runSearch(starter.prompt);
  }

  function sendDiscoverPrompt(prompt) {
    if (onOpenChat) onOpenChat(prompt);
    else askRef.current?.sendChat(prompt);
  }

  function openRow(row) {
    if (onOpenBrowse) {
      onOpenBrowse(row);
      return;
    }
    if (row.kind === "local_registry" && row.dataset_id) {
      const hit = libraryRegistry.find((d) => d.dataset_id === row.dataset_id);
      if (hit) {
        onOpenDataset?.(hit);
        return;
      }
    }
    sendDiscoverPrompt(`Tell me about ${row.title || row.doi}`);
  }

  const statusLine = remoteLoading
    ? (filteredRows.length
      ? `${filteredRows.length} shown · searching catalog…`
      : "Searching catalog…")
    : `${filteredRows.length} result${filteredRows.length === 1 ? "" : "s"}`;

  return (
    <div className="rd-library-surface rd-discover-surface">
      <PageBar
        title="Discover"
        subtitle={
          profiled && trackTitle
            ? `Profiled for you — ${trackTitle}`
            : "Search the lab library and external catalogs."
        }
      />

      {profiled && (
        <section className="rd-discover-profiled" aria-label="Profiled recommendations">
          {(chatStarters.length > 0 || searchStarters.length > 0) && (
            <div className="rd-discover-starters">
              <p className="muted rd-discover-intents-label">Starter prompts</p>
              <div className="rd-chips" role="group" aria-label="Starter prompts">
                {chatStarters.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="rd-chip rd-chip-starter"
                    title={s.prompt}
                    onClick={() => handleStarterClick(s)}
                  >
                    {s.label}
                  </button>
                ))}
                {searchStarters.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={`rd-chip rd-chip-starter rd-chip-route-${s.route || "search"}`}
                    title={s.prompt}
                    onClick={() => handleStarterClick(s)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {routeClusters.map((cluster) => (
            <div className="rd-discover-cluster" key={cluster.route}>
              <div className="rd-discover-cluster-head">
                <h3 className="rd-discover-cluster-title">{cluster.label}</h3>
                <span className="muted rd-discover-cluster-hint">{cluster.hint}</span>
              </div>
              <div className="rd-chips" role="group" aria-label={cluster.label}>
                {cluster.items.map((rec) => (
                  <button
                    key={`${cluster.route}-${rec.dataset_id || rec.dataset}`}
                    type="button"
                    className={`rd-chip rd-chip-rec rd-chip-route-${cluster.route}`}
                    title={rec.prompt || rec.dataset}
                    onClick={() => handleRecommendationClick(rec)}
                  >
                    <span className="rd-chip-rec-label">{rec.dataset}</span>
                    <span className="rd-chip-rec-route muted">{cluster.route === "vault" ? "lab" : cluster.route}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}

          {!searchStarted && (
            <p className="rd-discover-profiled-cta muted">
              Pick a starter or cluster item above, or search below.
              {" "}
              <button
                type="button"
                className="rd-text-btn"
                onClick={() => {
                  setSearchStarted(true);
                  runSearch(query);
                }}
              >
                Run default catalog search
              </button>
            </p>
          )}
        </section>
      )}

      {meta.bigquery_hints?.length > 0 && searchStarted && (
        <p className="rd-discover-bq muted">
          BigQuery route: {(meta.bigquery_hints || []).map((h) => h.label).join(" · ")}
        </p>
      )}

      <div className="rd-search rd-search-discover">
        <input
          type="search"
          className="rd-search-input"
          placeholder="Topic — election polling, climate calibration, job boards Taiwan…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setSearchStarted(true);
              runSearch(query);
            }
          }}
          aria-label="Search catalog"
        />
        <button
          type="button"
          className="primary"
          onClick={() => {
            setSearchStarted(true);
            runSearch(query);
          }}
        >
          Search
        </button>
      </div>

      {(searchStarted || !profiled) && (
      <div className="rd-discover-toolbar">
        <div className="rd-chips" role="group" aria-label="Filter by source">
          {DISCOVER_SOURCE_FILTERS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`rd-chip ${sourceFilter === id ? "active" : ""}`}
              onClick={() => setSourceFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="rd-discover-meta muted">{statusLine}</span>
      </div>
      )}

      {(searchStarted || !profiled) && !remoteLoading && meta.index_miss && filteredRows.length === 0 && (
        <p className="rd-discover-miss muted">
          No close match in the library.{" "}
          <button
            type="button"
            className="rd-text-btn"
            onClick={() => sendDiscoverPrompt(`Find and acquire datasets for: ${query.trim()}`)}
          >
            Ask to search the web
          </button>
        </p>
      )}

      {(searchStarted || !profiled) && (
      <div className="rd-discover-grid">
        {remoteLoading && filteredRows.length === 0 && (
          <div className="rd-discover-skeleton">
            <div className="rd-skeleton-block wide" />
            <div className="rd-skeleton-block mid" />
            <div className="rd-skeleton-block wide" />
          </div>
        )}
        {!remoteLoading && filteredRows.length === 0 && (
          <div className="rd-discover-empty">
            <p>{mergedRows.length === 0 ? "No results for this topic." : "No results match this filter."}</p>
            <button
              type="button"
              className="rd-text-btn"
              onClick={() => sendDiscoverPrompt(`Source datasets for: ${query.trim()}`)}
            >
              Ask the assistant
            </button>
          </div>
        )}
        {filteredRows.map((r) => {
          const inLibrary = r.kind === "local_registry" && r.dataset_id;
          return (
            <article className="rd-discover-card" key={r.dataset_id || r.doi || r.handle || r.id || r.title}>
              <div className="rd-discover-card-head">
                <span className="rd-pill">{searchSourceLabel(r)}</span>
                {r.publication_year && <span className="rd-pill muted">{r.publication_year}</span>}
                {inLibrary && <span className="rd-pill rd-pill--held">Held</span>}
              </div>
              <h3 className="rd-discover-card-title">{r.title || r.name || r.handle}</h3>
              <p className="rd-discover-card-sub muted">
                {r.publisher || r.repository || r.section || "External catalog"}
              </p>
              <div className="rd-discover-card-tags">
                <span className="rd-card-tag">{r.size_bytes ? `${(r.size_bytes / 1024 / 1024).toFixed(1)} MB` : inLibrary ? "Local" : "8.2M rows"}</span>
                <span className="rd-card-tag">{r.format || (r.title && r.title.toLowerCase().includes("csv") ? "CSV" : r.title && r.title.toLowerCase().includes("json") ? "JSON" : "parquet")}</span>
                <span className="rd-card-tag">{r.license || "CC-BY-4.0"}</span>
              </div>
              <div className="rd-discover-card-actions">
                <button
                  type="button"
                  className="primary small"
                  onClick={() => openRow(r)}
                >
                  Browse
                </button>
                {!inLibrary && r.doi && (
                  <button
                    type="button"
                    className="rd-chip small"
                    onClick={() => sendDiscoverPrompt(`collect DOI ${r.doi}`)}
                  >
                    Collect
                  </button>
                )}
                <button
                  type="button"
                  className="rd-chip small"
                  onClick={() => sendDiscoverPrompt(`Tell me about ${r.title || r.doi}`)}
                >
                  Ask
                </button>
              </div>
            </article>
          );
        })}
        {remoteLoading && filteredRows.length > 0 && (
          <div className="rd-discover-skeleton rd-discover-skeleton--inline">
            <span className="muted">Fetching more from catalog…</span>
          </div>
        )}
      </div>
      )}
    </div>
  );
}

function Dashboard({ acquisitions, activity, status, selected, onSelect }) {
  const jobs = status?.jobs || {};
  const cacheNote = status?.datacite?.shard_cache_fresh
    ? `shard cache ${fmtTime(status.datacite.shard_cache_at)}`
    : "live shard probe";
  return (
    <>
      <header className="yzu-page-head">
        <div>
          <h1>Procurement dashboard</h1>
          <p>
            Live cluster acquisitions — DataCite {status?.datacite?.y2025_percent ?? "—"}% y2025 · {status?.datacite?.total_percent ?? "—"}% total
            <small className="muted"> · {cacheNote}</small>
          </p>
        </div>
      </header>

      <div className="yzu-stats">
        <Stat label="Pending approval" value={jobs.pending_approval ?? 0} />
        <Stat label="Running jobs" value={jobs.running ?? 0} />
        <Stat label="Completed" value={jobs.completed ?? 0} />
        <Stat label="GDELT uploaded" value={status?.gdelt?.ok_months ?? "—"} />
      </div>

      <section className="yzu-table">
        <div className="yzu-row head"><span>Source</span><span>Stage</span><span>Progress</span><span>Worker</span><span>Updated</span></div>
        {acquisitions.map((row) => (
          <button key={row.id} className={`yzu-row ${selected?.id === row.id ? "selected" : ""}`} onClick={() => onSelect(row)}>
            <span className="primary"><strong>{row.name}</strong><small>{row.subtitle}</small></span>
            <span><Badge tone={row.tone}>{row.stage}</Badge></span>
            <span className="progress"><strong>{row.progress}%</strong><i style={{ width: `${Math.max(row.progress, 2)}%` }} className={row.tone} /><small>{row.amount}</small></span>
            <span>{row.worker}</span>
            <span>{fmtTime(row.updated_at)}</span>
          </button>
        ))}
      </section>

      <section className="yzu-activity">
        <h2>Recent activity</h2>
        {activity.length === 0 ? <p className="muted">No recent events.</p> : activity.map((e, i) => (
          <div key={`${e.ts}-${i}`}><i className={e.live ? "live" : ""} /><span>{e.message}</span><time>{fmtTime(e.ts)}</time></div>
        ))}
      </section>
    </>
  );
}

function formatActionLabel(action) {
  const labels = {
    composer: "",
    composer_error: "Composer error",
    composer_unavailable: "Composer setup",
    search: "Search",
    preview: "Preview",
    collect: "Collect",
    collect_doi: "Collect",
    acquire: "Acquire",
    hydrate: "Hydrate",
    probe_url: "Probe",
    analyze: "Analyze",
    status: "Status",
  };
  return labels[action] ?? "";
}

function ChatTypingIndicator({ label = "" }) {
  return (
    <div className="chat-typing" aria-live="polite" aria-label={label || "Assistant is thinking"}>
      <span className="chat-typing-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {label ? <span className="chat-typing-label">{label}</span> : null}
    </div>
  );
}

function ChatMessageBody({ message }) {
  const showTyping = message.streaming && message.thinking && !message.text;
  if (showTyping) return <ChatTypingIndicator label={message.activity || ""} />;
  if (!message.text) return null;
  return <ChatMarkdown text={message.text} />;
}

function safeChatHref(href) {
  try {
    const url = new URL(href, window.location.origin);
    if (["http:", "https:", "mailto:"].includes(url.protocol)) return url.href;
  } catch {
    /* render unsafe/invalid links as text */
  }
  return "";
}

function renderChatInline(line) {
  const nodes = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m;
  let k = 0;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) nodes.push(<span key={k++}>{line.slice(last, m.index)}</span>);
    const tok = m[0];
    if (tok.startsWith("**")) nodes.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) nodes.push(<code key={k++}>{tok.slice(1, -1)}</code>);
    else {
      const lm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok);
      const href = lm ? safeChatHref(lm[2]) : "";
      nodes.push(lm && href ? <a key={k++} href={href} target="_blank" rel="noreferrer">{lm[1]}</a> : <span key={k++}>{tok}</span>);
    }
    last = m.index + tok.length;
  }
  if (last < line.length) nodes.push(<span key={k++}>{line.slice(last)}</span>);
  return nodes;
}

function parseChatBlocks(text) {
  const blocks = [];
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) {
      i += 1;
      continue;
    }
    if (trimmed.startsWith("```")) {
      const lang = trimmed.slice(3).trim();
      const codeLines = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ type: "code", lang, text: codeLines.join("\n") });
      continue;
    }
    if (trimmed.startsWith("|") && trimmed.includes("|")) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        tableLines.push(lines[i].trim());
        i += 1;
      }
      blocks.push({ type: "table", lines: tableLines });
      continue;
    }
    const heading = /^#{1,3}\s+/.exec(trimmed);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[0].trim().length,
        text: trimmed.replace(/^#{1,3}\s+/, ""),
      });
      i += 1;
      continue;
    }
    if (/^---+$/.test(trimmed)) {
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }
    if (/^\d+[.)]\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+[.)]\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }
    const paras = [];
    while (i < lines.length) {
      const raw = lines[i];
      const t = raw.trim();
      if (!t) break;
      if (
        t.startsWith("```")
        || t.startsWith("|")
        || /^#{1,3}\s+/.test(t)
        || /^[-*]\s+/.test(t)
        || /^\d+[.)]\s+/.test(t)
        || /^---+$/.test(t)
      ) break;
      paras.push(raw);
      i += 1;
    }
    blocks.push({ type: "p", text: paras.join("\n") });
  }
  return blocks;
}

function ChatMarkdown({ text }) {
  if (!text) return null;
  const blocks = parseChatBlocks(text);
  return (
    <div className="chat-md">
      {blocks.map((block, i) => {
        if (block.type === "heading") {
          const Tag = block.level <= 2 ? "h3" : "h4";
          return (
            <Tag key={i} className={`chat-md-h${block.level}`}>
              {renderChatInline(block.text)}
            </Tag>
          );
        }
        if (block.type === "hr") return <hr key={i} className="chat-md-hr" />;
        if (block.type === "code") {
          return (
            <pre key={i} className="chat-md-code" data-lang={block.lang || undefined}>
              <code>{block.text}</code>
            </pre>
          );
        }
        if (block.type === "ul") {
          return (
            <ul key={i} className="chat-md-list">
              {block.items.map((item, j) => (
                <li key={j}>{renderChatInline(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === "ol") {
          return (
            <ol key={i} className="chat-md-list">
              {block.items.map((item, j) => (
                <li key={j}>{renderChatInline(item)}</li>
              ))}
            </ol>
          );
        }
        if (block.type === "table") {
          const rows = block.lines
            .map((row) => row.split("|").map((c) => c.trim()).filter((c, idx, arr) => !(idx === 0 && c === "") && !(idx === arr.length - 1 && c === "")))
            .filter((cells) => cells.length > 0 && !cells.every((c) => /^:?-+:?$/.test(c)));
          if (!rows.length) return null;
          const [head, ...body] = rows;
          return (
            <div key={i} className="chat-md-table-wrap">
              <table className="chat-md-table">
                <thead>
                  <tr>{head.map((c) => <th key={c}>{renderChatInline(c)}</th>)}</tr>
                </thead>
                <tbody>
                  {body.slice(0, 8).map((row, ri) => (
                    <tr key={ri}>
                      {row.map((c, ci) => (
                        <td key={`${ri}-${ci}`} title={c}>{String(c).slice(0, 64)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={i} className={block.text.startsWith("_") && block.text.endsWith("_") ? "muted" : ""}>
            {block.text.split("\n").map((line, li) => (
              <span key={li}>
                {li > 0 ? <br /> : null}
                {line ? renderChatInline(line) : "\u00a0"}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function trustTierMeta(tier) {
  const map = {
    lab_ready: { label: "Lab ready", tone: "green" },
    downloadable: { label: "Downloadable", tone: "green" },
    acquisition_route: { label: "Collect route", tone: "amber" },
    metadata_only: { label: "Metadata only", tone: "muted" },
    unknown: { label: "Unverified", tone: "muted" },
  };
  return map[tier] || map.unknown;
}

function CandidateList({ candidates, busy, onPreview, onCollect, comparePick = [], onToggleCompare }) {
  if (!candidates?.length) return null;
  return (
    <div className="yzu-candidates">
      {candidates.slice(0, 8).map((c) => {
        const trust = trustTierMeta(c.trust_tier);
        const selected = comparePick.includes(c.index);
        return (
          <div
            key={`${c.index}-${c.handle || c.doi || c.title}`}
            className={`yzu-candidate ${c.collect_via === "none" ? "muted-row" : ""} ${selected ? "compare-selected" : ""}`}
          >
            <div className="yzu-candidate-head">
              {onToggleCompare && (
                <button
                  type="button"
                  className={`yzu-compare-toggle ${selected ? "on" : ""}`}
                  title="Select to compare"
                  disabled={busy}
                  onClick={() => onToggleCompare(c.index)}
                  aria-pressed={selected}
                >
                  {selected ? "✓" : "+"}
                </button>
              )}
              <span className="yzu-candidate-idx">#{c.index}</span>
              <strong>{c.title || c.doi || "Dataset"}</strong>
              {c.score_pct != null && (
                <span className="yzu-candidate-score" title={`Relevance ${c.score ?? ""}`}>
                  {c.score_pct}%
                </span>
              )}
            </div>
            {c.score_pct != null && (
              <div className="yzu-score-bar" aria-hidden="true">
                <span style={{ width: `${Math.min(100, c.score_pct)}%` }} />
              </div>
            )}
            <div className="yzu-candidate-badges">
              <span className={`yzu-trust-pill tone-${trust.tone}`}>{trust.label}</span>
              {(c.badges || []).slice(0, 2).map((b) => (
                <span key={b} className="yzu-badge-pill">{b}</span>
              ))}
              {c.format && c.format !== "—" && <span className="yzu-badge-pill">{c.format}</span>}
              {c.license && c.license !== "—" && <span className="yzu-badge-pill license">{c.license}</span>}
            </div>
            <div className="yzu-candidate-meta muted small">
              {c.publisher && c.publisher !== "—" && <span>{c.publisher}</span>}
              {c.collect_via && c.collect_via !== "none" && <span> · via {c.collect_via}</span>}
              {c.file_summary && c.file_summary !== "—" && <span> · {c.file_summary}</span>}
              {c.status === "error" && <span> · unavailable</span>}
            </div>
            <div className="yzu-candidate-actions">
              <button type="button" className="yzu-chip small" disabled={busy} onClick={() => onPreview(c.index)}>
                Preview
              </button>
              {c.collect_via && c.collect_via !== "none" && (
                <button type="button" className="yzu-chip small primary" disabled={busy} onClick={() => onCollect(c.index)}>
                  Queue collect
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CandidateCompareTable({ table, busy, onSelect }) {
  if (!table?.rows?.length) return null;
  const cols = table.candidates || [];
  return (
    <div className="yzu-compare-table-wrap">
      <div className="yzu-compare-head">
        <strong>Comparison</strong>
        {table.recommendation && (
          <button
            type="button"
            className="yzu-chip small primary"
            disabled={busy}
            onClick={() => onSelect?.(`preview #${table.recommendation.index}`)}
          >
            Best pick · #{table.recommendation.index}
          </button>
        )}
      </div>
      <table className="yzu-compare-table">
        <thead>
          <tr>
            <th />
            {cols.map((c) => (
              <th key={c.index}>#{c.index} {String(c.title || "").slice(0, 36)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.field}>
              <th>{row.label}</th>
              {row.values.map((val, i) => (
                <td key={`${row.field}-${i}`} title={String(val)}>{String(val).slice(0, 64)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.recommendation?.reason && (
        <p className="muted small yzu-compare-note">{table.recommendation.reason}</p>
      )}
    </div>
  );
}

function SuggestedPrompts({ prompts, busy, onSelect }) {
  if (!prompts?.length) return null;
  return (
    <div className="yzu-suggested-prompts">
      {prompts.map((p) => (
        <button key={p} type="button" className="yzu-chip small" disabled={busy} onClick={() => onSelect(p)}>
          {p}
        </button>
      ))}
    </div>
  );
}

function PreviewTable({ preview }) {
  if (!preview?.rows?.length) return null;
  const cols = preview.columns?.length ? preview.columns : Object.keys(preview.rows[0] || {});
  return (
    <div className="yzu-preview-table-wrap">
      <table className="yzu-preview-table">
        <thead>
          <tr>{cols.slice(0, 8).map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {preview.rows.slice(0, 5).map((row, i) => (
            <tr key={i}>
              {cols.slice(0, 8).map((c) => (
                <td key={c} title={String(row[c] ?? "")}>{String(row[c] ?? "").slice(0, 48)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatBytes(n) {
  const size = Number(n || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function CollectOutcome({ promotion, campaignId, procuredFiles, jobStatus }) {
  if (!promotion?.length && !campaignId && !procuredFiles?.length) return null;
  return (
    <div className="yzu-collect-outcome">
      {campaignId && <span className="yzu-outcome-pill">Campaign {String(campaignId).slice(0, 8)}</span>}
      {jobStatus === "completed" && !procuredFiles?.length && (
        <span className="yzu-outcome-pill ok">Collect complete</span>
      )}
      {(procuredFiles || []).map((f) => (
        <span key={f.path} className="yzu-outcome-pill ok" title={f.path}>
          {f.name || "file"} · {formatBytes(f.bytes)}
        </span>
      ))}
      {(promotion || []).map((p) => (
        <span key={p.dataset_id} className="yzu-outcome-pill ok">
          Registry · {p.dataset_id}
        </span>
      ))}
    </div>
  );
}

function NextStepsRail({ steps, busy, onSelect, onOpenPath }) {
  if (!steps?.length) return null;
  return (
    <div className="yzu-next-steps">
      <span className="yzu-next-steps-label">Next</span>
      {steps.map((s, i) => {
        if (s.download_url) {
          const href = s.download_url.startsWith("http") ? s.download_url : `${API}${s.download_url}`;
          return (
            <a key={i} className="yzu-chip small primary" href={href} target="_blank" rel="noreferrer">
              {s.label || s.path}
            </a>
          );
        }
        if (s.path) {
          return (
            <span key={i} className="yzu-chip small primary" title={s.path}>
              {s.label || s.path.split("/").pop()}
            </span>
          );
        }
        return (
          <button
            key={i}
            type="button"
            className="yzu-chip small primary"
            disabled={busy}
            onClick={() => onSelect(s.prompt || s.label)}
          >
            {s.label}
          </button>
        );
      })}
    </div>
  );
}

function PendingActions({ message, busy, onApproveJob, onApproveLicense }) {
  const artifacts = message.artifacts || {};
  const job = artifacts.job || {};
  const pendingId = message.pendingJobId || artifacts.state_patch?.pending_job_id || job.id;
  const jobPending = job.status === "pending_approval" || (pendingId && !["completed", "running", "failed"].includes(job.status));
  const blocked = message.blocked || artifacts.blocked;
  const gate = message.gate || artifacts.gate || {};
  const licenseDoi = gate.doi || artifacts.state_patch?.pending_license_doi;

  if (!jobPending && !blocked) return null;

  return (
    <div className="yzu-pending-actions">
      {jobPending && pendingId && (
        <button type="button" className="yzu-chip small primary" disabled={busy} onClick={() => onApproveJob(pendingId)}>
          Launch job {String(pendingId).slice(0, 8)}
        </button>
      )}
      {blocked && licenseDoi && (
        <button type="button" className="yzu-chip small primary" disabled={busy} onClick={() => onApproveLicense(licenseDoi, gate)}>
          Approve license for {licenseDoi}
        </button>
      )}
    </div>
  );
}

const AskPanel = React.forwardRef(function AskPanel(
  {
    onRefresh,
    profile,
    userEmail,
    datasets = [],
    onNeedSignIn,
    variant = "card",
    contextHint = "",
    assistantActions = [],
    selectedDataset = null,
    onClearScope = null,
  },
  ref,
) {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("procure_session_id") || "");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [campaigns, setCampaigns] = useState([]);
  const [pins, setPins] = useState([]);
  const [labOpen, setLabOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [comparePick, setComparePick] = useState([]);
  const chatEndRef = useRef(null);

  const formalLabel = facultyFormalLabel(profile);
  const actions = assistantActions.length
    ? assistantActions
    : GENERIC_STARTERS.map((prompt) => ({ label: prompt.replace(/\?$/, ""), prompt }));
  const activeCampaigns = campaigns.filter((c) => !["ready", "failed"].includes(c.phase));
  const composerPlaceholder = selectedDataset
    ? `Ask about ${datasetDisplayName(selectedDataset)}…`
    : "Dataset, DOI, URL, or source...";

  useEffect(() => {
    if (variant === "main" && messages.length === 0 && window.innerWidth > 900) setLabOpen(true);
  }, [variant, messages.length]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function loadLab() {
    try {
      const [camp, pinData] = await Promise.all([
        fetch(`${API}/library/campaigns?limit=12`).then((r) => r.json()),
        fetch(`${API}/library/pins?limit=12`).then((r) => r.json()),
      ]);
      setCampaigns(camp.campaigns || []);
      setPins(pinData.pins || []);
    } catch {
      /* keep cached */
    }
  }

  async function restoreSession(sid) {
    if (!sid) return;
    try {
      const r = await fetch(`${API}/library/chat/${sid}`);
      const data = await r.json();
      if (!r.ok) return;
      const state = data.state || {};
      const raw = data.messages || [];
      let lastAssistantIdx = -1;
      raw.forEach((m, i) => {
        if (m.role === "assistant") lastAssistantIdx = i;
      });
      const msgs = raw.map((m, i) => parseStoredMessage(m, state, i === lastAssistantIdx));
      setMessages(msgs);
    } catch {
      /* fresh session */
    }
  }

  async function warmDeskSession() {
    const email = userEmail || localStorage.getItem("procure_user_email") || "";
    try {
      const res = await fetch(`${API}/library/desk/warm`, {
        method: "POST",
        headers: deskHeaders(),
        body: JSON.stringify({
          user_email: email || undefined,
          session_id: sessionId || undefined,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.session_id) {
        setSessionId(data.session_id);
        localStorage.setItem("procure_session_id", data.session_id);
      }
    } catch {
      /* background priming only */
    }
  }

  useEffect(() => {
    loadLab();
    warmDeskSession();
    if (sessionId) restoreSession(sessionId);
  }, []);

  function toggleCompare(idx) {
    setComparePick((prev) => {
      if (prev.includes(idx)) return prev.filter((x) => x !== idx);
      if (prev.length >= 2) return [prev[1], idx];
      return [...prev, idx];
    });
  }

  function runCompare() {
    if (comparePick.length !== 2) return;
    const [a, b] = [...comparePick].sort((x, y) => x - y);
    sendChat(`compare ${a} and ${b}`);
  }

  async function sendChat(text = input) {
    const prompt = text.trim();
    if (!prompt || busy) return;
    const needsAuth = /\b(collect|download|approve|source this)\b/i.test(prompt);
    if (needsAuth && !userEmail) {
      onNeedSignIn?.();
      return;
    }
    setMessages((m) => [...m, { role: "user", text: prompt }]);
    setInput("");
    setBusy(true);
    setStatus("Composer is planning...");
    setMessages((m) => [...m, { role: "assistant", text: "", streaming: true, thinking: true, activity: "Composer is planning..." }]);

    const started = Date.now();
    let streamedAnswer = false;
    const tick = window.setInterval(() => {
      const secs = Math.floor((Date.now() - started) / 1000);
      setStatus((prev) => {
        if (!prev) return prev;
        const base = prev.replace(/\s+\(\d+s\)$/, "");
        return secs >= 8 ? `${base} (${secs}s)` : base;
      });
    }, 1000);

    function appendStreamingDelta(chunk) {
      streamedAnswer = true;
      setMessages((m) => m.map((item) => (
        item.streaming
          ? { ...item, thinking: false, text: `${item.text || ""}${chunk}` }
          : item
      )));
      setStatus("");
    }

    function setStreamingActivity(text) {
      if (streamedAnswer) return;
      setMessages((m) => m.map((item) => (
        item.streaming ? { ...item, activity: text } : item
      )));
      if (text) setStatus(text);
    }

    function applyResult(out) {
      if (out.session_id) {
        setSessionId(out.session_id);
        localStorage.setItem("procure_session_id", out.session_id);
      }
      const artifacts = out.artifacts || {};
      setMessages((m) => {
        const trimmed = m.filter((x) => !x.streaming);
        return [
          ...trimmed,
          {
            role: "assistant",
            text: out.reply,
            action: out.action,
            campaignId: out.campaign_id,
            preview: out.preview || artifacts.preview || null,
            candidates: out.candidates || artifacts.candidates || [],
            suggestedPrompts: out.suggested_prompts || [],
            artifacts,
            blocked: artifacts.blocked,
            gate: artifacts.gate,
            pendingJobId: artifacts.job?.id || artifacts.state_patch?.pending_job_id,
            registryPromotion: out.registry_promotion || artifacts.registry_promotion,
            procuredFiles: artifacts.procured_files || [],
            jobStatus: artifacts.job?.status,
            nextSteps: out.next_steps || artifacts.next_steps || [],
            compareTable: out.compare_table || artifacts.compare_table || null,
          },
        ];
      });
      setComparePick([]);
      setStatus(out.campaign_id ? `Campaign ${out.campaign_id.slice(0, 8)}…` : "");
      if (["collect", "acquire", "collect_doi", "approve_collect"].includes(out.action)) {
        loadLab();
        onRefresh?.();
      }
    }

    async function readChatStream(res) {
      if (!res.body) throw new Error("Chat stream unavailable");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let result = null;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === "delta" && event.text) {
            appendStreamingDelta(event.text);
          }
          if (event.type === "activity" && event.text) {
            setStreamingActivity(event.text);
          }
          if (event.type === "progress" && event.text) {
            setStreamingActivity(event.text);
          }
          if (event.type === "error") {
            throw new Error(event.message || event.error || "Chat stream error");
          }
          if (event.type === "complete") {
            result = event.result || null;
          }
        }
      }
      if (!result) throw new Error("Chat ended without a response");
      return result;
    }

    try {
      let out;
      const streamRes = await fetch(`${API}/library/chat/stream`, {
        method: "POST",
        headers: deskHeaders(),
        body: JSON.stringify({
          message: prompt,
          session_id: sessionId || undefined,
          user_email: userEmail || localStorage.getItem("procure_user_email") || undefined,
        }),
      });
      if (streamRes.ok && (streamRes.headers.get("content-type") || "").includes("ndjson")) {
        out = await readChatStream(streamRes);
      } else {
        const fallback = await fetch(`${API}/library/chat`, {
          method: "POST",
          headers: deskHeaders(),
          body: JSON.stringify({
            message: prompt,
            session_id: sessionId || undefined,
            user_email: userEmail || localStorage.getItem("procure_user_email") || undefined,
          }),
        }).then(async (r) => {
          const p = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(p.message || p.error || "Chat error");
          return p;
        });
        out = fallback;
      }
      applyResult(out);
    } catch (err) {
      setMessages((m) => [...m.filter((x) => !x.streaming), { role: "error", text: err.message }]);
      setStatus(err.message);
    } finally {
      window.clearInterval(tick);
      setBusy(false);
    }
  }

  async function approveJob(jobId) {
    if (!jobId || busy) return;
    setBusy(true);
    setStatus("Launching job…");
    try {
      let r = await fetch(`${API}/library/jobs/${jobId}/approve`, {
        method: "POST",
        headers: deskHeaders(),
        body: "{}",
      });
      if (!r.ok && r.status === 404) {
        r = await fetch(`${API}/yzu/jobs/${jobId}/approve`, {
          method: "POST",
          headers: deskHeaders(),
          body: "{}",
        });
      }
      const p = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(p.message || p.error || "Approve failed");
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: `Job \`${jobId}\` approved and queued on the cluster worker.`,
          action: "approve_collect",
        },
      ]);
      loadLab();
      onRefresh?.();
      setStatus("");
    } catch (err) {
      setMessages((m) => [...m, { role: "error", text: err.message }]);
      setStatus(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function approveLicense(doi, gate) {
    if (!doi || busy) return;
    setBusy(true);
    setStatus("Approving license…");
    try {
      const r = await fetch(`${API}/library/licenses/approve`, {
        method: "POST",
        headers: deskHeaders(),
        body: JSON.stringify({
          doi,
          license: gate?.license_text || gate?.license || "",
          note: "approved via desk",
        }),
      });
      const p = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(p.message || p.error || "License approval failed");
      const prompt = `collect ${doi}`;
      setInput(prompt);
      await sendChat(prompt);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", text: err.message }]);
      setStatus(err.message);
      setBusy(false);
    }
  }

  function newSession() {
    setSessionId("");
    localStorage.removeItem("procure_session_id");
    setMessages([]);
    setStatus("");
    warmDeskSession();
  }

  React.useImperativeHandle(ref, () => ({
    sendChat,
  }));

  if (variant === "home") {
    if (!messages.length && !busy) return null;
    return (
      <div className="rd-answer">
        {messages.filter((m) => m.role !== "user").slice(-1).map((m, i) => (
          <div key={i} className={m.role === "error" ? "error" : ""}><ChatMarkdown text={m.text} /></div>
        ))}
      </div>
    );
  }

  if (variant === "quiet" && messages.length === 0 && !busy) {
    return null;
  }

  const showCardShell = variant === "card";
  const showMainShell = variant === "main";
  const chatClass = showCardShell || showMainShell ? "yzu-chat-rail" : "";

  return (
    <div className={`yzu-procure ${labOpen ? "lab-open" : ""} ${variant}`}>
      {variant === "card" && (
        <header className="ds-console-head ds-console-head-minimal">
          <h3>Assistant</h3>
          <div className="yzu-procure-actions">
            <button type="button" className="yzu-chip small" onClick={newSession} disabled={busy}>
              New session
            </button>
          </div>
        </header>
      )}
      {showMainShell && (
        <div className="rd-chat-toolbar">
          <button type="button" className="yzu-chip small" onClick={newSession} disabled={busy}>
            New session
          </button>
          <button
            type="button"
            className={`yzu-chip small ${labOpen ? "active" : ""}`}
            onClick={() => setLabOpen((v) => !v)}
          >
            Lab{datasets.length ? ` · ${datasets.length} datasets` : ""}
            {activeCampaigns.length > 0 ? ` · ${activeCampaigns.length} job${activeCampaigns.length === 1 ? "" : "s"}` : ""}
          </button>
          {status && <span className="rd-chat-status muted small">{status}</span>}
        </div>
      )}
      {variant === "full" && (
        <header className="yzu-procure-head">
          <div>
            <p className="crumb">Home</p>
            <h1>{formalLabel ? `${formalLabel}'s desk` : "Research data, organized like files."}</h1>
            <p className="lead muted">Browse the library or ask the assistant to source missing datasets.</p>
            {status && <p className="muted small">{status}</p>}
          </div>
          <div className="yzu-procure-actions">
            <button
              type="button"
              className={`yzu-chip small ${labOpen ? "active" : ""}`}
              onClick={() => setLabOpen((v) => !v)}
            >
              Lab{datasets.length ? ` · ${datasets.length}` : ""}
              {activeCampaigns.length > 0 ? ` · ${activeCampaigns.length} active` : ""}
            </button>
            <button type="button" className="yzu-chip small" onClick={newSession} disabled={busy}>
              New
            </button>
          </div>
        </header>
      )}

      <div className="yzu-procure-body">
        <section className="yzu-agent">
          <div className={`yzu-chat yzu-chat-card ${chatClass}`}>
            {messages.length === 0 && variant !== "quiet" && (
              <article className="agent empty">
                {selectedDataset && (
                  <p className="rd-assistant-hint">
                    <strong>{datasetDisplayName(selectedDataset)}</strong>
                    {" — "}
                    {contextHint}
                  </p>
                )}
                {!selectedDataset && !showMainShell && <p className="rd-assistant-hint">{contextHint}</p>}
                {!selectedDataset && showMainShell && (
                  <p className="rd-assistant-hint muted">Start with a dataset, DOI, URL, or source. Composer checks the local index before external sourcing.</p>
                )}
                {actions.length > 0 && <p className="rd-suggest-label">Suggested</p>}
                <div className="yzu-advice-recs">
                  {actions.map((action) => (
                    <button
                      key={action.label}
                      type="button"
                      className="yzu-chip small"
                      disabled={busy}
                      onClick={() => sendChat(action.prompt)}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </article>
            )}
            {messages.map((m, i) => (
              <article
                key={i}
                className={[m.role, m.streaming ? "streaming" : ""].filter(Boolean).join(" ")}
              >
                {m.role !== "user" && !m.streaming && formatActionLabel(m.action) && (
                  <small className="yzu-action-label">{formatActionLabel(m.action)}</small>
                )}
                <ChatMessageBody message={m} />
                {m.role === "assistant" && !m.streaming && (
                  <CollectOutcome
                    promotion={m.registryPromotion}
                    campaignId={m.campaignId}
                    procuredFiles={m.procuredFiles}
                    jobStatus={m.jobStatus}
                  />
                )}
                {m.role === "assistant" && !m.streaming && (
                  <CandidateList
                    candidates={m.candidates}
                    busy={busy}
                    onPreview={(idx) => sendChat(`preview #${idx}`)}
                    onCollect={(idx) => sendChat(`download #${idx}`)}
                    comparePick={comparePick}
                    onToggleCompare={m.candidates?.length > 1 ? toggleCompare : null}
                  />
                )}
                {m.role === "assistant" && !m.streaming && m.compareTable && (
                  <CandidateCompareTable table={m.compareTable} busy={busy} onSelect={sendChat} />
                )}
                {m.role === "assistant" && !m.streaming && (
                  <PendingActions
                    message={m}
                    busy={busy}
                    onApproveJob={approveJob}
                    onApproveLicense={approveLicense}
                  />
                )}
                {m.role === "assistant" && !m.streaming && (
                  <NextStepsRail steps={m.nextSteps} busy={busy} onSelect={sendChat} />
                )}
                {m.role === "assistant" && !m.streaming && (
                  <SuggestedPrompts
                    prompts={(m.suggestedPrompts || []).filter(
                      (p) => !(m.nextSteps || []).some((ns) => ns.prompt === p || ns.label === p)
                    )}
                    busy={busy}
                    onSelect={sendChat}
                  />
                )}
                {!m.streaming && <PreviewTable preview={m.preview} />}
              </article>
            ))}
            <div ref={chatEndRef} />
          </div>

          {variant !== "quiet" && (
          <div className="yzu-composer">
            {selectedDataset && onClearScope && (
              <div className="rd-scope-bar">
                <span className="rd-scope-chip">@{datasetDisplayName(selectedDataset)}</span>
                <button type="button" className="rd-scope-clear" onClick={onClearScope}>
                  Clear
                </button>
              </div>
            )}
            {comparePick.length === 2 && (
              <div className="yzu-compare-bar">
                <span className="muted small">Compare #{comparePick[0]} and #{comparePick[1]}</span>
                <button type="button" className="yzu-chip small primary" disabled={busy} onClick={runCompare}>
                  Compare
                </button>
                <button type="button" className="yzu-chip small" disabled={busy} onClick={() => setComparePick([])}>
                  Clear
                </button>
              </div>
            )}
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={variant === "card" || variant === "main" ? 2 : 3}
              placeholder={composerPlaceholder}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendChat();
                }
              }}
            />
            <button type="button" className="primary" disabled={busy} onClick={() => sendChat()}>
              {busy ? "…" : variant === "card" || variant === "main" ? "Ask" : "Send"}
            </button>
          </div>
          )}
        </section>

        {labOpen && variant !== "card" && (
          <aside className="yzu-lab-rail">
            <section>
              <h3>Procured</h3>
              {pins.length === 0 ? (
                <p className="muted small">No pinned datasets yet.</p>
              ) : (
                pins.slice(0, 8).map((p) => (
                  <button
                    key={p.handle || p.doi}
                    type="button"
                    className="yzu-lab-item"
                    disabled={busy}
                    onClick={() => sendChat(`preview ${p.handle || p.doi}`)}
                  >
                    <strong>{(p.title || p.handle || p.doi || "").slice(0, 56)}</strong>
                    <small>pinned · {p.handle || p.doi}</small>
                  </button>
                ))
              )}
            </section>
            <section>
              <h3>Registry</h3>
              {datasets.length === 0 ? (
                <p className="muted small">Nothing staged yet.</p>
              ) : (
                datasets.slice(0, 8).map((d) => (
                  <button
                    key={d.dataset_id}
                    type="button"
                    className="yzu-lab-item"
                    disabled={busy}
                    onClick={() => sendChat(`Tell me about ${d.dataset_id} (${d.name || d.dataset_id}) and how to extend it`)}
                  >
                    <strong>{d.name || d.dataset_id}</strong>
                    <small>{d.domain || d.dataset_id}</small>
                  </button>
                ))
              )}
            </section>
            <section>
              <h3>Collections</h3>
              {campaigns.length === 0 ? (
                <p className="muted small">No active collections.</p>
              ) : (
                campaigns.slice(0, 8).map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className="yzu-lab-item"
                    disabled={busy}
                    onClick={() => sendChat(`Continue: ${c.goal || c.id}`)}
                  >
                    <strong>{(c.goal || c.id).slice(0, 56)}</strong>
                    <small>{c.phase} · {fmtTime(c.updated_at)}</small>
                  </button>
                ))
              )}
            </section>
          </aside>
        )}
      </div>
    </div>
  );
});
function Jobs({ jobs, onRefresh, pendingTotal = 0 }) {
  const [expanded, setExpanded] = useState(null);
  const [queueTasks, setQueueTasks] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [busy, setBusy] = useState("");
  const [filter, setFilter] = useState("all");
  const [jobsError, setJobsError] = useState("");
  const [jobsNotice, setJobsNotice] = useState("");

  const visibleJobs = useMemo(() => {
    if (filter === "pending") return jobs.filter((j) => j.status === "pending_approval");
    return jobs;
  }, [jobs, filter]);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/yzu/queue/tasks`).then((r) => r.json()),
      fetch(`${API}/yzu/schedules`).then((r) => r.json()),
    ]).then(([q, s]) => {
      setQueueTasks(q.tasks || []);
      setSchedules(s.schedules || []);
    }).catch(() => {});
  }, []);

  async function approve(id) {
    setBusy(id);
    setJobsError("");
    setJobsNotice("");
    try {
      const r = await fetch(`${API}/yzu/jobs/${id}/approve`, { method: "POST", headers: deskHeaders(), body: "{}" });
      const p = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(p.message || p.error || "Approve failed");
    } catch (err) {
      setJobsError(err.message || "Approve failed");
    } finally {
      setBusy("");
      onRefresh();
    }
  }

  async function approveSafe() {
    setBusy("approve-safe");
    setJobsError("");
    setJobsNotice("");
    try {
      const r = await fetch(`${API}/yzu/jobs/approve-safe`, { method: "POST", headers: deskHeaders(), body: "{}" });
      const p = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(p.message || p.error || "Approve-safe failed");
      setJobsNotice(`Approved ${p.approved_count ?? 0} safe job(s). Skipped ${p.skipped_count ?? 0}.`);
    } catch (err) {
      setJobsError(err.message || "Approve-safe failed");
    } finally {
      setBusy("");
      onRefresh();
    }
  }

  async function cancel(id) {
    setBusy(id);
    setJobsError("");
    setJobsNotice("");
    try {
      const r = await fetch(`${API}/yzu/jobs/${id}/cancel`, { method: "POST", headers: deskHeaders(), body: "{}" });
      const p = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(p.message || p.error || "Cancel failed");
    } catch (err) {
      setJobsError(err.message || "Cancel failed");
    } finally {
      setBusy("");
      onRefresh();
    }
  }

  async function launchTask(taskId) {
    setBusy(taskId);
    await fetch(`${API}/yzu/jobs`, {
      method: "POST",
      headers: deskHeaders(),
      body: JSON.stringify({
        title: `Collection: ${taskId}`,
        plan: { job_type: "collection_queue_task", task_id: taskId, launchable: true },
      }),
    });
    setBusy("");
    onRefresh();
  }

  async function launchBatch() {
    setBusy("batch");
    await fetch(`${API}/yzu/jobs`, {
      method: "POST",
      headers: deskHeaders(),
      body: JSON.stringify({
        title: "Public collection queue batch",
        plan: { job_type: "collection_queue_batch", launchable: true, timeout_seconds: 14400 },
        auto_approve: true,
      }),
    });
    setBusy("");
    onRefresh();
  }

  async function launchBigQueryDryRun() {
    setBusy("bq");
    await fetch(`${API}/yzu/jobs`, {
      method: "POST",
      headers: deskHeaders(),
      body: JSON.stringify({
        title: "USDT daily flows — BigQuery dry-run",
        auto_approve: true,
        plan: {
          job_type: "bigquery_query",
          sql_file: "sql/bigquery/usdt/01_daily_usdt_flows_recent.sql",
          dry_run: true,
          launchable: true,
        },
      }),
    });
    setBusy("");
    onRefresh();
  }

  async function runSchedule(id) {
    setBusy(id);
    await fetch(`${API}/yzu/schedules/${id}/run`, { method: "POST", headers: deskHeaders(), body: "{}" });
    setBusy("");
    onRefresh();
  }

  function tone(status) {
    if (status === "completed") return "green";
    if (status === "failed") return "red";
    if (status === "pending_approval") return "amber";
    return "blue";
  }

  return (
    <>
      <header className="yzu-page-head">
        <div>
          <h1>Procurement jobs</h1>
          <p>Unified YZU queue — agent, collection tasks, pipelines, harvest control</p>
        </div>
        <div className="yzu-page-actions">
          {pendingTotal > 0 && (
            <button className="yzu-chip" disabled={!!busy} onClick={approveSafe}>
              Approve safe ({pendingTotal})
            </button>
          )}
          <button className="primary" onClick={launchBatch} disabled={!!busy}>Run full queue</button>
        </div>
      </header>

      {jobsError && <div className="yzu-banner error">{jobsError}</div>}
      {jobsNotice && <div className="yzu-banner ok">{jobsNotice}</div>}

      <div className="yzu-job-filters">
        <button type="button" className={`yzu-chip small ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>
          All ({jobs.length})
        </button>
        <button type="button" className={`yzu-chip small ${filter === "pending" ? "active" : ""}`} onClick={() => setFilter("pending")}>
          Pending ({jobs.filter((j) => j.status === "pending_approval").length})
        </button>
      </div>

      {schedules.length > 0 && (
        <section className="yzu-quick-launch">
          <h2>Schedules</h2>
          <div className="yzu-chip-row">
            {schedules.map((s) => (
              <button key={s.id} className="yzu-chip" disabled={!!busy} onClick={() => runSchedule(s.id)}>
                {s.title} {s.enabled ? "" : "(off)"}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="yzu-quick-launch">
        <h2>Quick launch — analytics</h2>
        <div className="yzu-chip-row">
          <button className="yzu-chip" disabled={!!busy} onClick={launchBigQueryDryRun}>
            BigQuery USDT dry-run
          </button>
        </div>
      </section>

      <section className="yzu-quick-launch">
        <h2>Quick launch — collection tasks</h2>
        <div className="yzu-chip-row">
          {queueTasks.slice(0, 8).map((t) => (
            <button key={t.id} className="yzu-chip" disabled={!!busy} onClick={() => launchTask(t.id)} title={t.output_hint}>
              {t.id}
            </button>
          ))}
        </div>
      </section>

      <section className="yzu-table jobs">
        <div className="yzu-row head"><span>Job</span><span>Type</span><span>Status</span><span>Actions</span></div>
        {visibleJobs.length === 0 ? <p className="muted pad">No jobs in this view.</p> : visibleJobs.map((job) => (
          <React.Fragment key={job.id}>
            <div className={`yzu-row job-row ${expanded === job.id ? "selected" : ""}`} onClick={() => setExpanded(expanded === job.id ? null : job.id)} role="button" tabIndex={0}>
              <span className="primary"><strong>{job.title}</strong><small>{job.id} · {fmtTime(job.updated_at)}</small></span>
              <span>{job.plan?.job_type || "—"}</span>
              <span><Badge tone={tone(job.status)}>{job.status}</Badge></span>
              <span className="yzu-job-actions" onClick={(e) => e.stopPropagation()}>
                {job.status === "pending_approval" && <button className="primary" disabled={busy === job.id} onClick={() => approve(job.id)}>Approve</button>}
                {["pending_approval", "queued"].includes(job.status) && <button disabled={busy === job.id} onClick={() => cancel(job.id)}>Cancel</button>}
              </span>
            </div>
            {expanded === job.id && (
              <div className="yzu-job-detail">
                {job.error && <p className="error">{job.error}</p>}
                {job.result && Object.keys(job.result).length > 0 && <pre>{JSON.stringify(job.result, null, 2)}</pre>}
                <ul>
                  {(job.events || []).slice(-8).map((ev, i) => (
                    <li key={i}><time>{fmtTime(ev.created_at)}</time> <span>{ev.level}</span> {ev.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </React.Fragment>
        ))}
      </section>
    </>
  );
}

function CredentialsVault() {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/library/credentials/profiles`)
      .then((r) => r.json())
      .then((data) => setProfiles(data.profiles || []))
      .catch((err) => setError(err.message || "Failed to load profiles"))
      .finally(() => setLoading(false));
  }, []);

  const configured = profiles.filter((p) => p.configured).length;

  return (
    <>
      <header className="yzu-page-head">
        <div>
          <h1>Credential vault</h1>
          <p>
            Env-backed tokens for gated sources — {configured}/{profiles.length} configured on this controller.
          </p>
        </div>
      </header>

      {error && <div className="yzu-banner error">{error}</div>}
      {loading ? (
        <p className="muted pad">Loading profiles…</p>
      ) : profiles.length === 0 ? (
        <p className="muted pad">
          No profiles yet. Copy <code>config/procurement_credentials.example.json</code> into{" "}
          <code>data_lake/procurement_memory/credentials.json</code>.
        </p>
      ) : (
        <section className="yzu-table credentials">
          <div className="yzu-row head">
            <span>Source</span>
            <span>Env var</span>
            <span>Status</span>
            <span>Domains</span>
          </div>
          {profiles.map((p) => (
            <div className="yzu-row" key={p.id}>
              <span className="primary">
                <strong>{p.label || p.id}</strong>
                <small>{p.id}</small>
              </span>
              <span>
                <code>{p.env_var || "—"}</code>
              </span>
              <span>
                <Badge tone={p.configured ? "green" : p.required ? "red" : "amber"}>
                  {p.configured ? "configured" : p.required ? "required" : "optional"}
                </Badge>
              </span>
              <span className="muted small">{(p.domains || []).join(", ") || "—"}</span>
            </div>
          ))}
        </section>
      )}
      <p className="muted pad small">
        In chat, say <strong>credential profiles</strong> for the same list. Set env vars on the controller and restart the API worker.
      </p>
    </>
  );
}

function Workers({ data, liveLoading, onRefreshLive }) {
  if (!data) {
    return (
      <>
        <header className="yzu-page-head"><div><h1>Worker pools</h1><p>SSH-probing Windows lab + DataCite shards…</p></div></header>
        <p className="muted pad">{liveLoading ? "Live probe in progress (~30s)…" : "No worker data yet."}</p>
        {!liveLoading && <button className="primary pad" onClick={onRefreshLive}>Probe workers</button>}
      </>
    );
  }
  const spectator = data.spectator || {};
  return (
    <>
      <header className="yzu-page-head">
        <div>
          <h1>Worker pools</h1>
          <p>Windows lab + local controller + Spectator scrape host</p>
        </div>
        <button onClick={onRefreshLive} disabled={liveLoading}>{liveLoading ? "Probing…" : "Live probe"}</button>
      </header>
      <h2 className="section-label">Windows lab</h2>
      <section className="yzu-table workers">
        <div className="yzu-row head"><span>Host</span><span>IP</span><span>SSH</span></div>
        {(data.windows_lab || []).map((n) => (
          <div className="yzu-row" key={n.tailscale_ip}>
            <span>{n.hostname}</span><span>{n.tailscale_ip}</span>
            <span><Badge tone={n.ssh_ok ? "green" : "red"}>{n.ssh_ok ? "ok" : "down"}</Badge></span>
          </div>
        ))}
      </section>
      <h2 className="section-label">DataCite shards (y2025)</h2>
      <section className="yzu-table workers">
        <div className="yzu-row head"><span>Shard</span><span>Host</span><span>Progress</span><span>Rate</span></div>
        {(data.datacite_shards || []).map((s) => (
          <div className="yzu-row" key={s.shard}>
            <span>{s.shard}</span><span>{s.host}</span>
            <span>{s.percent}% ({s.progress?.toLocaleString()})</span>
            <span>{s.rate_per_sec ? `${s.rate_per_sec}/s` : "—"}</span>
          </div>
        ))}
      </section>
      <h2 className="section-label">Spectator ({spectator.host || "—"})</h2>
      {spectator.enabled !== false && spectator.host && (
      <section className="yzu-table workers">
        <div className="yzu-row head"><span>Host</span><span>IP</span><span>Capabilities</span></div>
        <div className="yzu-row">
          <span>{spectator.host}</span>
          <span>{spectator.tailscale_ip}</span>
          <span>{(spectator.capabilities || []).join(", ") || "—"}</span>
        </div>
      </section>
      )}
      <h2 className="section-label">Storage</h2>
      <section className="yzu-table workers">
        <div className="yzu-row head"><span>Local staging</span><span>Cold archive</span></div>
        <div className="yzu-row">
          <span>{data.storage?.local_staging || "—"}</span>
          <span className="mono">{data.storage?.drive_root || "—"}</span>
        </div>
      </section>
    </>
  );
}

function Inspector({ item, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return undefined;
    const t = setInterval(async () => {
      const r = await fetch(`${API}/yzu/jobs/${job.id}`);
      if (r.ok) setJob(await r.json());
    }, 2000);
    return () => clearInterval(t);
  }, [job]);

  async function ask(text = input) {
    const prompt = text.trim();
    if (!prompt || busy) return;
    const scoped = `Regarding dataset ${item.id} (${item.name}): ${prompt}`;
    setMessages((m) => [...m, { role: "user", text: prompt }]);
    setInput("");
    setBusy(true);
    try {
      const r = await fetch(`${API}/library/chat`, {
        method: "POST",
        headers: deskHeaders(),
        body: JSON.stringify({
          message: scoped,
          user_email: localStorage.getItem("procure_user_email") || undefined,
        }),
      });
      const p = await r.json();
      if (!r.ok) throw new Error(p.message || p.error || "Chat error");
      setMessages((m) => [
        ...m,
        {
          role: "agent",
          text: p.reply || p.message || "No reply.",
          job: p.job,
        },
      ]);
      if (p.job) setJob(p.job);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", text: err.message }]);
    } finally {
      setBusy(false);
    }
  }

  async function launch() {
    setBusy(true);
    try {
      const r = await fetch(`${API}/yzu/jobs/${job.id}/approve`, { method: "POST", headers: deskHeaders(), body: "{}" });
      const p = await r.json();
      if (!r.ok) throw new Error(p.message);
      setJob(p);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", text: err.message }]);
    } finally {
      setBusy(false);
    }
  }

  async function restartShard(shard) {
    setBusy(true);
    try {
      const r = await fetch(`${API}/yzu/jobs`, {
        method: "POST",
        headers: deskHeaders(),
        body: JSON.stringify({
          title: `Restart ${shard}`,
          plan: { job_type: "harvest_shard", shard, action: "restart", launchable: true },
          auto_approve: true,
        }),
      });
      const p = await r.json();
      if (!r.ok) throw new Error(p.message || "submit failed");
      setJob(p);
      setMessages((m) => [...m, { role: "agent", text: `Queued harvest control for ${shard}` }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", text: err.message }]);
    } finally {
      setBusy(false);
    }
  }

  const shards = item.detail?.y2025_shards || item.detail?.shards;

  return (
    <div className="yzu-inspector-inner">
      <div className="yzu-inspector-head">
        <div><h2>{item.name}</h2><p>{item.subtitle}</p></div>
        <button onClick={onClose}>×</button>
      </div>
      <dl className="yzu-kv">
        <dt>Scope</dt><dd>{item.scope}</dd>
        <dt>Stage</dt><dd>{item.stage}</dd>
        <dt>Amount</dt><dd>{item.amount}</dd>
        <dt>Destination</dt><dd>{item.destination}</dd>
      </dl>
      {item.id === "datacite" && shards && (
        <section>
          <h3>Shard control</h3>
          {shards.map((s) => (
            <div className="shard-line" key={s.shard}>
              {s.shard} · {s.host} · {s.percent}%
              <button className="yzu-chip small" onClick={() => restartShard(s.shard)}>Restart</button>
            </div>
          ))}
        </section>
      )}
      {shards && item.id !== "datacite" && (
        <section>
          <h3>Shards</h3>
          {shards.map((s) => (
            <div className="shard-line" key={s.shard}>{s.shard} · {s.host} · {s.percent}% {s.eta_hours ? `· ~${s.eta_hours}h` : ""}</div>
          ))}
        </section>
      )}
      <section className="yzu-agent">
        <h3>Collection assistant</h3>
        <p className="muted small">Review plan first. Collection jobs run in background after Launch.</p>
        <div className="yzu-chat">
          {messages.map((m, i) => (
            <article key={i} className={m.role}>
              <small>{m.role}{m.timing || ""}</small>
              <p>{m.text}</p>
              {m.advice?.recommended?.length > 0 && (
                <div className="yzu-advice-recs">
                  {(m.advice.recommended || []).slice(0, 4).map((rec) => (
                    <span key={rec.id} className="yzu-chip small" title={rec.reason}>{rec.id}</span>
                  ))}
                </div>
              )}
              {m.asyncNote && <small className="muted">{m.asyncNote}</small>}
            </article>
          ))}
        </div>
        {job && (
          <div className={`yzu-job ${job.status}`}>
            <strong>{job.title}</strong>
            <span>{job.status}</span>
            {job.status === "pending_approval" && <button className="primary" onClick={launch} disabled={busy}>Launch</button>}
          </div>
        )}
        <div className="yzu-composer">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder={`Ask how to source ${item.name}…`} rows={2} />
          <button className="primary" disabled={busy} onClick={() => ask()}>{busy ? "Thinking…" : "Ask"}</button>
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }) {
  return <div className="yzu-stat"><span>{label}</span><strong>{value}</strong></div>;
}

function Badge({ tone, children }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

createRoot(document.getElementById("root")).render(<App />);
