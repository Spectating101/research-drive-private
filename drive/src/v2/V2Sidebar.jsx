import { useEffect, useRef } from "react";
import { V2_SIDEBAR_TABS } from "@/v2/nav-config.jsx";
import { AccountMenu } from "@/v2/AccountMenu";

/**
 * Desktop: primary workspace stack + bottom-anchored account cluster.
 * Mobile: horizontal workspace row only (account via header avatar).
 */
export function V2Sidebar({
  tab,
  onTabChange,
  profile = null,
  onOpenResearchContext,
  onOpenWorkspacePrefs,
}) {
  const activeButtonRef = useRef(null);

  useEffect(() => {
    activeButtonRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [tab]);

  return (
    <aside className="yzu-sidebar" data-testid="v2-sidebar">
      <nav aria-label="Workspace">
        {V2_SIDEBAR_TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            ref={tab === id ? activeButtonRef : null}
            className={tab === id ? "active" : ""}
            onClick={() => onTabChange(id)}
            title={label}
          >
            {Icon ? <Icon /> : null}
            <span className="rd-nav-label">{label}</span>
          </button>
        ))}
      </nav>
      <div className="rd-v2-sidebar-account" data-testid="sidebar-account-cluster">
        <AccountMenu
          variant="sidebar"
          profile={profile}
          onOpenResearchContext={onOpenResearchContext}
          onOpenWorkspacePrefs={onOpenWorkspacePrefs}
        />
      </div>
    </aside>
  );
}
