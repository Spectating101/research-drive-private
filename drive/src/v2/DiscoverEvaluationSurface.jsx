/**
 * Discover Evaluation Surface body — shared by rail (legacy) and focused workspace.
 * Semantics stay in discoverEvaluation / discoverLifecycle / discoverSufficiency;
 * this is presentation only.
 */

import { useMemo } from "react";
import { applyLifecycleToEvaluation, LIFECYCLE } from "@/v2/discoverLifecycle";
import { buildDiscoverEvaluation } from "@/v2/discoverEvaluation";
import {
  assessLocalSufficiency,
  applySufficiencyToActions,
  buildSufficiencyAskContext,
  sufficiencyAskPrompts,
  SUFFICIENCY,
} from "@/v2/discoverSufficiency";
import {
  RailField,
  RailFieldGrid,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";
import { EmptyRailState } from "@/v2/EmptyRailState";

const PATH_STAGES = [
  { id: "submitted", label: "Submitted" },
  { id: "approval", label: "Approval" },
  { id: "queue", label: "Queue" },
  { id: "running", label: "Running" },
  { id: "registered", label: "Registered" },
];

const SUFFICIENCY_DIMENSION_LABELS = Object.freeze({
  temporal_coverage: "Time coverage",
  grain: "Grain",
  geographic_coverage: "Geography",
  variables: "Variables",
  entity_universe: "Entity universe",
});

function sufficiencyDimensionLabel(dimension) {
  const key = String(dimension || "").trim();
  if (SUFFICIENCY_DIMENSION_LABELS[key]) return SUFFICIENCY_DIMENSION_LABELS[key];
  return key ? key.replace(/_/g, " ") : "Difference";
}

function sufficiencyLocalTitle(sufficiency) {
  const local = sufficiency?.bestLocal;
  return String(local?.title || local?.name || local?.dataset_id || "").trim();
}

export function DiscoverEvaluationSurface({
  target,
  labIds,
  catalog = [],
  onAskAbout,
  onAddToLab,
  onPreviewExternal,
  onProbeSource,
  probeState,
  onOpenInLibrary,
  lifecycle = null,
  onTrackResources,
  onReviewApproval,
  onRetryLifecycleRefresh,
  variant = "rail",
}) {
  const evaluation = target
    ? applyLifecycleToEvaluation(buildDiscoverEvaluation(target, labIds, probeState), lifecycle)
    : null;
  const sufficiency = useMemo(() => {
    if (!target) return null;
    if (target?.discover_sufficiency?.state) return target.discover_sufficiency;
    const taxonomy = target.discover_taxonomy;
    const group = Number(taxonomy?.group);
    // Lab holdings do not need local-alternative comparison against themselves.
    if (Number.isFinite(group) && group <= 2) return null;
    return assessLocalSufficiency(target, catalog);
  }, [target, catalog]);
  const exactLocalEvaluation = useMemo(() => {
    if (lifecycle || sufficiency?.state !== SUFFICIENCY.EXACT_LOCAL || !sufficiency?.bestLocal) {
      return null;
    }
    return buildDiscoverEvaluation(sufficiency.bestLocal, labIds, null);
  }, [lifecycle, sufficiency, labIds]);

  if (!target || !evaluation) {
    if (variant === "workspace") return null;
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState
            title="No candidate selected"
            hint="Search, then select a candidate to evaluate what you can use and what remains unknown."
          />
        </div>
      </RailFrame>
    );
  }

  const probeLoading = evaluation.probeLoading;
  const submitting = lifecycle?.state === LIFECYCLE.SUBMITTING;
  const targetKey = target?.candidate_key || target?.dataset_id || target?.url || evaluation.title;
  const displayDecision = exactLocalEvaluation?.decision || evaluation.decision;
  const displayUnknowns = exactLocalEvaluation?.unknowns || evaluation.unknowns;

  const baseAskPrompts = lifecycle
    ? [
        lifecycle.state === LIFECYCLE.APPROVAL_REQUIRED
          ? {
              id: "why_approval",
              label: "Why is this waiting for approval?",
              prompt: `Why is collection of ${evaluation.title} waiting for approval, and what happens after approval?`,
            }
          : null,
        lifecycle.state === LIFECYCLE.FAILED
          ? {
              id: "what_failed",
              label: "What failed?",
              prompt: `What failed while collecting ${evaluation.title}? Distinguish known errors from unknowns.`,
            }
          : null,
        lifecycle.state === LIFECYCLE.COMPLETED_UNREGISTERED ||
        lifecycle.state === LIFECYCLE.REGISTERED ||
        lifecycle.state === LIFECYCLE.QUERY_READY
          ? {
              id: "what_registered",
              label: "What will be registered?",
              prompt: `What was or will be registered from collecting ${evaluation.title}?`,
            }
          : null,
        {
          id: "can_use",
          label: "Can I use the output yet?",
          prompt: `Can I use the output of ${evaluation.title} yet? Distinguish registered vs query-ready honestly.`,
        },
      ].filter(Boolean)
    : [
        {
          id: "assess",
          label: "Assess this source",
          prompt: `Assess this Discover source: ${evaluation.title}. What is verified, what remains unknown, and what should I do next?`,
        },
        {
          id: "risks",
          label: "What are the main risks?",
          prompt: `What are the main risks of using or acquiring ${evaluation.title}? Distinguish verified facts from unknowns.`,
        },
        {
          id: "probe_next",
          label: "What should I probe next?",
          prompt: `Given ${evaluation.title}, what should I probe next, and what would still remain unknown after a successful probe?`,
        },
      ];

  const askPrompts = [
    ...(sufficiency ? sufficiencyAskPrompts(sufficiency, evaluation.title) : []),
    ...baseAskPrompts,
  ].slice(0, 4);

  const actions = sufficiency
    ? applySufficiencyToActions(evaluation.actions, sufficiency, {
        lifecycleOverrides: Boolean(lifecycle?.primaryAction),
      })
    : evaluation.actions;
  const primary = lifecycle?.primaryAction || actions.primary;
  const secondary = lifecycle?.primaryAction
    ? lifecycle.secondaryActions || []
    : actions.secondary;
  const mobileSecondary = (() => {
    if (lifecycle?.primaryAction || !secondary.length) return null;
    const preferredIds =
      sufficiency?.state === SUFFICIENCY.EXACT_LOCAL
        ? ["preview", "probe", "ask"]
        : sufficiency?.state === SUFFICIENCY.PARTIAL_LOCAL ||
            sufficiency?.state === SUFFICIENCY.RELATED_LOCAL
          ? ["open_local", "inspect_related", "preview", "probe", "ask"]
          : ["preview", "open_local", "inspect_related", "probe", "ask"];
    return preferredIds
      .map((id) => secondary.find((action) => action.id === id))
      .find(Boolean) || secondary[0];
  })();
  const mobileOverflowActions = secondary.filter((action) => action.id !== mobileSecondary?.id);
  const mobileSecondaryLabel =
    mobileSecondary?.id === "preview" && sufficiency?.state === SUFFICIENCY.EXACT_LOCAL
      ? "Inspect external source"
      : mobileSecondary?.label;
  const sufficiencyDifferences = (sufficiency?.differences || []).filter(
    (difference) => difference?.local || difference?.candidate,
  );
  const localDatasetTitle = sufficiencyLocalTitle(sufficiency);

  const openLocal = () => {
    const local = sufficiency?.bestLocal;
    if (local) onOpenInLibrary?.(local);
    else onOpenInLibrary?.(target);
  };

  const askWithSufficiency = (promptOverride) => {
    const ctx = sufficiency ? buildSufficiencyAskContext(sufficiency, target) : null;
    const label = evaluation.title;
    if (typeof promptOverride === "string" && promptOverride.trim()) {
      onAskAbout?.(
        target,
        ctx
          ? {
              prompt: [
                promptOverride.trim(),
                "",
                "Local comparison (structured — do not upgrade related to equivalent):",
                JSON.stringify(ctx, null, 2),
              ].join("\n"),
              displayText: promptOverride.trim().split("\n")[0],
            }
          : promptOverride.trim(),
      );
      return;
    }
    onAskAbout?.(
      target,
      ctx
        ? {
            prompt: [
              `Assess this Discover source for research use: ${label}.`,
              "Summarize what is verified, what remains unknown, access/acquisition constraints, local lab coverage, and the safest next action.",
              "Do not invent legal clearance, query readiness, or equivalence.",
              "",
              "Local comparison (structured):",
              JSON.stringify(ctx, null, 2),
            ].join("\n"),
            displayText: `Assess this source: ${label}`,
          }
        : undefined,
    );
  };

  const runAction = (id) => {
    if (id === "open_local" || id === "inspect_related") openLocal();
    else if (id === "open_library" || id === "inspect_record") {
      const datasetId = lifecycle?.registeredDatasetId || target?.dataset_id;
      onOpenInLibrary?.(datasetId ? { ...target, dataset_id: datasetId } : target);
    } else if (id === "add_lab") onAddToLab?.(target);
    else if (id === "probe") onProbeSource?.(target);
    else if (id === "preview") onPreviewExternal?.();
    else if (id === "review_approval") onReviewApproval?.(lifecycle?.job || target);
    else if (id === "track_resources") onTrackResources?.(lifecycle?.job || target);
    else if (id === "ask" || id === "review_access") askWithSufficiency();
  };

  const reachedStages = new Set(lifecycle?.stages || []);
  const shellClass = variant === "workspace" ? "rd-v2-eval-workspace" : "rd-v2-eval-rail";

  const body = (
    <>
      <div
        className={`rd-v2-eval-surface ${shellClass}`}
        data-testid="discover-eval-surface"
        data-variant={variant}
        data-taxonomy={evaluation.taxonomyKey}
        data-lifecycle={lifecycle?.state || ""}
        data-sufficiency={sufficiency?.state || ""}
        data-selected-title={evaluation.title}
      >
        <header className="rd-v2-eval-identity">
          <p className="rd-v2-eval-kicker">Selected candidate</p>
          <h2 className="rd-v2-eval-title">{evaluation.title}</h2>
          <p className="rd-v2-eval-source">
            {evaluation.sourceLine}
            <span aria-hidden="true"> · </span>
            {evaluation.taxonomyLabel}
          </p>
        </header>

        <section className="rd-v2-eval-decision" aria-label="Can I use this">
          <p className="rd-v2-eval-section-label">Can I use this?</p>
          <p className="rd-v2-eval-decision-headline">{displayDecision.headline}</p>
          <p className="rd-v2-eval-decision-body">{displayDecision.body}</p>
        </section>

        {lifecycle ? (
          <section
            className={`rd-v2-eval-lifecycle rd-v2-eval-lifecycle-${lifecycle.state}`}
            aria-label="Collection status"
            data-testid="discover-lifecycle"
          >
            <p className="rd-v2-eval-section-label">Collection status</p>
            <p className="rd-v2-eval-decision-headline">{lifecycle.label}</p>
            <p className="rd-v2-eval-decision-body">{lifecycle.explanation}</p>
            {lifecycle.refreshFailed ? (
              <p className="rd-v2-eval-lifecycle-warn">
                Status refresh failed · showing last known state{" "}
                <button type="button" className="rd-v2-linkish" onClick={() => onRetryLifecycleRefresh?.()}>
                  Retry
                </button>
              </p>
            ) : null}
            {lifecycle.evidence?.length ? (
              <ul className="rd-v2-eval-lifecycle-evidence">
                {lifecycle.evidence.map((item) => (
                  <li key={`${item.label}-${item.value}`}>
                    <b>{item.label}</b> {item.value}
                  </li>
                ))}
              </ul>
            ) : null}
            <ol className="rd-v2-eval-lifecycle-path" aria-label="Lifecycle path">
              {PATH_STAGES.map((stage) => (
                <li
                  key={stage.id}
                  className={`${reachedStages.has(stage.id) ? "on" : ""}${
                    lifecycle.state === LIFECYCLE.FAILED &&
                    stage.id === "running" &&
                    reachedStages.has("failed")
                      ? " failed"
                      : ""
                  }`}
                  data-stage={stage.id}
                  data-reached={reachedStages.has(stage.id) ? "true" : "false"}
                >
                  {stage.label}
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        {sufficiency ? (
          <section
            className={`rd-v2-eval-sufficiency rd-v2-eval-sufficiency-${sufficiency.state}`}
            aria-label="Lab coverage"
            data-testid="discover-lab-coverage"
          >
            <div className="rd-v2-eval-sufficiency-copy">
              <p className="rd-v2-eval-section-label">Lab coverage</p>
              <p className="rd-v2-eval-decision-headline">{sufficiency.focusHeadline}</p>
              <p className="rd-v2-eval-decision-body">{sufficiency.focusBody}</p>
            </div>

            {sufficiencyDifferences.length ? (
              <div className="rd-v2-eval-sufficiency-compare" aria-label="Lab coverage comparison">
                {sufficiencyDifferences.map((difference) => (
                  <div
                    key={`${difference.dimension}-${difference.local}-${difference.candidate}`}
                    className="rd-v2-eval-sufficiency-compare-row"
                  >
                    <span className="rd-v2-eval-sufficiency-dimension">
                      {sufficiencyDimensionLabel(difference.dimension)}
                    </span>
                    <span className="rd-v2-eval-sufficiency-side">
                      <small>In lab</small>
                      <strong>{difference.local || "Not described"}</strong>
                    </span>
                    <span className="rd-v2-eval-sufficiency-arrow" aria-hidden="true">
                      →
                    </span>
                    <span className="rd-v2-eval-sufficiency-side">
                      <small>Candidate</small>
                      <strong>{difference.candidate || "Not described"}</strong>
                    </span>
                  </div>
                ))}
              </div>
            ) : null}

            {localDatasetTitle ? (
              <p className="rd-v2-eval-sufficiency-reference">
                <span>Local asset</span>
                <strong>{localDatasetTitle}</strong>
              </p>
            ) : null}
          </section>
        ) : null}

        <div className="rd-v2-rail-scroll rd-v2-eval-scroll">
          <section className="rd-v2-eval-block" aria-label="Useful for">
            <p className="rd-v2-eval-section-label">Useful for</p>
            <p className="rd-v2-eval-prose">{evaluation.usefulFor}</p>
          </section>

          {evaluation.coverage.length ? (
            <section className="rd-v2-eval-block" aria-label="Coverage">
              <p className="rd-v2-eval-section-label">Coverage</p>
              <ul className="rd-v2-eval-list">
                {evaluation.coverage.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ) : (
            <section className="rd-v2-eval-block" aria-label="Coverage">
              <p className="rd-v2-eval-section-label">Coverage</p>
              <p className="rd-v2-eval-prose muted">Coverage not described</p>
            </section>
          )}

          <div className="rd-v2-eval-evidence-grid">
            {evaluation.hasProbe && evaluation.verified.length ? (
              <section className="rd-v2-eval-block rd-v2-eval-verified" aria-label="Verified">
                <p className="rd-v2-eval-section-label">Verified</p>
                <ul className="rd-v2-eval-checklist">
                  {evaluation.verified.map((item) => (
                    <li key={item}>
                      <span className="rd-v2-eval-mark ok" aria-hidden="true">
                        ✓
                      </span>
                      {item}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className="rd-v2-eval-block rd-v2-eval-unknown" aria-label="Still unknown">
              <p className="rd-v2-eval-section-label">Still unknown</p>
              <ul className="rd-v2-eval-checklist">
                {displayUnknowns.map((item) => (
                  <li key={item}>
                    <span className="rd-v2-eval-mark unknown" aria-hidden="true">
                      ?
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {evaluation.inferred.length ? (
            <section className="rd-v2-eval-block rd-v2-eval-inferred" aria-label="Inferred">
              <p className="rd-v2-eval-section-label">Inferred</p>
              <ul className="rd-v2-eval-checklist">
                {evaluation.inferred.map((item) => (
                  <li key={item}>
                    <span className="rd-v2-eval-mark infer" aria-hidden="true">
                      ~
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {evaluation.probeError ? (
            <p className="rd-v2-discover-probe-error">{evaluation.probeError}</p>
          ) : null}

          {evaluation.technical.length || evaluation.modelNotes.length ? (
            <details key={targetKey} className="rd-v2-eval-tech">
              <summary>Technical evidence</summary>
              <div className="rd-v2-eval-tech-body">
                {evaluation.modelNotes.map((note) => (
                  <p key={note.label} className="rd-v2-eval-model-note">
                    <span className="rd-v2-eval-section-label">Model interpretation</span>
                    {note.detail || note.label}
                  </p>
                ))}
                <RailFieldGrid>
                  {evaluation.technical.map((fact) => (
                    <RailField
                      key={`${fact.label}-${fact.detail}`}
                      label={fact.label}
                      value={fact.detail || "—"}
                      mono={/url|etag|connector/i.test(fact.label)}
                    />
                  ))}
                </RailFieldGrid>
              </div>
            </details>
          ) : (
            <details key={targetKey} className="rd-v2-eval-tech">
              <summary>Technical evidence</summary>
              <p className="rd-v2-eval-prose muted">
                No probe evidence yet. Probe the source to collect endpoint facts.
              </p>
            </details>
          )}

          <section className="rd-v2-eval-ask-chips" aria-label="Ask about this source">
            <p className="rd-v2-eval-section-label">Ask about this source</p>
            <div className="rd-v2-chips-row">
              {askPrompts.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  className="rd-v2-chip clickable"
                  onClick={() => askWithSufficiency(chip.prompt)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>

      <div className="rd-v2-eval-actions" data-testid="discover-eval-actions">
        {probeLoading || submitting ? (
          <p className="rd-v2-eval-action-status">{submitting ? "Submitting…" : "Probing source…"}</p>
        ) : null}

        <button
          type="button"
          className="rd-v2-btn primary rd-v2-eval-primary-action"
          disabled={probeLoading || submitting}
          onClick={() => runAction(primary.id)}
        >
          {primary.label}
        </button>

        <div className="rd-v2-eval-actions-wide" aria-label="Additional candidate actions">
          {secondary.map((action) => (
            <button
              key={action.id}
              type="button"
              className="rd-v2-btn"
              disabled={probeLoading || submitting}
              onClick={() => runAction(action.id)}
            >
              {action.label}
            </button>
          ))}
        </div>

        <div className="rd-v2-eval-actions-mobile" aria-label="Additional focused candidate actions">
          {mobileSecondary || mobileOverflowActions.length ? (
            <div className="rd-v2-eval-mobile-secondary-row">
              {mobileSecondary ? (
                <button
                  type="button"
                  className="rd-v2-eval-mobile-secondary"
                  disabled={probeLoading || submitting}
                  onClick={() => runAction(mobileSecondary.id)}
                >
                  {mobileSecondaryLabel}
                </button>
              ) : (
                <span />
              )}

              {mobileOverflowActions.length ? (
                <details className="rd-v2-eval-action-menu">
                  <summary aria-label="More actions">•••</summary>
                  <div className="rd-v2-eval-action-menu-popover">
                    {mobileOverflowActions.map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        disabled={probeLoading || submitting}
                        onClick={(event) => {
                          runAction(action.id);
                          event.currentTarget.closest("details")?.removeAttribute("open");
                        }}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </>
  );

  if (variant === "workspace") return body;

  return (
    <RailFrame>
      {body}
      <RailStickyFooter>
        <span className="rd-v2-muted">Candidate {targetKey}</span>
      </RailStickyFooter>
    </RailFrame>
  );
}
