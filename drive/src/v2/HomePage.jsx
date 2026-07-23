import { useEffect, useMemo, useState } from "react";
import { resolveCapacityMark } from "@/v2/capacityMarks";
import { GuidedState, Skeleton } from "@/v2/InteractionFeedback";
import { readResourcesRollupCache, writeResourcesRollupCache } from "@/v2/resourcesRollupCache";
import { PageShell } from "@/v2/ui";
import {
  buildPickUp,
  buildRecentTrail,
  buildRecommendedEvidence,
  buildResourceHeadroom,
  projectRollupFromHealth,
} from "@/v2/homeIteration10";

/**
 * Home — Iteration 10 freeze
 * docs/HOME_FULL_SCALE_FREEZE_2026-07-16.md
 *
 * TOP: Pick Up (~65%) | Resource Headroom (~35%)
 * MIDDLE: Recommended Evidence (≤2)
 * BOTTOM: Recent Trail (≤3)
 * No desktop page scroll. No three-lane action strip.
 */

function HeadroomBar({ pct, warn }) {
  if (pct == null || !Number.isFinite(pct)) return null;
  const width = Math.max(0, Math.min(100, pct));
  return (
    <div className={`rd-v2-home-headroom-bar${warn ? " warn" : ""}`} aria-hidden>
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

function HomeHeadroomMark({ markId }) {
  const mark = resolveCapacityMark(markId);
  if (!mark) return null;
  return (
    <span className="rd-v2-home-headroom-mark" aria-hidden>
      <img src={mark.src} alt="" title={mark.title || mark.alt} width={16} height={16} />
    </span>
  );
}

function PickUpCard({ point, loading, onContinue, onReview }) {
  if (loading) {
    return (
      <div className="rd-v2-home-pickup-card" data-testid="home-continue" aria-busy="true">
        <span className="rd-v2-home-eyebrow">Pick up</span>
        <Skeleton lines={3} label="Loading resume point" />
      </div>
    );
  }
  if (!point) {
    return (
      <div className="rd-v2-home-pickup-card" data-testid="home-continue">
        <span className="rd-v2-home-eyebrow">Pick up</span>
        <GuidedState
          eyebrow="No resume point"
          title="Open the vault or find missing evidence"
          detail="Home has no typed resume object in this session yet."
          checks={["Library holds registered assets", "Discover searches beyond holdings"]}
        />
      </div>
    );
  }
  return (
    <article
      className={`rd-v2-home-pickup-card${point.warn ? " warn" : ""}`}
      data-testid="home-continue"
      data-kind={point.kind}
      aria-label={`Pick up: ${point.title}`}
    >
      <span className="rd-v2-home-eyebrow">Pick up</span>
      <h2>{point.title}</h2>
      <p className="rd-v2-home-pickup-state">{point.stateSummary}</p>
      <div className="rd-v2-home-pickup-foot">
        <div>
          {point.pill ? <span className="rd-v2-pill">{point.pill}</span> : null}
          <span className="rd-v2-home-pickup-loc">{point.location}</span>
        </div>
        {point.action === "review" ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onReview?.(point)}>
            Review
          </button>
        ) : (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onContinue?.(point)}>
            Continue
          </button>
        )}
      </div>
      {point.dataset?.dataset_id ? (
        <p className="rd-v2-home-continue-id mono">{point.dataset.dataset_id}</p>
      ) : null}
    </article>
  );
}

