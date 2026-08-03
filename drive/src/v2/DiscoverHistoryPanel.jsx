import { useEffect, useMemo, useState } from "react";
import { Chip } from "@/v2/ui";
import { fenceHistoryEvents, systemVerificationClassification } from "@/v2/historyNoiseFence";
import { historyLifecycleBucket } from "@/v2/discoverAdapters";
import { historyLifecycleLabel } from "@/v2/historyLifecycleLabel";

const HISTORY_FILTERS = [
  { id: "all", label: "All" },
  { id: "needs_approval", label: "Needs you" },
  { id: "active", label: "Active" },
  { id: "ready", label: "Ready" },
  { id: "needs_recovery", label: "Recovery" },
  { id: "scheduled", label: "Scheduled" },
  { id: "search", label: "Search" },
  { id: "system", label: "System" },
];

function cleanTarget(value) {
  const valueText = String(value || "").replace(/\s+/g, " ").trim();
  if (!valueText.startsWith("[context:") || !valueText.includes("]")) return valueText;
  return valueText.split("]").slice(1).join("]").trim();
}

function eventTitle(event) {
  const title = cleanTarget(event?.target) || event?.title || "Discover request";
  // Some legacy collection records expose only a run hash as their target.
  // Keep the durable record reachable, but do not make an opaque identifier the
  // researcher-facing label.
  if (/^[a-f0-9]{10,}$/i.test(title)) return "Collection run";
  return title;
}

function opaqueRunReference(event) {
  const target = cleanTarget(event?.target);
  return /^[a-f0-9]{10,}$/i.test(target) ? target : "";
}

function eventKind(event) {
  const action = String(event?.action || "").toLowerCase();
  // Terra donor: Ask/search telemetry stays under Search, not the durable trail.
  if (/^(ask|semantic_discover|discover|search|probe|query|preview|bq_)/.test(action)) {
    return "search";
  }
  if (event?.meta?.ask_telemetry === true || event?.meta?.telemetry === true) {
    return "search";
  }
  const bucket = historyLifecycleBucket(event);
  if (bucket !== "all") return bucket;
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
  const summary = meta.summary || event?.summary;
  // Keep low-level collector diagnostics in Detail rather than making an
  // allow-list error read like the primary description of a research record.
  if (opaqueRunReference(event) && /script_key\s+not\s+allowlisted/i.test(String(summary || ""))) {
    return "Collector configuration blocked";
  }
  if (summary) return String(summary);
  if (meta.cadence) return `Cadence: ${meta.cadence}`;
  if (meta.candidate_key) return `Candidate: ${meta.candidate_key}`;
  return "Durable Discover record";
}

function eventSourceIdentity(event) {
  const meta = event?.meta || {};
  const source =
    meta.source ||
    meta.source_route ||
    meta.collect_via ||
    meta.provider ||
    event?.source ||
    "Source pending";
  const identity =
    meta.evidence_identity ||
    meta.identity ||
    meta.entity ||
    meta.scope ||
    eventSummary(event);
  const runReference = opaqueRunReference(event);
  // "Source pending" is an implementation fallback, not useful researcher
  // context. Preserve it in the record/rail but do not lead every ledger row
  // with the same empty phrase.
  return [source === "Source pending" ? "" : source, identity, runReference ? `Run ${runReference}` : ""]
    .filter(Boolean)
    .join(" · ");
}

function eventEvidenceLine(event) {
  const meta = event?.meta || {};
  const parts = [];
  if (meta.bytes_received || meta.received) parts.push(String(meta.bytes_received || meta.received));
  if (meta.archive_note) parts.push(String(meta.archive_note));
  if (meta.progress_note) parts.push(String(meta.progress_note));
  parts.push(eventTime(event));
  return parts.filter(Boolean).join(" · ");
}

function eventMethodCue(event) {
  const meta = event?.meta || {};
  const cue = meta.method_cue || meta.method || meta.route_method || event?.method_cue;
  if (!cue) return null;
  const kind = eventKind(event);
  if (!["active", "needs_approval", "needs_recovery"].includes(kind) && !meta.method_material) {
    return null;
  }
  return String(cue);
}

