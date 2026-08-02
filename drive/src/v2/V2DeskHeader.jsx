import { useEffect, useRef, useState } from "react";
import { deskStatusBadge, visibleIntegrationChips } from "@/v2/deskStatusBadge";

/** v2 header — brand · research context · resting status (no global search/Ask pill) */

function freshnessLabel(refreshedAt) {
  if (refreshedAt == null) return null;
  const sec = Math.max(0, Math.round((Date.now() - refreshedAt) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  return `${min}m ago`;
}

const PAGE_LABELS = {
  home: "HOME",
  library: "LIBRARY",
  browse: "DISCOVER",
  synthesis: "SYNTHESIS",
  resources: "RESOURCES",
  profile: "PROFILE",
  settings: "SETTINGS",
};

export function V2DeskHeader({
  onBrandClick,
  onRetry,
  headerInitials = "YZ",
  datasetCount = 0,
  usingSeed = false,
  workCount = 0,
  onPendingClick,
  deskStatus = "unknown",
  refreshedAt = null,
  dryRunProtected: _dryRunProtected = true,
  integrationChips = [],
  activeResearchTitle = "Active research",
  currentPage = "home",
  onAccountNavigate,
  principal = null,
}) {
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef(null);
  const metaText = usingSeed
    ? `${datasetCount} datasets`
    : workCount > 0
      ? `${datasetCount} datasets · ${workCount} pending`
      : `${datasetCount} datasets`;
  const fresh = freshnessLabel(refreshedAt);
  const chips = Array.isArray(integrationChips) ? integrationChips : [];

  const statusBadge = deskStatusBadge(deskStatus, usingSeed);
  const pageLabel = PAGE_LABELS[currentPage] || String(currentPage || "").toUpperCase();

  useEffect(() => {
    if (!accountOpen) return undefined;
    const closeOutside = (event) => {
      if (!accountRef.current?.contains(event.target)) setAccountOpen(false);
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setAccountOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [accountOpen]);

  const openAccountPage = (page) => {
    setAccountOpen(false);
    onAccountNavigate?.(page);
  };

  return (
    <header className="yzu-header rd-v2-header rd-v2-header-wire">
      <button type="button" className="yzu-brand" onClick={onBrandClick}>
        <span className="rd-brand-mark">RD</span>
        <div className="yzu-brand-text">
          <strong>Research Drive</strong>
        </div>
      </button>

      <div className="rd-v2-header-context" aria-label="Active research context">
        <button type="button" className="rd-v2-header-research" title={activeResearchTitle}>
          <span>{activeResearchTitle}</span>
          <em aria-hidden>▾</em>
        </button>
        <span className="rd-v2-header-page" data-testid="header-page-label">
          {pageLabel}
        </span>
      </div>

      <div className="rd-v2-header-meta">
        <div className="rd-v2-trust-strip" aria-label="Desk status" data-testid="desk-integration-strip">
          <span className={`rd-v2-trust-badge ${statusBadge.tone}`}>{statusBadge.label}</span>
          {visibleIntegrationChips(chips, statusBadge.label)
            .map((chip) => (
              <span
                key={chip.id}
                className={`rd-v2-trust-badge ${chip.tone || "muted"}`}
                title={chip.label}
              >
                {chip.label}
              </span>
            ))}
          {fresh && deskStatus !== "ok" ? (
            <span className="rd-v2-trust-badge muted">Updated {fresh}</span>
          ) : null}
        </div>
        <span className="rd-v2-header-meta-count" title={metaText}>
          {workCount > 0 && onPendingClick ? (
            <>
              {`${datasetCount} datasets · `}
              <button
                type="button"
                className="rd-v2-header-pending-link"
                data-testid="header-pending-link"
                onClick={onPendingClick}
              >
                {workCount} pending
              </button>
            </>
          ) : (
            metaText
          )}
        </span>
        {usingSeed && onRetry ? (
          <button type="button" className="rd-v2-header-retry" onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </div>
      <div className="rd-v2-account-menu-wrap" ref={accountRef}>
        <button
          type="button"
          className="rd-header-avatar"
          aria-label="Account"
          aria-haspopup="menu"
          aria-expanded={accountOpen}
          onClick={() => setAccountOpen((open) => !open)}
        >
          {headerInitials}
        </button>
        {accountOpen ? (
          <div className="rd-v2-account-menu" role="menu" aria-label="Account destinations">
            {principal ? (
              <div className="rd-v2-account-identity">
                <strong>{principal.display_name || principal.email || "Research Drive user"}</strong>
                <span>
                  {principal.default_workspace_id || "personal"} · {principal.role || "viewer"}
                </span>
              </div>
            ) : null}
            <button type="button" role="menuitem" onClick={() => openAccountPage("profile")}>
              <span>Profile</span>
              <small>Research memory</small>
            </button>
            <button type="button" role="menuitem" onClick={() => openAccountPage("settings")}>
              <span>Settings</span>
              <small>Desk preferences</small>
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