export function HomePage({
  datasets = [],
  health,
  jobs = [],
  profile,
  acquisitions = [],
  resourcesRollup,
  onGoTab,
  onOpenAttention,
  onSelectDataset,
  onPreviewDataset,
  onSuggestSearch,
}) {
  const loading = health == null && datasets.length === 0;
  // Mirror Resources cache-first: never block Home headroom on a cold /desk/resources round-trip.
  const [cachedRollup, setCachedRollup] = useState(() => readResourcesRollupCache());
  useEffect(() => {
    if (resourcesRollup && typeof resourcesRollup === "object") {
      writeResourcesRollupCache(resourcesRollup);
      setCachedRollup(resourcesRollup);
    }
  }, [resourcesRollup]);
  const headroomRollup = useMemo(() => {
    if (resourcesRollup && typeof resourcesRollup === "object") return resourcesRollup;
    if (cachedRollup) return cachedRollup;
    return projectRollupFromHealth(health);
  }, [resourcesRollup, cachedRollup, health]);
  const headroomLoading = headroomRollup == null && resourcesRollup === undefined && health == null;
  const pickUp = useMemo(
    () => buildPickUp({ datasets, jobs, health, acquisitions, profile }),
    [datasets, jobs, health, acquisitions, profile],
  );
  const headroom = useMemo(
    () => buildResourceHeadroom(headroomRollup),
    [headroomRollup],
  );
  const recommended = useMemo(
    () => buildRecommendedEvidence(profile, { limit: 2 }),
    [profile],
  );
  const trail = useMemo(
    () => buildRecentTrail({ jobs, datasets, limit: 3 }),
    [jobs, datasets],
  );

  const continuePrimary = (point) => {
    if (!point?.dataset) {
      onGoTab(point?.tab || "library");
      return;
    }
    // openLibraryDataset (passed as onSelectDataset) sets tab+selection atomically.
    onSelectDataset?.(point.dataset);
  };

  const reviewDecision = (point) => {
    // Freeze: approvals / Needs you live on Discover History, not Resources Usage.
    if (onOpenAttention) {
      onOpenAttention({
        id: point.id,
        kind: "approval",
        tab: "browse",
        discoverMode: "history",
        title: point.title,
        resourceRow: {
          kind: "active",
          key: point.job?.id ? `job-${point.job.id}` : "jobs-pending",
          label: point.title,
          metric: point.pill,
          section: "active",
          warn: true,
          ok: false,
          job: point.job,
        },
      });
      return;
    }
    onGoTab("browse");
  };

  return (
    <PageShell
      className="rd-v2-home-page rd-v2-home-i10"
      title="Home"
      lead="Resume · headroom · durable consequences"
      footer={null}
    >
      <div className="rd-v2-home-topband">
        <section className="rd-v2-home-pickup" aria-label="Pick up">
          <PickUpCard
            point={pickUp.primary}
            loading={loading}
            onContinue={continuePrimary}
            onReview={reviewDecision}
          />
          {pickUp.secondary ? (
            <button
              type="button"
              className={`rd-v2-home-pickup-secondary${pickUp.secondary.warn ? " warn" : ""}`}
              onClick={() =>
                pickUp.secondary.action === "review"
                  ? reviewDecision(pickUp.secondary)
                  : continuePrimary(pickUp.secondary)
              }
            >
              <strong>{pickUp.secondary.title}</strong>
              <span>{pickUp.secondary.stateSummary}</span>
              <em>
                {pickUp.secondary.location}
                {pickUp.secondary.action === "review" ? " · Review" : " · Continue →"}
              </em>
            </button>
          ) : null}
        </section>

        <section className="rd-v2-home-headroom" aria-label="Resource headroom">
          <div className="rd-v2-home-headroom-head">
            <span className="rd-v2-home-eyebrow">Resource headroom</span>
            <button type="button" className="rd-v2-linkish" onClick={() => onGoTab("resources")}>
              Resources →
            </button>
          </div>
          {loading || headroomLoading ? (
            <Skeleton lines={3} label="Loading headroom" />
          ) : headroom.length ? (
            <ul className="rd-v2-home-headroom-list">
              {headroom.map((slot) => (
                <li key={slot.id} className={slot.warn ? "warn" : undefined}>
                  <div className="rd-v2-home-headroom-row">
                    <strong>
                      {slot.markId ? <HomeHeadroomMark markId={slot.markId} /> : null}
                      {slot.name}
                    </strong>
                    <span>{slot.metric}</span>
                  </div>
                  <HeadroomBar pct={slot.pct} warn={slot.warn} />
                  <div className="rd-v2-home-headroom-meta">
                    <span>{slot.headroom}</span>
                    <button
                      type="button"
                      className="rd-v2-linkish"
                      onClick={() => onGoTab("resources")}
                    >
                      {slot.action === "check" ? "Check →" : "Resources →"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rd-v2-home-headroom-empty">Capacity signals load with Resources.</p>
          )}
        </section>
      </div>

      {recommended.length ? (
        <section className="rd-v2-home-recommended" aria-label="Recommended evidence">
          <div className="rd-v2-home-section-head">
            <h2>Recommended evidence</h2>
          </div>
          <ul className="rd-v2-home-recommended-list">
            {recommended.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="rd-v2-home-recommended-row"
                  onClick={() => {
                    if (item.action === "library" && item.datasetId) {
                      onGoTab("library");
                      return;
                    }
                    if (item.query && onSuggestSearch) {
                      onSuggestSearch(item.query);
                      return;
                    }
                    onGoTab("browse");
                  }}
                >
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.reason}</span>
                  </div>
                  <em>{item.badge}</em>
                  <span className="rd-v2-home-recommended-go">
                    {item.action === "library" ? "Library →" : "Explore →"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rd-v2-home-trail" aria-label="Recent trail">
        <div className="rd-v2-home-section-head">
          <h2>Recent trail</h2>
          <button
            type="button"
            className="rd-v2-linkish"
            onClick={() => onGoTab("browse")}
          >
            View all →
          </button>
        </div>
        {trail.length ? (
          <ul className="rd-v2-home-trail-list">
            {trail.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="rd-v2-home-trail-row"
                  onClick={() => {
                    if (item.dataset) {
                      onSelectDataset?.(item.dataset);
                      return;
                    }
                    if (item.dest === "history") {
                      onGoTab("browse");
                      return;
                    }
                    onGoTab(item.dest === "library" ? "library" : "browse");
                  }}
                >
                  <span className="rd-v2-home-trail-kind">{item.kind}</span>
                  <strong>{item.title}</strong>
                  <span>{item.summary}</span>
                  <em>{item.dest === "library" ? "Library →" : "History →"}</em>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rd-v2-home-section-empty">No material machine consequences to show.</p>
        )}
      </section>
    </PageShell>
  );
}
