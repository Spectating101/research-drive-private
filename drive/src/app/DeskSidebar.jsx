import { LIBRARY_NAV, NAV_SECTIONS_LEGACY, PRIMARY_NAV } from "@/app/nav-config";

export function DeskSidebar({
  view,
  navOpen,
  adminOpen,
  onToggleAdmin,
  pendingJobs,
  runningCount,
  onNavigate,
  onOpenNew,
  navIcon,
  accountFooter,
  adminViews = [],
}) {
  const badgeFor = (item) => {
    if (item.badgeKind !== "jobs") return null;
    const n = pendingJobs > 0 ? pendingJobs : runningCount > 0 ? runningCount : null;
    return n;
  };

  return (
    <aside className={`yzu-sidebar${navOpen ? " nav-open" : ""}`}>
      <button type="button" className="rd-new-btn" onClick={onOpenNew}>
        + New
      </button>
      <nav>
        {PRIMARY_NAV.map((item) => {
          const badge = badgeFor(item);
          return (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? "active" : ""}
              onClick={() => onNavigate(item.id)}
            >
              {navIcon(item.icon)}
              <span className="rd-nav-label">{item.label}</span>
              {badge != null ? <small>{badge}</small> : null}
            </button>
          );
        })}
        <p className="rd-nav-title">Library</p>
        {LIBRARY_NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={view === item.id ? "active" : ""}
            onClick={() => onNavigate(item.id)}
          >
            {navIcon(item.icon)}
            <span className="rd-nav-label">{item.label}</span>
          </button>
        ))}
        <div className="rd-nav-legacy" aria-hidden="true">
          {NAV_SECTIONS_LEGACY.map((s) => (
            <p key={s.label} className="rd-nav-title">{s.label}</p>
          ))}
        </div>
        <button type="button" className={`rd-more-toggle ${adminOpen ? "active" : ""}`} onClick={onToggleAdmin}>
          Lab admin
        </button>
        {adminOpen
          ? adminViews.map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`rd-more-item ${view === id ? "active" : ""}`}
                onClick={() => onNavigate(id)}
              >
                {label}
                {id === "jobs" && pendingJobs > 0 ? <em>{pendingJobs}</em> : null}
              </button>
            ))
          : null}
      </nav>
      <footer>{accountFooter}</footer>
    </aside>
  );
}
