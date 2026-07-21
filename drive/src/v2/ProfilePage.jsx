import { useEffect, useState } from "react";
import {
  buildDeskRead,
  buildLab,
  buildMemoryCards,
  buildWorks,
} from "@/v2/profileViewModel";
import {
  buildProfileRailState,
  buildUnboundProfileCentre,
  isProfileBound,
  profileCentreMode,
  profilePrimaryCommand,
  profileSectionsVisible,
} from "@/v2/profilePresentation";
import { PageShell } from "@/v2/ui";
import {
  RailEntityHeader,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";

const MEMORY_LABELS = {
  focus: "Focus",
  current: "Current",
  also: "Also",
  methods: "Methods",
};

function MemoryEditIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 20h9"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <path
        d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Profile — Memory · Works · Lab when bound.
 * Unbound: one compact zero state + Settings CTA; no empty section shells; no pilot identity.
 */
export function ProfilePage({
  profile,
  selectedWorkId = null,
  onSelectWork,
  onGoTab,
  onSuggestSearch,
}) {
  const bound = isProfileBound(profile);
  const showSections = profileSectionsVisible(profile);
  const mode = profileCentreMode(profile);
  const primary = profilePrimaryCommand(mode);
  const unbound = bound ? null : buildUnboundProfileCentre();
  const name = bound
    ? profile?.name_en || profile?.name || "Research profile"
    : unbound.title;
  const orgLine = bound
    ? [profile?.title, profile?.discipline].filter(Boolean).join(" · ")
    : unbound.lead;
  const email = bound ? profile?.email || "" : "";
  const memory = showSections ? buildMemoryCards(profile) : [];
  const works = showSections ? buildWorks(profile) : { paperCount: null, items: [] };
  const lab = showSections ? buildLab(profile) : { linked: [], suggested: [] };
  const [memoryDraft, setMemoryDraft] = useState([]);
  const [editingMemoryId, setEditingMemoryId] = useState(null);
  const [editBuffer, setEditBuffer] = useState("");
  const memoryKey = showSections
    ? `${profile?.email || ""}:${memory.map((c) => c.id).join(",")}:${memory.map((c) => c.text).join("|")}`
    : "unbound";

  useEffect(() => {
    setMemoryDraft(memory.map((card) => ({ ...card })));
    setEditingMemoryId(null);
    setEditBuffer("");
    // Reset drafts when the bound profile memory payload changes, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memoryKey]);

  const startEdit = (card) => {
    setEditingMemoryId(card.id);
    setEditBuffer(card.text || "");
  };

  const cancelEdit = () => {
    setEditingMemoryId(null);
    setEditBuffer("");
  };

  const saveEdit = () => {
    if (!editingMemoryId) return;
    const next = String(editBuffer || "").trim();
    setMemoryDraft((rows) =>
      rows.map((row) => (row.id === editingMemoryId ? { ...row, text: next } : row)),
    );
    setEditingMemoryId(null);
    setEditBuffer("");
  };

  const runQuery = (q) => {
    const query = String(q || "").trim();
    if (query && onSuggestSearch) {
      onSuggestSearch(query);
      return;
    }
    onGoTab?.("browse");
  };

  return (
    <PageShell
      className={`rd-v2-profile-page${bound ? "" : " is-unbound"}`}
      title="Profile"
      lead={bound ? "Saved research context for Discover and Ask" : "Researcher context for this browser"}
    >
      <section
        className={`rd-v2-profile-identity${bound ? "" : " is-zero"}`}
        aria-label="Faculty identity"
        data-testid={bound ? "profile-bound-identity" : "profile-unbound-zero"}
      >
        <div className="rd-v2-profile-ident">
          {!bound ? (
            <span className="rd-v2-profile-badge quiet" data-testid="profile-unbound-badge">
              {unbound.badge}
            </span>
          ) : null}
          <h2 className="rd-v2-profile-name">{name}</h2>
          {orgLine ? <p className="rd-v2-profile-org">{orgLine}</p> : null}
          <p className="rd-v2-profile-hint">
            {bound ? email || "—" : unbound.hint}
          </p>
        </div>
        <div className="rd-v2-profile-identity-actions">
          {primary ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              data-testid="profile-primary-command"
              onClick={() => onGoTab?.(primary.tab || "settings")}
            >
              {primary.label}
            </button>
          ) : null}
        </div>
      </section>

      {!showSections ? null : (
      <>
      <section
        className="rd-v2-profile-section rd-v2-profile-memory-section"
        data-testid="profile-memory"
        data-section="memory"
        aria-labelledby="profile-memory-title"
      >
        <header className="rd-v2-profile-section-head">
          <h2 id="profile-memory-title">Memory</h2>
          <span>{memoryDraft.length ? `${memoryDraft.length} saved` : "None yet"}</span>
        </header>
        {memoryDraft.length ? (
          <ul className="rd-v2-profile-memory">
            {memoryDraft.map((card) => {
              const label = MEMORY_LABELS[card.id] || card.id;
              const active = editingMemoryId === card.id;
              return (
                <li
                  key={card.id}
                  className={`rd-v2-profile-memory-row${active ? " is-editing" : ""}`}
                  data-memory={card.id}
                >
                  {active ? (
                    <div className="rd-v2-profile-memory-edit">
                      <label
                        className="rd-v2-profile-memory-label"
                        htmlFor={`profile-memory-${card.id}`}
                      >
                        {label}
                      </label>
                      <textarea
                        id={`profile-memory-${card.id}`}
                        className="rd-v2-profile-memory-input"
                        rows={3}
                        value={editBuffer}
                        onChange={(e) => setEditBuffer(e.target.value)}
                        data-testid={`profile-memory-${card.id}`}
                        // eslint-disable-next-line jsx-a11y/no-autofocus
                        autoFocus
                      />
                      <div className="rd-v2-profile-memory-edit-actions">
                        <button
                          type="button"
                          className="rd-v2-btn sm primary"
                          data-testid={`profile-memory-save-${card.id}`}
                          onClick={saveEdit}
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          className="rd-v2-btn sm"
                          data-testid={`profile-memory-cancel-${card.id}`}
                          onClick={cancelEdit}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="rd-v2-profile-memory-line">
                      <span className="rd-v2-profile-memory-label">{label}</span>
                      <span
                        className="rd-v2-profile-memory-value"
                        data-testid={`profile-memory-${card.id}`}
                        title={card.text || undefined}
                      >
                        {card.text || "—"}
                      </span>
                      <button
                        type="button"
                        className="rd-v2-profile-memory-edit-btn"
                        aria-label={`Edit ${label}`}
                        data-testid={`profile-memory-edit-${card.id}`}
                        onClick={() => startEdit(card)}
                      >
                        <MemoryEditIcon />
                        <span>Edit</span>
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="rd-v2-empty-inline" data-testid="profile-memory-empty">
            No specialties, tracks, or methods on file.
          </p>
        )}
      </section>

      <section
        className="rd-v2-profile-section rd-v2-profile-works-section"
        data-testid="profile-works"
        data-section="works"
        aria-labelledby="profile-works-title"
      >
        <header className="rd-v2-profile-section-head">
          <h2 id="profile-works-title">Works</h2>
          {works.paperCount ? <span>{works.paperCount} indexed</span> : null}
        </header>
        {works.items.length ? (
          <ul className="rd-v2-profile-works" role="listbox" aria-label="Publication works">
            {works.items.map((work, index) => {
              const selected = Boolean(selectedWorkId) && selectedWorkId === work.raw;
              return (
                <li key={work.raw}>
                  <button
                    type="button"
                    className={`rd-v2-profile-work-row${selected ? " is-selected" : ""}`}
                    aria-selected={selected}
                    data-testid="profile-work-row"
                    onClick={() => onSelectWork?.(selected ? null : work)}
                  >
                    <span className="rd-v2-profile-work-index">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="rd-v2-profile-work-body">
                      <span className="rd-v2-profile-work-title">{work.title}</span>
                      <span className="rd-v2-profile-work-meta">
                        {work.type}
                        {work.relationship ? ` · ${work.relationship}` : ""}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="rd-v2-empty-inline" data-testid="profile-works-empty">
            {works.paperCount
              ? "Indexed count on file; highlights not listed."
              : "No works on file."}
          </p>
        )}
      </section>

      <section
        className="rd-v2-profile-section rd-v2-profile-lab-section"
        data-testid="profile-lab"
        data-section="lab"
        aria-labelledby="profile-lab-title"
      >
        <header className="rd-v2-profile-section-head">
          <h2 id="profile-lab-title">Lab</h2>
          <span>Linked · gaps</span>
        </header>

        <div className="rd-v2-profile-lab-block">
          <h3 className="rd-v2-profile-lab-label">Linked evidence</h3>
          {lab.linked.length ? (
            <ul className="rd-v2-profile-lab-rows">
              {lab.linked.map((row) => (
                <li key={row.id}>
                  <span className="rd-v2-profile-lab-title" title={row.label}>
                    {row.label}
                  </span>
                  <button
                    type="button"
                    className="rd-v2-profile-lab-action"
                    onClick={() => runQuery(row.label)}
                  >
                    {row.routeLabel} · Open →
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rd-v2-empty-inline" data-testid="profile-lab-linked-empty">
              None linked yet
            </p>
          )}
        </div>

        <div className="rd-v2-profile-lab-block">
          <h3 className="rd-v2-profile-lab-label">Evidence gaps</h3>
          {lab.suggested.length ? (
            <ul className="rd-v2-profile-lab-rows">
              {lab.suggested.map((row) => (
                <li key={row.id}>
                  <span className="rd-v2-profile-lab-title" title={row.label}>
                    {row.label}
                    <em> — {row.reason}</em>
                  </span>
                  <button
                    type="button"
                    className="rd-v2-profile-lab-action"
                    onClick={() => runQuery(row.query)}
                  >
                    {row.action === "link" ? "Link →" : "Search →"}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rd-v2-empty-inline" data-testid="profile-lab-gaps-empty">
              No open gaps
            </p>
          )}
        </div>
      </section>
      </>
      )}
    </PageShell>
  );
}

/**
 * DETAIL rail — selected work or research context.
 * Never shows Loading once Profile centre has rendered (including unbound).
 */
export function ProfileDetailPanel({
  profile,
  selectedWork = null,
  onGoTab,
  onClearWork,
  onAskAbout,
}) {
  // Centre always renders; treat null/undefined as unbound pending — not Loading.
  const rail = buildProfileRailState({
    profile: profile ?? { unknown: true },
    selectedWork,
    profileResolved: true,
  });
  const bound = isProfileBound(profile);
  const read = bound && !selectedWork ? buildDeskRead(profile, { previewing: false }) : null;

  return (
    <RailFrame>
      <RailEntityHeader
        id="profile"
        title={rail.identity[0] || "Profile"}
        description={rail.identity.slice(1).filter(Boolean).join(" · ") || null}
      />
      <div className="rd-v2-rail-scroll" data-testid="profile-detail-rail">
        <section className="rd-v2-rail-value-brief" aria-label="Judgement">
          <p className="rd-v2-rail-section-label">Judgement</p>
          <p>{rail.judgement}</p>
        </section>
        {rail.facts.length ? (
          <ul className="rd-v2-profile-rail-facts">
            {rail.facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        ) : null}
        {rail.unknowns.length ? (
          <section className="rd-v2-profile-rail-block">
            <h3>Unknowns</h3>
            <ul>
              {rail.unknowns.map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          </section>
        ) : null}
        {read?.strengths?.length ? (
          <section className="rd-v2-profile-rail-block">
            <h3>Strengths</h3>
            <ul>
              {read.strengths.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </section>
        ) : null}
        {read?.desk ? (
          <section className="rd-v2-profile-rail-block">
            <h3>Desk</h3>
            <p>{read.desk}</p>
          </section>
        ) : null}
      </div>
      <RailStickyFooter>
        {rail.primaryAction?.id === "ask-work" ? (
          <button
            type="button"
            className="rd-v2-btn sm primary"
            data-testid="profile-ask-about-work"
            onClick={() => onAskAbout?.(selectedWork)}
          >
            {rail.primaryAction.label}
          </button>
        ) : rail.primaryAction?.id === "clear-work" ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onClearWork?.()}>
            {rail.primaryAction.label}
          </button>
        ) : rail.primaryAction?.tab ? (
          <button
            type="button"
            className="rd-v2-btn sm primary"
            onClick={() => onGoTab?.(rail.primaryAction.tab)}
          >
            {rail.primaryAction.label}
          </button>
        ) : null}
      </RailStickyFooter>
    </RailFrame>
  );
}
