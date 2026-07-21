import { useEffect, useState } from "react";
import { facultyProfile } from "@/v2/api";
import { saveUserEmail } from "@/v2/deskSession";
import {
  PILOT_PREVIEW_EMAIL,
  buildDeskRead,
  buildLab,
  buildMemoryCards,
  buildWorks,
} from "@/v2/profileViewModel";
import { PageShell } from "@/v2/ui";

function memoryText(card, prefix) {
  return String(card?.text || "").replace(new RegExp(`^${prefix}:\\s*`, "i"), "");
}

function memoryLabel(card) {
  if (card?.id === "focus") return "Research focus";
  if (card?.id === "methods") return "Methods";
  if (card?.id === "also") return "Research context";
  if (card?.id === "current") return "Current research direction";
  return "Research memory";
}

/**
 * Profile — Memory · Works · Lab (PROFILE_GROUNDED_FREEZE).
 * Unbound desk shows labelled EXAMPLE pilot from faculty registry.
 */
export function ProfilePage({ profile, onGoTab, onSuggestSearch, onProfileRefresh }) {
  const bound = Boolean(profile && !profile.unknown);
  const [pilot, setPilot] = useState(null);
  const [pilotLoading, setPilotLoading] = useState(!bound);

  useEffect(() => {
    if (bound) {
      setPilot(null);
      setPilotLoading(false);
      return undefined;
    }
    let cancelled = false;
    setPilotLoading(true);
    facultyProfile(PILOT_PREVIEW_EMAIL)
      .then((data) => {
        if (cancelled) return;
        if (data?.found && data.profile && !data.profile.unknown) setPilot(data.profile);
        else setPilot(null);
      })
      .catch(() => {
        if (!cancelled) setPilot(null);
      })
      .finally(() => {
        if (!cancelled) setPilotLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bound]);

  const previewing = !bound && Boolean(pilot);
  const active = bound ? profile : pilot;
  const name = active?.name_en || active?.name || "Research profile";
  const paperCount = active?.paper_count_parsed || active?.paper_count || null;
  const orgLine = [active?.title, active?.discipline].filter(Boolean).join(" · ");
  const email = active?.email || "";
  const memory = buildMemoryCards(active);
  const works = buildWorks(active);
  const lab = buildLab(active);
  const currentMemory = memory.find((card) => card.id === "current") || null;
  const savedMemory = memory.filter((card) => card.id !== "current");
  const savedCount = memory.length;

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
      className={`rd-v2-profile-page rd-v2-profile-grounded${previewing ? " is-preview" : ""}`}
      title="Profile"
      lead="Research memory carried into Discover and Ask"
    >
      <section className="rd-v2-profile-identity" aria-label="Faculty identity">
        <div className="rd-v2-profile-ident">
          <span className="rd-v2-profile-kicker">Research memory</span>
          {previewing ? <span className="rd-v2-profile-badge">Example</span> : null}
          <h2 className="rd-v2-profile-name">{name}</h2>
          {orgLine ? <p className="rd-v2-profile-org">{orgLine}</p> : null}
          <p className="rd-v2-profile-hint">
            {email || "—"}
            {previewing ? " · Example · pilot faculty" : ""}
          </p>
        </div>
        <div className="rd-v2-profile-identity-side">
          <div className="rd-v2-profile-identity-metrics" aria-label="Research memory summary">
            {paperCount ? (
              <span>
                <strong>{paperCount}</strong>
                <em>indexed works</em>
              </span>
            ) : null}
            {savedCount ? (
              <span>
                <strong>{savedCount}</strong>
                <em>saved contexts</em>
              </span>
            ) : null}
          </div>
          {previewing ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              onClick={() => {
                saveUserEmail(PILOT_PREVIEW_EMAIL);
                onProfileRefresh?.();
              }}
            >
              Bind example identity
            </button>
          ) : !bound ? (
            <button type="button" className="rd-v2-btn sm primary" onClick={() => onGoTab?.("settings")}>
              Use my email
            </button>
          ) : null}
        </div>
      </section>

      {pilotLoading && !bound ? (
        <p className="rd-v2-profile-loading" data-testid="profile-know-empty">
          Loading example profile…
        </p>
      ) : null}

      {(bound || previewing) && memory.length ? (
        <section
          className="rd-v2-profile-section rd-v2-profile-memory-section"
          data-testid="profile-memory"
          aria-labelledby="profile-memory-title"
        >
          <header className="rd-v2-profile-section-head">
            <div>
              <h2 id="profile-memory-title">Memory</h2>
              <p>Context Research Drive should remember while finding and evaluating evidence.</p>
            </div>
            <span>{savedCount} saved</span>
          </header>
          <div className="rd-v2-profile-memory-layout">
            <ul className="rd-v2-profile-memory">
              {savedMemory.map((card) => (
                <li key={card.id} className="rd-v2-profile-memory-card" data-memory={card.id}>
                  <span>{memoryLabel(card)}</span>
                  <strong>
                    {memoryText(
                      card,
                      card.id === "also" ? "Also" : card.id === "methods" ? "Methods" : "Focus",
                    )}
                  </strong>
                </li>
              ))}
            </ul>
            {currentMemory ? (
              <article className="rd-v2-profile-memory-anchor" data-memory="current">
                <span>Current research direction</span>
                <strong>{memoryText(currentMemory, "Current")}</strong>
                <p>Used when finding and evaluating evidence.</p>
              </article>
            ) : null}
          </div>
        </section>
      ) : (bound || previewing) && !memory.length ? (
        <section className="rd-v2-profile-section" data-testid="profile-memory-thin" aria-label="Memory">
          <header className="rd-v2-profile-section-head">
            <div>
              <h2>Memory</h2>
              <p>Thin faculty profiles keep Memory empty rather than inventing research context.</p>
            </div>
          </header>
          <p className="rd-v2-empty-inline">No specialties, tracks, or methods on file.</p>
        </section>
      ) : null}

      {(bound || previewing) && (works.items.length || works.paperCount) ? (
        <section
          className="rd-v2-profile-section rd-v2-profile-works-section"
          data-testid="profile-works"
          aria-labelledby="profile-works-title"
        >
          <header className="rd-v2-profile-section-head">
            <div>
              <h2 id="profile-works-title">Works</h2>
              <p>Research output that helps ground recurring evidence needs.</p>
            </div>
            {works.paperCount ? <span>{works.paperCount} indexed</span> : null}
          </header>
          {works.items.length ? (
            <ol className="rd-v2-profile-works">
              {works.items.map((work, index) => (
                <li key={work.raw}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{work.title}</strong>
                  <em aria-hidden>→</em>
                </li>
              ))}
            </ol>
          ) : (
            <p className="rd-v2-empty-inline">Indexed count on file; highlights not listed.</p>
          )}
        </section>
      ) : null}

      {bound || previewing ? (
        <section
          className="rd-v2-profile-section rd-v2-profile-lab-section"
          data-testid="profile-lab"
          aria-labelledby="profile-lab-title"
        >
          <header className="rd-v2-profile-section-head">
            <div>
              <h2 id="profile-lab-title">Lab</h2>
              <p>Data relationships already attached to this research context and useful next connections.</p>
            </div>
            <span>Linked · next</span>
          </header>

          <div className="rd-v2-profile-lab-grid">
            <div className="rd-v2-profile-lab-block">
              <h3 className="rd-v2-profile-lab-label">Linked to you</h3>
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
                  None yet
                </p>
              )}
            </div>

            <div className="rd-v2-profile-lab-block rd-v2-profile-lab-suggested">
              <h3 className="rd-v2-profile-lab-label">Suggested</h3>
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
                <p className="rd-v2-empty-inline">—</p>
              )}
            </div>
          </div>
        </section>
      ) : !pilotLoading ? (
        <p className="rd-v2-profile-loading" data-testid="profile-know-empty">
          Bind a YZU faculty email in Settings, or load the example research memory.
        </p>
      ) : null}
    </PageShell>
  );
}