function systemVerificationCue(event) {
  const classification = systemVerificationClassification(event);
  if (!classification.matched) return null;
  if (classification.basis === "explicit_metadata") {
    return `System verification · ${classification.detail}`;
  }
  return `System verification · name pattern ${classification.detail}`;
}

function eventId(event, index = 0) {
  return event?.id || `${event?.ts || "event"}:${index}`;
}

function HistoryRow({ event, selectedId, index, onSelectEvent, secondary = false }) {
  const id = eventId(event, index);
  const title = eventTitle(event);
  const kind = eventKind(event);
  const selected = selectedId === id;
  const methodCue = eventMethodCue(event);
  const systemCue = secondary ? systemVerificationCue(event) : null;
  return (
    <button
      key={id}
      type="button"
      className={`rd-v2-history-row rd-v2-history-row-3line${selected ? " on" : ""}${secondary ? " is-system" : ""}`}
      aria-label={`${title} ${stateLabel(event)}`}
      aria-pressed={selected}
      onClick={() => onSelectEvent?.({ ...event, id })}
    >
      <span className={`rd-v2-history-node ${kind}`} aria-hidden />
      <span className="rd-v2-history-main">
        <span className="rd-v2-history-line1">
          {selected ? <span className="rd-v2-history-selected-mark" aria-hidden>▌</span> : null}
          <strong>{title}</strong>
        </span>
        <span className="rd-v2-history-line2">{eventSourceIdentity(event)}</span>
        <span className="rd-v2-history-line3">{eventEvidenceLine(event)}</span>
        {systemCue ? <span className="rd-v2-history-system-cue">{systemCue}</span> : null}
        {methodCue ? <span className="rd-v2-history-method-cue">Method · {methodCue}</span> : null}
      </span>
      <span className="rd-v2-history-state">
        <em>{stateLabel(event)}</em>
      </span>
    </button>
  );
}

function Territory({ title, events, selectedId, onSelectEvent, startIndex = 0, secondary = false }) {
  if (!events.length) return null;
  return (
    <section className={`rd-v2-history-territory${secondary ? " is-secondary" : ""}`} aria-label={title}>
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
            secondary={secondary}
          />
        ))}
      </div>
    </section>
  );
}

