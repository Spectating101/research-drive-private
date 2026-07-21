import { useEffect, useMemo, useState } from "react";
import { Chip } from "@/v2/ui";
import { fenceHistoryEvents } from "@/v2/historyNoiseFence";
import { historyLifecycleBucket } from "@/v2/discoverAdapters";
import { historyLifecycleLabel } from "@/v2/historyLifecycleLabel";

const HISTORY_FILTERS = [
  { id: "all", label: "All" },
  { id: "needs_approval", label: "Needs you" },
  { id: "active", label: "Active" },
  { id: "ready", label: "Ready" },
  { id: "needs_recovery", label: "Recovery" },
  { id: "scheduled", label: "Scheduled" },
];

function cleanTarget(value) {
  const valueText = String(value || "").replace(/\s+/g, " ").trim();
  if (!valueText.startsWith("[context:") || !valueText.includes("]")) return valueText;
  return valueText.split("]").slice(1).join("]").trim();
}

function eventKind(event) {
  const bucket = historyLifecycleBucket(event);
  if (bucket !== "all") return bucket;
  const action = String(event?.action || "").toLowerCase();
  if (action === "intent") return "needs_approval";
  if (action === "collection_run") return "active";
  return "other";
}

function stateLabel(event) {
  return historyLifecycleLabel(event);
}

function eventTime(event) {
  if (!event?.ts) return "Time unavailable";
  const date = new Date(event.ts);
  if (Number.isNaN(date.getTime())) return String(event.ts);
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function eventSummary(event) {
  const meta = event?.meta || {};
  if (meta.summary) return String(meta.summary);
  if (event?.summary) return String(event.summary);
  if (meta.cadence) return `Cadence: ${meta.cadence}`;
  if (meta.candidate_key) return `Candidate: ${meta.candidate_key}`;
  return "Durable Discover record";
}

function eventId(event, index = 0) {
  return event?.id || `${event?.ts || "event"}:${index}`;
}

function HistoryRow({ event, selectedId, index, onSelectEvent }) {
  const id = eventId(event, index);
  const title = cleanTarget(event.target) || event.title || "Discover request";
  const kind = eventKind(event);
  return (
    <button
      key={id}
      type="button"
      className={`rd-v2-history-row${selectedId === id ? " on" : ""}`}
      aria-label={`${title} ${stateLabel(event)}`}
      aria-pressed={selectedId === id}
      onClick={() => onSelectEvent?.({ ...event, id })}
    >
      <span className={`rd-v2-history-node ${kind}`} aria-hidden />
      <span className="rd-v2-history-main">
        <strong>{title}</strong>
        <span>{eventSummary(event)}</span>
      </span>
      <span className="rd-v2-history-state">
        <em>{stateLabel(event)}</em>
        <time>{eventTime(event)}</time>
      </span>
    </button>
  );
}

function Territory({ title, events, selectedId, onSelectEvent, startIndex = 0 }) {
  if (!events.length) return null;
  return (
    <section className="rd-v2-history-territory" aria-label={title}>
      <header className="rd-v2-history-territory-head">
        <h3>{title}</h3>
        <span>{events.length}</span>
      </header>
      <div className="rd-v2-history-list">
        {events.map((event, index) => (
          <HistoryRow
            key={eventId(event, index)}
            event={event}
            selectedId={selectedId}
            index={startIndex + index}
            onSelectEvent={onSelectEvent}
          />
        ))}
      </div>
    </section>
  );
}

export function DiscoverHistoryPanel({ events = [], selectedId = "", onSelectEvent }) {
  const [filter, setFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(8);
  const fenced = useMemo(() => {
    const raw = [...events]
      .filter((event) => event && (event.id || event.ts || event.target))
      .sort((a, b) => String(b.ts || "").localeCompare(String(a.ts || "")));
    return fenceHistoryEvents(raw);
  }, [events]);
  const normalized = fenced.visible;
  const filtered = useMemo(
    () => (filter === "all" ? normalized : normalized.filter((event) => eventKind(event) === filter)),
    [filter, normalized],
  );
  const visible = filtered.slice(0, visibleCount);
  const needsYou = filter === "all" ? visible.filter((event) => eventKind(event) === "needs_approval") : [];
  const lifecycle = filter === "all" ? visible.filter((event) => eventKind(event) !== "needs_approval") : visible;

  useEffect(() => {
    setVisibleCount(8);
  }, [filter]);

  useEffect(() => {
    if (!visible.length || !onSelectEvent) return;
    const hasVisibleSelection = visible.some((event, index) => eventId(event, index) === selectedId);
    if (!hasVisibleSelection) onSelectEvent({ ...visible[0], id: eventId(visible[0], 0) });
  }, [visible, onSelectEvent, selectedId]);

  return (
    <section className="rd-v2-discover-history" data-testid="discover-history" aria-label="Research lifecycle">
      <div className="rd-v2-history-intro">
        <div>
          <span className="rd-v2-eyebrow">Research lifecycle</span>
          <h2>Durable evidence requests and results</h2>
          <p>Researcher decisions come first. Collection, recovery, schedules, and reusable results remain linked.</p>
          {fenced.hiddenNoise > 0 ? (
            <p className="rd-v2-history-noise-note muted small" data-testid="history-noise-fence">
              {fenced.hiddenNoise} fixture/ops noise row{fenced.hiddenNoise === 1 ? "" : "s"} hidden
              {fenced.collapsedDuplicates > 0
                ? ` · ${fenced.collapsedDuplicates} duplicate${fenced.collapsedDuplicates === 1 ? "" : "s"} collapsed`
                : ""}
            </p>
          ) : null}
        </div>
        <strong>{normalized.length} item{normalized.length === 1 ? "" : "s"}</strong>
      </div>

      <div className="rd-v2-toolbar inline rd-v2-history-filters" aria-label="History filters">
        {HISTORY_FILTERS.map((item) => (
          <Chip key={item.id} active={filter === item.id} onClick={() => setFilter(item.id)}>
            {item.label}
          </Chip>
        ))}
      </div>

      {!visible.length ? (
        <div className="rd-v2-discover-miss">
          <p className="rd-v2-empty-inline">
            No durable Discover items match this filter. Requests, collections, schedules, and registered outputs appear here.
          </p>
        </div>
      ) : filter === "all" ? (
        <div className="rd-v2-history-territories">
          <Territory title="Needs you" events={needsYou} selectedId={selectedId} onSelectEvent={onSelectEvent} />
          <Territory
            title="Research lifecycle"
            events={lifecycle}
            selectedId={selectedId}
            onSelectEvent={onSelectEvent}
            startIndex={needsYou.length}
          />
        </div>
      ) : (
        <div className="rd-v2-history-territories">
          <Territory
            title={HISTORY_FILTERS.find((item) => item.id === filter)?.label || "Research lifecycle"}
            events={lifecycle}
            selectedId={selectedId}
            onSelectEvent={onSelectEvent}
          />
        </div>
      )}

      {filtered.length > visible.length ? (
        <button type="button" className="rd-v2-history-load-more" onClick={() => setVisibleCount((count) => count + 8)}>
          Load more
        </button>
      ) : null}
    </section>
  );
}