/** DETAIL rail content for Profile — Scholar / Strengths / Desk. */
export function ProfileDetailPanel({ profile }) {
  const bound = Boolean(profile && !profile.unknown);
  const [pilot, setPilot] = useState(null);

  useEffect(() => {
    if (bound) {
      setPilot(null);
      return undefined;
    }
    let cancelled = false;
    facultyProfile(PILOT_PREVIEW_EMAIL)
      .then((data) => {
        if (!cancelled && data?.found && data.profile && !data.profile.unknown) setPilot(data.profile);
      })
      .catch(() => {
        if (!cancelled) setPilot(null);
      });
    return () => {
      cancelled = true;
    };
  }, [bound]);

  const previewing = !bound && Boolean(pilot);
  const active = bound ? profile : pilot;
  const read = buildDeskRead(active, { previewing });

  if (!active) {
    return (
      <div className="rd-v2-profile-rail" data-testid="profile-detail-rail">
        <p className="rd-v2-empty-inline">Loading…</p>
      </div>
    );
  }

  return (
    <div className="rd-v2-profile-rail" data-testid="profile-detail-rail">
      <section className="rd-v2-profile-rail-block">
        <h3>Scholar</h3>
        <p>{read.scholar}</p>
      </section>
      {read.strengths.length ? (
        <section className="rd-v2-profile-rail-block">
          <h3>Strengths</h3>
          <ul>
            {read.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {read.desk ? (
        <section className="rd-v2-profile-rail-block">
          <h3>Desk</h3>
          <p>{read.desk}</p>
        </section>
      ) : null}
    </div>
  );
}
