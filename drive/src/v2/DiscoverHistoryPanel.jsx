import { useEffect, useMemo, useState } from "react";
import { Chip } from "@/v2/ui";

const HISTORY_FILTERS = [
  { id: "all", label: "All" },
  { id: "search", label: "Search" },
  { id: "probe", label: "Probe" },
  { id: "query", label: "Query" },
  { id: "procure", label: "Procure" },
  { id: "registered", label: "Registered" },
];

const ACTION_LABELS = {
  ask: "Research request",
  discover: "Searched",
  search: "Searched",
  probe: "Probed",
  query: "Queried",
  preview: "Previewed",
  procure: "Procurement submitted",
  job_submit: "Collection submitted",
  job_approve: "Collection approved",
  approve_collect: "Collection approved",
  archive: "Archived",
  register: "Registered",
  registry_promote: "Registered",
  synthesis: "Synthesis built",
};

function cleanTarget(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text.startsWith("[context:") || !text.includes("]")) return text;
  return text.split("]").slice(1).join("]").trim();
}

function eventKind(event) {
  const action = String(event?.action || "").toLowerCase();
  if (/discover|search/.test(action)) return "search";
  if (/probe/.test(action)) return "probe";
  if (/query|preview|bq_/.test(action)) return "query";
  if (/register|promote/.test(action)) return "registered";
  if (/procure|job_|approve|archive|collect/.test(action)) return "procure";
  return action || "other";
}

function eventLabel(event) {
  return ACTION_LABELS[event?.action] || String(event?.action || "Activity").replace(/_/g, " ");
}

function eventTime(event) {
  if (!event?.ts) return "Time unavailable";
  const date = new Date(event.ts);
  if (Number.isNaN(date.getTime())) return String(event.ts);
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function eventDay(event) {
  if (!event?.ts) return { key: "undated", label: "Earlier" };
  const date = new Date(event.ts);
  if (Number.isNaN(date.getTime())) return { key: "undated", label: "Earlier" };
  const key = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return { key, label: "Today" };
  if (date.toDateString() === yesterday.toDateString()) return { key, label: "Yesterday" };
  return {
    key,
    label: date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }),
  };
}

function eventOutcome(event) {
  const meta = event?.meta || {};
  if (meta.repeat_count > 1) {
    const latest = meta.total != null ? ` · ${meta.total} latest results` : "";
    return `${meta.repeat_count} repeated searches${latest}`;
  }
  if (meta.dataset_id) return `Dataset · ${meta.dataset_id}`;
  if (meta.job_id) return `Job · ${meta.job_id}`;
  if (meta.total != null) return `${meta.total} result${meta.total === 1 ? "" : "s"}`;
  if (meta.status) return String(meta.status).replace(/_/g, " ");
  return eventKind(event) === "search" ? "Research discovery" : "Recorded by the desk";
}

function eventId(event, index = 0) {
  return event?.id || `${event?.ts || "event"}:${index}`;
}

function compactRepeatedSearches(events) {
  const compacted = [];
  for (const event of events) {
    const previous = compacted[compacted.length - 1];
    const currentTime = new Date(event?.ts || 0).getTime();
    const previousTime = new Date(previous?.ts || 0).getTime();
    const sameSearch =
      previous &&
      eventKind(event) === "search" &&
      eventKind(previous) === "search" &&
      cleanTarget(event.target).toLowerCase() === cleanTarget(previous.target).toLowerCase() &&
      Number.isFinite(currentTime) &&
      Number.isFinite(previousTime) &&
      Math.abs(previousTime - currentTime) <= 15 * 60 * 1000;
    if (!sameSearch) {
      compacted.push(event);
      continue;
    }
    const repeatCount = Number(previous.meta?.repeat_count || 1) + 1;
    compacted[compacted.length - 1] = {
      ...previous,
      meta: { ...previous.meta, repeat_count: repeatCount },
    };
  }
  return compacted;
}

function groupEvents(events) {
  const groups = [];
  const index = new Map();
  for (const event of events) {
    const day = eventDay(event);
    let group = index.get(day.key);
    if (!group) {
      group = { ...day, events: [] };
      index.set(day.key, group);
      groups.push(group);
    }
    group.events.push(event);
  }
  return groups;
}

export function DiscoverHistoryPanel({
  events = [],
  selectedId = "",
  onSelectEvent,
}) {
  const [filter, setFilter] = useState("all");
  const normalized = useMemo(
    () => compactRepeatedSearches(
      [...events]
        .filter((event) => event && (event.id || event.ts || event.target))
        .sort((a, b) => String(b.ts || "").localeCompare(String(a.ts || ""))),
    ),
    [events],
  );
  const filtered = useMemo(
    () => (filter === "all" ? normalized : normalized.filter((event) => eventKind(event) === filter)),
    [filter, normalized],
  );
  const groups = useMemo(() => groupEvents(filtered), [filtered]);

  useEffect(() => {
    if (!filtered.length || !onSelectEvent) return;
    const hasVisibleSelection = filtered.some((event, index) => eventId(event, index) === selectedId);
    if (!hasVisibleSelection) onSelectEvent({ ...filtered[0], id: eventId(filtered[0], 0) });
  }, [filtered, onSelectEvent, selectedId]);

  return (
    <section className="rd-v2-discover-history" data-testid="discover-history" aria-label="Research trail">
      <div className="rd-v2-history-intro">
        <div>
          <span className="rd-v2-eyebrow">Research trail</span>
          <h2>From question to registered evidence</h2>
          <p>Searches, probes, queries and procurement outcomes remain linked so the lab can reuse prior work.</p>
        </div>
        <strong>{normalized.length} recorded event{normalized.length === 1 ? "" : "s"}</strong>
      </div>

      <div className="rd-v2-toolbar inline rd-v2-history-filters" aria-label="History filters">
        {HISTORY_FILTERS.map((item) => (
          <Chip key={item.id} active={filter === item.id} onClick={() => setFilter(item.id)}>
            {item.label}
          </Chip>
        ))}
      </div>

      {!groups.length ? (
        <div className="rd-v2-discover-miss">
          <p className="rd-v2-empty-inline">
            No history matches this filter. Search, preview, probe or collect a source to create a reusable trail.
          </p>
        </div>
      ) : (
        <div className="rd-v2-history-groups">
          {groups.map((group) => (
            <section key={group.key} className="rd-v2-history-day" aria-label={group.label}>
              <div className="rd-v2-history-day-head">
                <h3>{group.label}</h3>
                <span>{group.events.length} event{group.events.length === 1 ? "" : "s"}</span>
              </div>
              <div className="rd-v2-history-list">
                {group.events.map((event, index) => {
                  const id = eventId(event, index);
                  const title = cleanTarget(event.target) || eventLabel(event);
                  return (
                    <button
                      key={id}
                      type="button"
                      className={`rd-v2-history-row${selectedId === id ? " on" : ""}`}
                      aria-label={`${eventLabel(event)} ${title}`}
                      aria-pressed={selectedId === id}
                      onClick={() => onSelectEvent?.({ ...event, id })}
                    >
                      <span className={`rd-v2-history-node ${eventKind(event)}`} aria-hidden />
                      <time>{eventTime(event)}</time>
                      <span className="rd-v2-history-main">
                        <strong>{eventLabel(event)}</strong>
                        <span>{title}</span>
                      </span>
                      <em>{eventOutcome(event)}</em>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
