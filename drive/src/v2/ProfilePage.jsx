import { useEffect, useId, useRef, useState } from "react";
import { facultyProfile } from "@/v2/api";
import { loadUserEmail, saveUserEmail } from "@/v2/deskSession";
import { loadSettings, saveSettings } from "@/v2/settingsStore";
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
  profileSectionsVisible,
} from "@/v2/profilePresentation";
import { PageShell } from "@/v2/ui";
import {
  RailEntityHeader,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";

/**
 * Faculty-email binding lives in Research context (identity / context source).
 * Bound: quiet source line + Change → inline save/clear.
 * Unbound: email field + Connect/Save in place (never Workspace preferences).
 */
function ContextSourceBinding({
  bound,
  profile,
  onProfileRefresh,
  onToast,
  onClearContext,
  editing,
  onEditingChange,
  inputRef,
}) {
  const inputId = useId();
  const storedEmail = loadUserEmail() || loadSettings().email || "";
  const boundEmail = profile?.email || storedEmail;
  const [emailDraft, setEmailDraft] = useState(() => boundEmail || "");
  const [saving, setSaving] = useState(false);
  const [bindStatus, setBindStatus] = useState(null);

  useEffect(() => {
    setEmailDraft(boundEmail || "");
  }, [boundEmail]);

  useEffect(() => {
    if (!boundEmail) {
      setBindStatus(null);
      return;
    }
    if (profile && !profile.unknown && (profile.name_en || profile.name)) {
      setBindStatus({ ok: true, name: profile.name_en || profile.name });
    } else if (profile?.unknown && profile?.email) {
      setBindStatus({ ok: false, email: profile.email });
    }
  }, [profile, boundEmail]);

  const saveEmail = async () => {
    const email = saveUserEmail(emailDraft);
    saveSettings({ email });
    setSaving(true);
    setBindStatus(null);
    try {
      if (!email) {
        onProfileRefresh?.();
        setBindStatus(null);
        onEditingChange?.(false);
        onToast?.("Research context cleared on this browser");
        return;
      }
      const data = await facultyProfile(email);
      onProfileRefresh?.();
      if (data?.found && data.profile) {
        const name = data.profile.name_en || data.profile.name || email;
        setBindStatus({ ok: true, name });
        onEditingChange?.(false);
        onToast?.(`Context bound to ${name} on this browser`);
      } else if (data?.found) {
        setBindStatus({ ok: true, name: email });
        onEditingChange?.(false);
        onToast?.(`Context bound for ${email} on this browser`);
      } else {
        setBindStatus({ ok: false, email });
        onToast?.(`No faculty profile resolved for ${email}`);
      }
    } catch {
      onProfileRefresh?.();
      setBindStatus({ ok: false, email: emailDraft.trim() || boundEmail });
      onToast?.(`Could not resolve faculty profile for ${emailDraft.trim() || boundEmail}`);
    } finally {
      setSaving(false);
    }
  };

  const clearContext = () => {
    if (onClearContext) {
      onClearContext();
    } else {
      saveUserEmail("");
      saveSettings({ email: "" });
      onProfileRefresh?.();
      onToast?.("Research context cleared on this browser");
    }
    setEmailDraft("");
    setBindStatus(null);
    onEditingChange?.(false);
  };

  const showEditor = !bound || editing;

  return (
    <div className="rd-v2-profile-context-source" data-testid="profile-context-source">
      {bound && !editing ? (
        <p className="rd-v2-profile-source-line" data-testid="profile-source-line">
          <span className="rd-v2-profile-source-label">Source</span>
          <span className="rd-v2-profile-source-email">{boundEmail || "Faculty email on this browser"}</span>
          <button
            type="button"
            className="rd-v2-linkish"
            data-testid="profile-context-change"
            onClick={() => onEditingChange?.(true)}
          >
            Change
          </button>
        </p>
      ) : null}

      {showEditor ? (
        <div className="rd-v2-profile-bind-form" data-testid="profile-bind-form">
          <label className="rd-v2-settings-label" htmlFor={inputId}>
            Faculty email
          </label>
          <input
            ref={inputRef}
            id={inputId}
            type="email"
            className="rd-v2-input"
            placeholder="name@yzu.edu.tw"
            value={emailDraft}
            onChange={(e) => setEmailDraft(e.target.value)}
            autoComplete="email"
            data-testid="profile-email-input"
          />
          <p className="rd-v2-settings-hint" data-testid="profile-email-hint">
            Browser-local preference for Research context, Discover, and Ask — not a sign-in.
          </p>
          <div className="rd-v2-settings-actions">
            <button
              type="button"
              className="rd-v2-btn sm primary"
              data-testid="profile-save-identity"
              disabled={saving}
              onClick={saveEmail}
            >
              {saving ? "Saving…" : bound ? "Save context" : "Connect faculty email"}
            </button>
            {bound || boundEmail || emailDraft ? (
              <button
                type="button"
                className="rd-v2-btn sm"
                data-testid="profile-clear-context"
                disabled={saving || (!boundEmail && !emailDraft)}
                onClick={clearContext}
              >
                Clear context
              </button>
            ) : null}
            {bound && editing ? (
              <button
                type="button"
                className="rd-v2-btn sm"
                data-testid="profile-context-cancel"
                disabled={saving}
                onClick={() => {
                  setEmailDraft(boundEmail || "");
                  onEditingChange?.(false);
                }}
              >
                Cancel
              </button>
            ) : null}
          </div>
          {bindStatus?.ok ? (
            <p className="rd-v2-settings-bind-ok" data-testid="profile-bind-status">
              Bound to {bindStatus.name} on this browser.
            </p>
          ) : null}
          {bindStatus && !bindStatus.ok ? (
            <p className="rd-v2-settings-bind-fail" data-testid="profile-bind-status">
              No faculty profile for {bindStatus.email}. Email is saved locally.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Research context — Understanding first (facts · interpretation · sources · gaps),
 * then Memory · source highlights · Lab as supporting evidence — not a CV dump.
 * Unbound: one compact zero-state + inline faculty-email connect; no empty section shells.
 * Browser-local identity / context source is owned here — not Workspace preferences.
 */
export function ProfilePage({
  profile,
  selectedWorkId = null,
  onSelectWork,
  onGoTab,
  onSuggestSearch,
  onAskAboutContext,
  onAskAboutWork,
  onProfileRefresh,
  onToast,
  onClearContext,
  embedded = false,
}) {
  const bound = isProfileBound(profile);
  const showSections = profileSectionsVisible(profile);
  const mode = profileCentreMode(profile);
  const unbound = bound ? null : buildUnboundProfileCentre();
  const [sourceEditing, setSourceEditing] = useState(!bound);
  const emailInputRef = useRef(null);
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

  useEffect(() => {
    setSourceEditing(!bound);
  }, [bound, mode]);

  useEffect(() => {
    if (sourceEditing && emailInputRef.current) {
      emailInputRef.current.focus();
    }
  }, [sourceEditing]);

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

  const beginChangeContext = () => {
    setSourceEditing(true);
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
          <ContextSourceBinding
            bound={bound}
            profile={profile}
            onProfileRefresh={onProfileRefresh}
            onToast={onToast}
            onClearContext={onClearContext}
            editing={sourceEditing}
            onEditingChange={setSourceEditing}
            inputRef={emailInputRef}
          />
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

          <div className="rd-v2-profile-understanding-primary">
            <div data-testid="profile-understanding-interpretation">
              <h3>Supported interpretation</h3>
              <p>
                Deterministic composition of the fields above. It shapes Discover ranking and Ask
                context on this browser; it is not a verified research claim.
              </p>
            </div>
          </div>

          <div
            className="rd-v2-profile-understanding-columns"
            data-testid="profile-understanding-columns"
          >
            <div
              className="rd-v2-profile-understanding-col rd-v2-profile-understanding-col--threads"
              data-testid="profile-understanding-col-threads"
            >
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

              {understanding.facts.length ? (
                <div
                  className="rd-v2-profile-understanding-block"
                  data-testid="profile-understanding-facts"
                >
                  <h3>Facts on file</h3>
                  <ul>
                    {understanding.facts.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>

            <div
              className="rd-v2-profile-understanding-col rd-v2-profile-understanding-col--evidence"
              data-testid="profile-understanding-col-evidence"
            >
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
                <div
                  className="rd-v2-profile-understanding-block"
                  data-testid="profile-understanding-missing"
                >
                  <h3>Open gaps</h3>
                  <p>
                    {understanding.missing.label}
                    <em> — {understanding.missing.detail}</em>
                  </p>
                </div>
              ) : null}

              {understanding.unknowns.length ? (
                <div
                  className="rd-v2-profile-understanding-block"
                  data-testid="profile-understanding-unknowns"
                >
                  <h3>Unknowns</h3>
                  <ul>
                    {understanding.unknowns.map((u) => (
                      <li key={u}>{u}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div
                  className="rd-v2-profile-understanding-block"
                  data-testid="profile-understanding-unknowns"
                >
                  <h3>Unknowns</h3>
                  <p>No structural gaps in the fields used for this reading.</p>
                </div>
              )}
            </div>
          </div>

          {understanding.provenance.length ? (
            <details
              className="rd-v2-profile-understanding-basis"
              data-testid="profile-understanding-provenance"
            >
              <summary>Evidence basis</summary>
              <ul>
                {understanding.provenance.map((p) => (
                  <li key={p.kind}>{p.label}</li>
                ))}
              </ul>
            </details>
          ) : null}

          {!embedded && understanding.askContext && onAskAboutContext ? (
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
              onClick={beginChangeContext}
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
