import { useEffect, useId, useRef, useState } from "react";
import { ProfileIcon } from "@/v2/nav-config.jsx";
import { isProfileBound } from "@/v2/profilePresentation";
import { accountDisplayName, accountInitials } from "@/v2/accountPresentation";

export { accountDisplayName, accountInitials };

function ChevronIcon({ open = false }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden className={open ? "is-open" : undefined}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function PreferencesIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function MenuItem({ testId, children, onClick, onKeyDown }) {
  return (
    <button
      type="button"
      role="menuitem"
      className="rd-v2-account-menu-item"
      data-testid={testId}
      onKeyDown={onKeyDown}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

/**
 * Shared account menu — desktop sidebar cluster + header/mobile avatar.
 * Two principal choices: Research context understanding, and compact workspace prefs.
 * Bind / clear / advanced live in the full preferences surface (?tab=settings or Manage context).
 */
export function AccountMenu({
  variant = "header",
  profile = null,
  headerInitials = "YZ",
  onOpenResearchContext,
  onOpenWorkspacePrefs,
}) {
  const bound = isProfileBound(profile);
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const listRef = useRef(null);

  const initials = accountInitials(profile, headerInitials);
  const label = accountDisplayName(profile);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (!rootRef.current?.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    queueMicrotask(() => listRef.current?.querySelector('[role="menuitem"]')?.focus());
  }, [open]);

  const focusRelative = (current, delta) => {
    const items = [...(listRef.current?.querySelectorAll('[role="menuitem"]') || [])];
    if (!items.length) return;
    const idx = items.indexOf(current);
    items[(idx + delta + items.length) % items.length]?.focus();
  };

  const onMenuKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      focusRelative(e.currentTarget, 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusRelative(e.currentTarget, -1);
    } else if (e.key === "Home") {
      e.preventDefault();
      listRef.current?.querySelector('[role="menuitem"]')?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      const items = listRef.current?.querySelectorAll('[role="menuitem"]');
      items?.[items.length - 1]?.focus();
    }
  };

  const openResearch = () => {
    const el = triggerRef.current;
    setOpen(false);
    onOpenResearchContext?.(el);
  };

  const openPrefs = () => {
    const el = triggerRef.current;
    setOpen(false);
    onOpenWorkspacePrefs?.({ mode: "workspace" }, el);
  };

  const panel = open ? (
    <div
      id={panelId}
      className={`rd-v2-account-menu-panel rd-v2-account-menu-panel--${variant}`}
      role="menu"
      aria-label="Account"
      data-testid="account-menu"
      ref={listRef}
    >
      <MenuItem testId="account-menu-profile" onClick={openResearch} onKeyDown={onMenuKeyDown}>
        <ProfileIcon />
        <span>Research context</span>
      </MenuItem>

      <MenuItem testId="account-menu-workspace" onClick={openPrefs} onKeyDown={onMenuKeyDown}>
        <PreferencesIcon />
        <span>Workspace preferences</span>
      </MenuItem>
    </div>
  ) : null;

  if (variant === "sidebar") {
    return (
      <div className="rd-v2-account-menu rd-v2-account-menu--sidebar" ref={rootRef} data-testid="sidebar-account-root">
        <button
          type="button"
          className={`rd-v2-account-cluster${open ? " is-open" : ""}${bound ? " is-bound" : ""}`}
          ref={triggerRef}
          aria-label={`Account menu · ${label}`}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          data-testid="sidebar-account-menu"
          title={label}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="rd-v2-account-avatar" aria-hidden>{initials}</span>
          <span className="rd-v2-account-meta">
            <span className="rd-v2-account-name">{label}</span>
            <span className="rd-v2-account-sub">{bound ? "Bound on this browser" : "Unbound"}</span>
          </span>
          <ChevronIcon open={open} />
        </button>
        {panel}
      </div>
    );
  }

  return (
    <div className="rd-v2-account-menu rd-v2-account-menu--header" ref={rootRef} data-testid="header-account-root">
      <button
        type="button"
        className="rd-header-avatar"
        ref={triggerRef}
        aria-label={`Account menu · ${label}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        data-testid="header-account-menu"
        title={label}
        onClick={() => setOpen((v) => !v)}
      >
        {initials}
      </button>
      {panel}
    </div>
  );
}

export function WorkspacePreferencesMenu(props) {
  return <AccountMenu variant="header" {...props} />;
}
