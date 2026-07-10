import { useEffect, useRef } from "react";
import { V2_SIDEBAR_TABS } from "@/v2/nav-config.jsx";

export function V2Sidebar({ tab, onTabChange }) {
  const activeButtonRef = useRef(null);

  useEffect(() => {
    activeButtonRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [tab]);

  return (
    <aside className="yzu-sidebar">
      <nav>
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
    </aside>
  );
}
