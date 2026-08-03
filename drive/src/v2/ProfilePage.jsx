import {
  buildLab,
  buildMemoryBrief,
  buildResearchUnderstanding,
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

/**
 * Research context — Understanding first (facts · interpretation · sources · gaps),
 * then Memory · source highlights · Lab as supporting evidence — not a CV dump.
 * Unbound: one compact zero-state + connect CTA; no empty section shells.
 * No inline Memory edits — browser-local identity lives in Workspace preferences.
 */
export function ProfilePage({
  profile,
  selectedWorkId = null,
  onSelectWork,
  onGoTab,
  onSuggestSearch,
  onAskAboutContext,
  onAskAboutWork,
  embedded = false,
}) {
  const bound = isProfileBound(profile);
  const showSections = profileSectionsVisible(profile);
  const mode = profileCentreMode(profile);
  const primary = profilePrimaryCommand(mode);
  const unbound = bound ? null : buildUnboundProfileCentre();
  const name = bound
    ? profile?.name_en || profile?.name || "Research context"
    : unbound.title;
  const orgLine = bound
    ? [profile?.title, profile?.discipline].filter(Boolean).join(" · ")
    : unbound.lead;
  const statusLine = bound
    ? "Research context bound on this browser"
    : unbound.hint;
  const understanding = showSections ? buildResearchUnderstanding(profile) : null;
  const brief = showSections ? buildMemoryBrief(profile) : { statement: "", descriptors: [] };
  const works = showSections ? buildWorks(profile) : { paperCount: null, items: [] };
  const lab = showSections
    ? buildLab(profile)
    : { linked: [], suggested: [], linkedTotal: 0, gapTotal: 0, exploreQuery: "" };

  const runQuery = (q) => {
    const query = String(q || "").trim();
    if (query && onSuggestSearch) {
      onSuggestSearch(query);
      return;
    }
    onGoTab?.("browse");
  };

  const openLibrary = () => onGoTab?.("library");
  const exploreGaps = () => {
    const q = lab.exploreQuery || lab.suggested[0]?.query || lab.suggested[0]?.label || "";
    runQuery(q);
  };

  return (
    <PageShell
      className={`rd-v2-profile-page${bound ? "" : " is-unbound"}${embedded ? " is-embedded" : ""}`}
      title={embedded ? null : "Research context"}
      lead={
        embedded
          ? null
          : bound
            ? "What Research Drive understands for this browser"
            : "Bind a faculty email preference for this browser"
      }
    >
      <section
        className={`rd-v2-profile-identity${bound ? "" : " is-zero"}`}
        aria-label="Faculty identity"
        data-testid="profile-identity"
      >
        <div className="rd-v2-profile-ident">
          {!bound ? (
            <span className="rd-v2-profile-badge quiet" data-testid="profile-unbound-badge">
              {unbound.badge}
            </span>
          ) : (
            <span className="rd-v2-profile-badge quiet" data-testid="profile-bound-badge">
              Bound
            </span>
          )}
          <h2 className="rd-v2-profile-name">{name}</h2>
          {orgLine ? <p className="rd-v2-profile-org">{orgLine}</p> : null}
          <p className="rd-v2-profile-hint" data-testid="profile-context-status">
            {statusLine}
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

      {showSections && understanding?.synthesis ? (
        <section
          className="rd-v2-profile-section rd-v2-profile-understanding"
          data-testid="profile-understanding"
          data-section="understanding"
          aria-labelledby="profile-understanding-title"
        >
          <header className="rd-v2-profile-section-head">
            <h2 id="profile-understanding-title">What Drive understands</h2>
            <span>Structured reading</span>
          </header>

          <p className="rd-v2-profile-understanding-synthesis" data-testid="profile-understanding-synthesis">
            {understanding.synthesis}
          </p>

          <div className="rd-v2-profile-understanding-grid">
            {understanding.threads.length ? (
              <div className="rd-v2-profile-understanding-block" data-testid="profile-understanding-threads">
                <h3>Supported threads</h3>
                <ul>
                  {understanding.threads.map((t) => (
                    <li key={t.id}>
                      <span>{t.label}</span>
                      <em>{t.source}</em>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {understanding.held ? (
              <div className="rd-v2-profile-understanding-block" data-testid="profile-understanding-held">
                <h3>Most relevant held evidence</h3>
                <p>
                  {understanding.held.label}
                  <em> — {understanding.held.detail}</em>
                </p>
              </div>
            ) : null}

            {understanding.missing ? (
              <div className="rd-v2-profile-understanding-block" data-testid="profile-understanding-missing">
                <h3>Open gaps</h3>
                <p>
                  {understanding.missing.label}
                  <em> — {understanding.missing.detail}</em>
                </p>
              </div>
            ) : null}
          </div>

          <div className="rd-v2-profile-understanding-layers">
            {understanding.facts.length ? (
              <div data-testid="profile-understanding-facts">
                <h3>Facts on file</h3>
                <ul>
                  {understanding.facts.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div data-testid="profile-understanding-interpretation">
              <h3>Supported interpretation</h3>
              <p>
                Deterministic composition of the fields above. It shapes Discover ranking and Ask
                context on this browser; it is not a verified research claim.
              </p>
            </div>
            {understanding.unknowns.length ? (
              <div data-testid="profile-understanding-unknowns">
                <h3>Unknowns</h3>
                <ul>
                  {understanding.unknowns.map((u) => (
                    <li key={u}>{u}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div data-testid="profile-understanding-unknowns">
                <h3>Unknowns</h3>
                <p>No structural gaps in the fields used for this reading.</p>
              </div>
            )}
            {understanding.provenance.length ? (
              <div data-testid="profile-understanding-provenance">
                <h3>Sources and evidence</h3>
                <ul>
                  {understanding.provenance.map((p) => (
                    <li key={p.kind}>{p.label}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          {understanding.askContext && onAskAboutContext ? (
            <button
              type="button"
              className="rd-v2-btn sm"
              data-testid="profile-ask-about-context"
              onClick={() => onAskAboutContext(understanding.askContext)}
            >
              Ask about this context
            </button>
          ) : null}
        </section>
      ) : null}

      {showSections ? (
        <>
      <section
        className="rd-v2-profile-section rd-v2-profile-memory-section"
        data-testid="profile-memory"
        data-section="memory"
        aria-labelledby="profile-memory-title"
      >
        <header className="rd-v2-profile-section-head">
          <h2 id="profile-memory-title">Saved context</h2>
          <span>{bound ? (brief.statement ? "On file" : "None yet") : "Unavailable"}</span>
        </header>
        {bound && brief.statement ? (
          <div className="rd-v2-profile-memory-brief">
            <p className="rd-v2-profile-memory-statement" data-testid="profile-memory-statement">
              {brief.statement}
            </p>
            {brief.descriptors.length ? (
              <ul className="rd-v2-profile-memory-descriptors">
                {brief.descriptors.map((d) => (
                  <li key={d.id} data-testid={`profile-memory-${d.id}`}>
                    <span className="rd-v2-profile-memory-desc-label">{d.label}</span>
                    <span className="rd-v2-profile-memory-desc-text">{d.text}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            <button
              type="button"
              className="rd-v2-linkish rd-v2-profile-manage-context"
              data-testid="profile-manage-context"
              onClick={() => onGoTab?.("settings")}
            >
              Change research context
            </button>
          </div>
        ) : (
          <p className="rd-v2-empty-inline" data-testid="profile-memory-empty">
            {bound
              ? "No research statement on file yet."
              : "Saved context unavailable until a faculty email is attached."}
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
          <h2 id="profile-works-title">Source highlights</h2>
          {bound && works.paperCount ? (
            <span className="rd-v2-profile-works-count">{works.paperCount} indexed</span>
          ) : null}
          {!bound ? <span>Unavailable</span> : null}
        </header>
        {bound && works.items.length ? (
          <>
          <ul className="rd-v2-profile-works" role="listbox" aria-label="Source highlights">
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
          {selectedWorkId && onAskAboutWork ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              data-testid="profile-ask-about-work"
              onClick={() => {
                const work = works.items.find((w) => w.raw === selectedWorkId);
                if (work) onAskAboutWork(work);
              }}
            >
              Ask about this work
            </button>
          ) : null}
          </>
        ) : (
          <p className="rd-v2-empty-inline" data-testid="profile-works-empty">
            {bound
              ? works.paperCount
                ? "Indexed count on file; highlights not listed."
                : "No source highlights on file."
              : "Source highlights unavailable until a faculty email is attached."}
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
          <h2 id="profile-lab-title">Evidence links</h2>
          <span>Linked · gaps</span>
        </header>

        <div className="rd-v2-profile-lab-block">
          <h3 className="rd-v2-profile-lab-label">Linked evidence</h3>
          {bound && lab.linked.length ? (
            <ul className="rd-v2-profile-lab-rows">
              {lab.linked.map((row) => (
                <li key={row.id}>
                  <span className="rd-v2-profile-lab-title" title={row.label}>
                    {row.label}
                  </span>
                  <span className="rd-v2-profile-lab-meta">{row.routeLabel}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rd-v2-empty-inline" data-testid="profile-lab-linked-empty">
              {bound ? "None linked yet" : "Lab links unavailable until a faculty email is attached."}
            </p>
          )}
        </div>

        <div className="rd-v2-profile-lab-block">
          <h3 className="rd-v2-profile-lab-label">Open gaps</h3>
          {bound && lab.suggested.length ? (
            <ul className="rd-v2-profile-lab-rows">
              {lab.suggested.map((row) => (
                <li key={row.id}>
                  <span className="rd-v2-profile-lab-title" title={row.label}>
                    {row.label}
                    <em> — {row.reason}</em>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rd-v2-empty-inline" data-testid="profile-lab-gaps-empty">
              {bound ? "No open gaps" : "Gaps unavailable until a faculty email is attached."}
            </p>
          )}
        </div>

        {bound ? (
          <div className="rd-v2-profile-lab-links" data-testid="profile-lab-links">
            <button
              type="button"
              className="rd-v2-linkish"
              data-testid="profile-lab-view-linked"
              onClick={openLibrary}
            >
              View all linked evidence
            </button>
            <button
              type="button"
              className="rd-v2-linkish"
              data-testid="profile-lab-explore-gaps"
              onClick={exploreGaps}
              disabled={!lab.exploreQuery && !lab.suggested.length}
            >
              Explore gaps
            </button>
          </div>
        ) : null}
      </section>
        </>
      ) : null}
    </PageShell>
  );
}

/**
 * DETAIL rail — understanding provenance, or selected-work Ask.
 * Sticky CTA only for real Ask / Connect actions.
 */
export function ProfileDetailPanel({
  profile,
  selectedWork = null,
  onGoTab,
  onClearWork,
  onAskAbout,
  onAskAboutContext,
}) {
  const understanding = isProfileBound(profile) ? buildResearchUnderstanding(profile) : null;
  const rail = buildProfileRailState({
    profile: profile ?? { unknown: true },
    selectedWork,
    profileResolved: true,
    understanding,
  });

  return (
    <RailFrame>
      <RailEntityHeader
        id="profile"
        title={rail.identity[0] || "Profile"}
        description={rail.identity.slice(1).filter(Boolean).join(" · ") || null}
      />
      <div className="rd-v2-rail-scroll" data-testid="profile-detail-rail">
        <section className="rd-v2-rail-value-brief" aria-label="Derivation">
          <p className="rd-v2-rail-section-label">Derivation</p>
          <p>{rail.judgement}</p>
        </section>
        {rail.provenance?.length ? (
          <section className="rd-v2-profile-rail-block" data-testid="profile-rail-provenance">
            <h3>Sources used</h3>
            <ul>
              {rail.provenance.map((p) => (
                <li key={p.kind || p.label}>{p.label}</li>
              ))}
            </ul>
          </section>
        ) : null}
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
      </div>
      {rail.primaryAction ? (
        <RailStickyFooter>
          {rail.primaryAction.id === "ask-work" ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              data-testid="profile-ask-about-work"
              onClick={() => onAskAbout?.(selectedWork)}
            >
              {rail.primaryAction.label}
            </button>
          ) : rail.primaryAction.id === "ask-context" ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              data-testid="profile-ask-about-context-rail"
              onClick={() => onAskAboutContext?.(understanding?.askContext)}
            >
              {rail.primaryAction.label}
            </button>
          ) : rail.primaryAction.id === "clear-work" ? (
            <button type="button" className="rd-v2-btn sm primary" onClick={() => onClearWork?.()}>
              {rail.primaryAction.label}
            </button>
          ) : rail.primaryAction.tab ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              onClick={() => onGoTab?.(rail.primaryAction.tab)}
            >
              {rail.primaryAction.label}
            </button>
          ) : null}
        </RailStickyFooter>
      ) : null}
    </RailFrame>
  );
}
