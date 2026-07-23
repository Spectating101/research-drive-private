import { useEffect, useRef } from "react";
import { V2_SIDEBAR_FOOT_TABS, V2_SIDEBAR_PRIMARY_TABS } from "@/v2/nav-config.jsx";

/**
 * Left nav — UI_PRODUCT_AUTHORITY + page freezes shell:
 * RESEARCH DRIVE nav · ACTIVE RESEARCH · RECENT · Profile/Settings (foot)
 */
export function V2Sidebar({
  tab,
  onTabChange,
  activeResearch = null,
  recentItems = [],
  onOpenRecent,
}) {
  const activeButtonRef = useRef(null);
  const research = activeResearch || {
    title: "Active research",
    emphases: [],
  };
  const recent = Array.isArray(recentItems) ? recentItems.slice(0, 4) : [];

  useEffect(() => {
    activeButtonRef.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [tab]);

  function renderNavButton({ id, label, Icon }) {
    return (
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
    );
  }

  return (
    <aside className="yzu-sidebar rd-v2-sidebar-wire" aria-label="Research Drive navigation">
      <nav className="rd-v2-sidebar-nav" aria-label="Faculty destinations">
        {V2_SIDEBAR_PRIMARY_TABS.map(renderNavButton)}
      </nav>

      <div className="rd-v2-sidebar-context" aria-label="Active research">
        <p className="rd-v2-sidebar-kicker">Active research</p>
        <strong className="rd-v2-sidebar-research-title">{research.title}</strong>
        {research.emphases?.length ? (
          <ul className="rd-v2-sidebar-emphases">
            {research.emphases.slice(0, 3).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="rd-v2-sidebar-hint">Profile sets research direction.</p>
        )}
      </div>

      <div className="rd-v2-sidebar-recent" aria-label="Recent">
        <p className="rd-v2-sidebar-kicker">Recent</p>
        {recent.length ? (
          <ul>
            {recent.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => onOpenRecent?.(item)}>
                  {item.title}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rd-v2-sidebar-hint">Recent assets appear as you work.</p>
        )}
      </div>

      <nav className="rd-v2-sidebar-foot-nav" aria-label="Account">
        {V2_SIDEBAR_FOOT_TABS.map(renderNavButton)}
      </nav>
    </aside>
  );
}