function SystemVerificationFold({ events, selectedId, onSelectEvent, startIndex = 0, open = false }) {
  if (!events.length) return null;
  return (
    <details
      className="rd-v2-history-system-fold"
      data-testid="history-system-verification"
      open={open || undefined}
    >
      <summary>
        <span>
          <strong>System checks</strong>
          <em>Host and integration checks kept outside research history</em>
        </span>
        <span className="rd-v2-history-system-count">{events.length}</span>
      </summary>
      <div className="rd-v2-history-list">
        {events.map((event, index) => (
          <HistoryRow
            key={eventId(event, startIndex + index)}
            event={event}
            selectedId={selectedId}
            index={startIndex + index}
            onSelectEvent={onSelectEvent}
            secondary
          />
        ))}
      </div>
    </details>
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
  // Default "All" = researcher lifecycle only. Ask/search and system verification stay secondary.
  const durable = fenced.visible;
  const searchRows = fenced.searchTelemetry || [];
  const systemRows = fenced.systemVerification || [];
  const normalized =
    filter === "search" ? searchRows : filter === "system" ? systemRows : durable;
  const filtered = useMemo(
    () =>
      filter === "all" || filter === "search" || filter === "system"
        ? normalized
        : normalized.filter((event) => eventKind(event) === filter),
    [filter, normalized],
  );
  const visible = filtered.slice(0, visibleCount);
  const needsYou = filter === "all" ? visible.filter((event) => eventKind(event) === "needs_approval") : [];
  const lifecycle =
    filter === "all" ? visible.filter((event) => eventKind(event) !== "needs_approval") : visible;
  const filterCounts = useMemo(() => {
    const counts = {
      all: durable.length,
      search: searchRows.length,
      system: systemRows.length,
    };
    for (const item of HISTORY_FILTERS) {
      if (item.id === "all" || item.id === "search" || item.id === "system") continue;
      counts[item.id] = durable.filter((event) => eventKind(event) === item.id).length;
    }
    return counts;
  }, [durable, searchRows, systemRows]);
  const visibleFilters = useMemo(
    () => HISTORY_FILTERS.filter((item) => item.id === "all" || (filterCounts[item.id] ?? 0) > 0),
    [filterCounts],
  );

  useEffect(() => {
    setVisibleCount(8);
  }, [filter]);

  useEffect(() => {
    if (!visible.length || !onSelectEvent) return;
    const hasVisibleSelection = visible.some((event, index) => eventId(event, index) === selectedId);
    if (hasVisibleSelection) return;
    // Prefer researcher trail selection; only fall through to system rows on System filter.
    if (filter === "all" && systemRows.some((event, index) => eventId(event, index) === selectedId)) {
      return;
    }
    onSelectEvent({ ...visible[0], id: eventId(visible[0], 0) });
  }, [visible, onSelectEvent, selectedId, filter, systemRows]);

  return (
    <section className="rd-v2-discover-history" data-testid="discover-history" aria-label="Research lifecycle">
      <div className="rd-v2-history-intro">
        <div>
          <span className="rd-v2-eyebrow">Research lifecycle</span>
          <h2>Research requests and outcomes</h2>
          <p>
            Approvals, collection, and registered assets. Search activity and host checks remain available without burying
            research work.
          </p>
          {fenced.hiddenNoise > 0 ||
          fenced.hiddenSearchTelemetry > 0 ||
          fenced.hiddenSystemVerification > 0 ? (
            <p className="rd-v2-history-noise-note muted small" data-testid="history-noise-fence">
              {fenced.hiddenNoise > 0
                ? `${fenced.hiddenNoise} fixture/ops noise row${fenced.hiddenNoise === 1 ? "" : "s"} hidden`
                : ""}
              {fenced.hiddenNoise > 0 && fenced.hiddenSearchTelemetry > 0 ? " · " : ""}
              {fenced.hiddenSearchTelemetry > 0
                ? `${fenced.hiddenSearchTelemetry} Ask/search row${fenced.hiddenSearchTelemetry === 1 ? "" : "s"} under Search`
                : ""}
              {(fenced.hiddenNoise > 0 || fenced.hiddenSearchTelemetry > 0) &&
              fenced.hiddenSystemVerification > 0
                ? " · "
                : ""}
              {fenced.hiddenSystemVerification > 0
                ? `${fenced.hiddenSystemVerification} system check${
                    fenced.hiddenSystemVerification === 1 ? "" : "s"
                  } kept separate`
                : ""}
              {fenced.collapsedDuplicates > 0
                ? ` · ${fenced.collapsedDuplicates} duplicate${fenced.collapsedDuplicates === 1 ? "" : "s"} collapsed`
                : ""}
            </p>
          ) : null}
        </div>
      </div>

      <div className="rd-v2-toolbar inline rd-v2-history-filters" aria-label="History filters">
        {visibleFilters.map((item) => (
          <Chip key={item.id} active={filter === item.id} onClick={() => setFilter(item.id)}>
            {item.label} <b>{filterCounts[item.id] ?? 0}</b>
          </Chip>
        ))}
      </div>

      {!visible.length && !(filter === "all" && systemRows.length) ? (
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
          <SystemVerificationFold
            events={systemRows}
            selectedId={selectedId}
            onSelectEvent={onSelectEvent}
            startIndex={visible.length}
          />
        </div>
      ) : filter === "system" ? (
        <div className="rd-v2-history-territories">
          <Territory
            title="System checks"
            events={lifecycle}
            selectedId={selectedId}
            onSelectEvent={onSelectEvent}
            secondary
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
          Load {Math.min(8, filtered.length - visible.length)} more
        </button>
      ) : null}
    </section>
  );
}
