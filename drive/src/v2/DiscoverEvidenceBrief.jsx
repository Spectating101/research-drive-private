import { useEffect, useMemo, useRef, useState } from "react";
import { assessDiscoverEvidence } from "@/v2/api";
import { DISCOVER_SUGGESTIONS } from "@/v2/deskSeed";
import { handleEnterToRequestSubmit } from "@/v2/enterToSubmit";

const VERDICT_LABELS = {
  covered: "Covered",
  partially_covered: "Partially covered",
  partial: "Partially covered",
  not_covered: "Not covered",
  uncovered: "Not covered",
  // Backward compatibility for the short-lived fourth-verdict contract.
  cannot_assess: "Not yet recorded",
};
const ASSESSMENT_STATUS_LABELS = {
  insufficient_metadata: "Not yet recorded",
  insufficient_requirement: "Needs a brief",
};

function text(value, fallback) {
  if (value == null || value === "") return fallback;
  if (typeof value === "string" || typeof value === "number") return String(value).trim() || fallback;
  if (Array.isArray(value)) {
    const values = value.map((item) => text(item, "")).filter(Boolean);
    return values.join(" · ") || fallback;
  }
  if (typeof value === "object") {
    for (const key of ["value", "statement", "text", "label", "name", "reason"]) {
      if (value[key] != null && value[key] !== value) return text(value[key], fallback);
    }
    const values = Object.values(value)
      .filter((item) => typeof item === "string" || typeof item === "number")
      .map((item) => String(item).trim())
      .filter(Boolean);
    return values.join(" · ") || fallback;
  }
  return fallback;
}

const PROVENANCE = ["explicit", "drafted", "unspecified"];
const DIMENSION_LABELS = {
  unit: "Unit",
  "universe/geography": "Geography / universe",
  time_range: "Time range",
  frequency: "Frequency",
  fields: "Fields",
  event_type: "Event type",
};

function normalizeProvenance(value) {
  const raw = text(value, "").toLowerCase();
  if (raw.includes("explicit") || raw === "question") return "explicit";
  if (raw.includes("draft")) return "drafted";
  return "unspecified";
}

function normalizeRequirement(requirement) {
  const dimensions = Array.isArray(requirement?.dimensions) ? requirement.dimensions : [];
  const source = dimensions.length
    ? dimensions
    : Object.entries(requirement || {}).filter(([key]) => key !== "dimensions").map(([key, value]) =>
        typeof value === "object" && value != null
          ? { key, ...value }
          : { key, value },
      );
  return source.map((dimension, index) => ({
    key: text(dimension?.key, `dimension_${index + 1}`),
    label: text(
      dimension?.label,
      DIMENSION_LABELS[dimension?.key] || text(dimension?.key, "Requirement").replaceAll("_", " "),
    ),
    value: text(dimension?.value, "Unknown"),
    rawValue: dimension?.value,
    provenance: normalizeProvenance(dimension?.provenance),
  }));
}

function serializedDimensionValue(dimension) {
  const value = text(dimension?.value, "");
  if (!value || (value === "Unknown" && dimension?.provenance === "unspecified")) return null;
  if (text(dimension?.rawValue, "") === value) return dimension.rawValue;
  if (dimension?.key === "fields") {
    return value.split(/[,·]/).map((item) => item.trim()).filter(Boolean);
  }
  if (dimension?.key === "time_range") {
    const years = value.match(/\b(?:19|20)\d{2}\b/g) || [];
    if (years.length >= 2) return { start: years[0], end: years[1] };
  }
  return value;
}

function keyedRequirement(dimensions) {
  return (dimensions || []).reduce((requirement, dimension) => {
    requirement[dimension.key] = {
      label: dimension.label,
      value: serializedDimensionValue(dimension),
      provenance: normalizeProvenance(dimension.provenance),
    };
    return requirement;
  }, {});
}

function evidenceStateSummary(state) {
  if (!state || typeof state !== "object" || Array.isArray(state)) return text(state, "Evidence state unknown");
  const parts = [
    text(state.materialization?.status ?? state.materialization, ""),
    text(state.access?.status ?? state.access?.value ?? state.access, ""),
    text(state.coverage?.status ?? state.coverage, ""),
  ]
    .map((item) => item.replaceAll("_", " "))
    .filter(Boolean);
  return [...new Set(parts)].join(" · ") || "Evidence state unknown";
}

function assessmentBasisSummary(basis) {
  if (!basis || typeof basis !== "object" || Array.isArray(basis)) {
    return text(basis, "Assessment basis incomplete");
  }
  const count = Number(basis.catalog_candidates_considered);
  const uncovered = Array.isArray(basis.uncovered_candidate_ids) ? basis.uncovered_candidate_ids : [];
  const parts = [
    Number.isFinite(count) ? `${count} held catalog record${count === 1 ? "" : "s"} considered` : "",
    text(basis.mode, "").replaceAll("_", " "),
    basis.assembly_status === "unknown" ? "assembly compatibility unknown" : "",
    // `cannot_assess` reports which specific candidates never declared coverage,
    // so this is a fixable data gap, not a dead end.
    uncovered.length
      ? `coverage never declared for ${uncovered.length} candidate${uncovered.length === 1 ? "" : "s"}: ${uncovered.slice(0, 5).join(", ")}${uncovered.length > 5 ? "…" : ""}`
      : "",
  ].filter(Boolean);
  return parts.join(" · ") || text(basis, "Assessment basis incomplete");
}

function evidenceCandidate(evidence) {
  return {
    dataset_id: evidence?.dataset_id || "",
    candidate_key: evidence?.dataset_id ? `dataset:${evidence.dataset_id}` : undefined,
    title: text(evidence?.title, "Held evidence record"),
    description: text(evidence?.contribution, "Contribution unknown"),
    limitations: text(evidence?.limitations, "Limitations unknown"),
    evidence_state: evidenceStateSummary(evidence?.evidence_state),
  };
}

function localSuggestions(catalog, question) {
  const terms = String(question || "")
    .toLowerCase()
    .split(/\s+/)
    .filter((term) => term.length > 2);
  const ranked = [...(catalog || [])].sort((left, right) => {
    const score = (row) => {
      const haystack = [row?.name, row?.title, row?.dataset_id, row?.source, row?.coverage]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return terms.reduce((total, term) => total + (haystack.includes(term) ? 1 : 0), 0);
    };
    return score(right) - score(left);
  });
  return ranked.slice(0, 2);
}

/** A compact, authoritative assessment path inside Explore. */
export function DiscoverEvidenceBrief({
  catalog = [],
  onSelectRow,
  onLegacySearch,
  onAssessmentActive,
  onCraftUrl,
  onAssessmentChange,
  onClose,
  initialQuestion = "",
  autoAssess = false,
  variant = "standalone",
}) {
  const [draft, setDraft] = useState(initialQuestion);
  const [assessment, setAssessment] = useState(null);
  const [dimensions, setDimensions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const autoStartedRef = useRef("");

  useEffect(() => {
    setDimensions(normalizeRequirement(assessment?.requirement));
  }, [assessment]);

  useEffect(() => {
    if (initialQuestion) setDraft(initialQuestion);
  }, [initialQuestion]);

  const suggestions = useMemo(() => localSuggestions(catalog, draft), [catalog, draft]);
  const heldEvidence = Array.isArray(assessment?.held_evidence) ? assessment.held_evidence : [];
  const verdictKey = String(assessment?.verdict || "").trim().toLowerCase().replace(/[ -]/g, "_");
  const assessmentStatus = String(assessment?.assessment_status || "").trim().toLowerCase().replace(/[ -]/g, "_");
  const verdictLabel = ASSESSMENT_STATUS_LABELS[assessmentStatus]
    || VERDICT_LABELS[verdictKey]
    || text(assessment?.verdict, "Assessment pending");
  const verdictTone = assessmentStatus || verdictKey || "unknown";

  const requestAssessment = async ({ requirement, questionOverride } = {}) => {
    const question = String(questionOverride || draft).trim();
    if (!question) return;
    setLoading(true);
    setError("");
    try {
      const next = await assessDiscoverEvidence({ question, requirement });
      setAssessment(next);
      onAssessmentChange?.(next);
      onAssessmentActive?.(true);
    } catch (requestError) {
      setError("Assessment is unavailable. Showing the catalogue instead.");
      onAssessmentChange?.(null);
      onAssessmentActive?.(false);
      // Existing catalogue search is retained only as a graceful fallback.
      onLegacySearch?.(question);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const question = String(initialQuestion || "").trim();
    if (!autoAssess || !question || autoStartedRef.current === question) return;
    autoStartedRef.current = question;
    requestAssessment({ questionOverride: question });
    // One deliberate assessment per mounted query. Reassessment is explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAssess, initialQuestion]);

  const updateDimension = (index, field, value) => {
    setDimensions((current) => current.map((item, itemIndex) =>
      itemIndex === index ? { ...item, [field]: value } : item,
    ));
  };

  const requirementEditor = (
    <section className="rd-v2-evidence-requirement" aria-label="Editable evidence brief">
      <div className="rd-v2-evidence-section-head">
        <div><span className="rd-v2-eyebrow">Evidence brief</span><p>Edit only what the assessment should use on its next pass.</p></div>
        <button type="button" className="rd-v2-btn sm" disabled={loading} onClick={() => requestAssessment({ requirement: keyedRequirement(dimensions) })}>
          Apply & reassess
        </button>
      </div>
      {dimensions.length ? dimensions.map((dimension, index) => (
        <div className="rd-v2-evidence-dimension" key={dimension.key}>
          <label>{dimension.label}<input aria-label={`${dimension.label} value`} value={dimension.value} onChange={(event) => updateDimension(index, "value", event.target.value)} /></label>
          <label>Basis<select aria-label={`${dimension.label} provenance`} value={dimension.provenance} onChange={(event) => updateDimension(index, "provenance", event.target.value)}>{PROVENANCE.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        </div>
      )) : <p className="muted">Requirement dimensions were not supplied.</p>}
    </section>
  );

  return (
    <section className={`rd-v2-evidence-brief ${variant === "layered" ? "is-layered" : ""}`} aria-label="Evidence assessment" data-testid="discover-evidence-brief">
      {variant !== "layered" ? <form
        className={`rd-v2-evidence-question${assessment ? " is-assessed" : ""}`}
        onSubmit={(event) => {
          event.preventDefault();
          requestAssessment();
        }}
      >
        <label className="rd-v2-eyebrow" htmlFor="discover-assessment-question">Explore question</label>
        <div className="rd-v2-evidence-question-row">
          <textarea
            id="discover-assessment-question"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleEnterToRequestSubmit}
            rows={1}
            placeholder="State the evidence you need…"
            aria-label="Explore question"
          />
          <button type="submit" className="rd-v2-btn sm primary" disabled={!draft.trim() || loading}>
            {loading ? "Assessing…" : "Assess evidence"}
          </button>
        </div>
        <p className="rd-v2-ask-send-hint">Enter to assess · ⇧↵ newline</p>
      </form> : null}

      {!assessment ? (
        variant === "layered" ? null : <div className="rd-v2-evidence-suggestions" data-testid="discover-empty">
          <span className="rd-v2-eyebrow">Held locally</span>
          <h2>What evidence are you looking for?</h2>
          <p data-testid="discover-evidence-suggestions">Local context only while you type. An assessment runs when you submit.</p>
          {suggestions.length ? (
            <div className="rd-v2-evidence-suggestion-list">
              {suggestions.map((row) => (
                <button key={row.dataset_id || row.name} type="button" onClick={() => onSelectRow?.(row)}>
                  <strong>{text(row.name || row.title || row.dataset_id, "Local dataset")}</strong>
                  <span>{text(row.coverage || row.grain || row.source, "Metadata incomplete")}</span>
                </button>
              ))}
            </div>
          ) : <p className="muted">No local metadata is available yet.</p>}
          {DISCOVER_SUGGESTIONS.length ? (
            <div className="rd-v2-evidence-starters" aria-label="Suggested evidence needs">
              {DISCOVER_SUGGESTIONS.slice(0, 5).map((suggestion) => (
                <button key={suggestion} type="button" onClick={() => setDraft(suggestion)}>{suggestion}</button>
              ))}
            </div>
          ) : null}
          {onCraftUrl ? (
            <form
              className="rd-v2-evidence-intake"
              data-testid="discover-craft-form"
              onSubmit={(event) => {
                event.preventDefault();
                const target = String(event.currentTarget.elements.sourceTarget?.value || "").trim();
                if (target) onCraftUrl(target);
              }}
            >
              <label htmlFor="discover-source-target">Have a URL or DOI?</label>
              <input
                id="discover-source-target"
                name="sourceTarget"
                type="text"
                inputMode="url"
                data-testid="discover-craft-url"
                placeholder="Paste a public URL or DOI"
                aria-label="Public URL or DOI"
              />
              <button type="submit">Inspect →</button>
            </form>
          ) : null}
        </div>
      ) : (
        <div className="rd-v2-evidence-assessment" data-testid="discover-assessment-result">
          <header className="rd-v2-evidence-assessment-head">
            <div>
              <span className="rd-v2-eyebrow">Held-evidence assessment</span>
              <h2>{text(assessment.question, draft)}</h2>
            </div>
            <span className={`rd-v2-evidence-verdict ${verdictTone}`} data-testid="discover-verdict">
              {verdictLabel}
            </span>
            {onClose ? <button type="button" className="rd-v2-evidence-close" onClick={onClose}>Hide assessment</button> : null}
          </header>
          <p className="rd-v2-evidence-because">{text(assessment.because, "Reasoning was not provided.")}</p>

          {variant === "layered" ? (
            <details className="rd-v2-evidence-edit">
              <summary>
                <span>{dimensions.filter((item) => item.value !== "Unknown").map((item) => `${item.label}: ${item.value}`).slice(0, 3).join(" · ") || "Requirement not yet specified"}</span>
                <b>Edit brief</b>
              </summary>
              {requirementEditor}
            </details>
          ) : requirementEditor}

          {variant !== "layered" ? <section className="rd-v2-evidence-held" aria-label="Held evidence">
            <div className="rd-v2-evidence-section-head"><div><span className="rd-v2-eyebrow">Held evidence</span><p>Select a record for existing Detail or Ask.</p></div></div>
            {heldEvidence.length ? (
              <ul data-testid="discover-held-evidence">
                {heldEvidence.map((evidence, index) => {
                  const candidate = evidenceCandidate(evidence);
                  return <li key={candidate.dataset_id || `${candidate.title}-${index}`}><button type="button" onClick={() => onSelectRow?.(candidate)}>
                    <strong>{candidate.title}</strong>
                    <span>{candidate.description}</span>
                    <em>{candidate.evidence_state} · {candidate.limitations}</em>
                  </button></li>;
                })}
              </ul>
            ) : <p className="muted">No held evidence was returned. This does not establish that no evidence exists.</p>}
          </section> : null}

          <section className="rd-v2-evidence-gap" aria-label="Evidence gap" data-testid="discover-evidence-gap">
            <span className="rd-v2-eyebrow">One precise gap</span>
            {assessment.gap ? <>
              <strong>{text(assessment.gap.statement, "Gap statement unavailable")}</strong>
              <p>{text(assessment.gap.blocks, "What this blocks is unknown.")}</p>
              <p className="muted">Resolve with: {text(assessment.gap.resolution_evidence, "Evidence to resolve this is unknown.")}</p>
            </> : <p className="muted">No remaining gap was reported.</p>}
          </section>
          {assessment.assessment_basis ? <p className="rd-v2-evidence-basis">Basis: {assessmentBasisSummary(assessment.assessment_basis)}</p> : null}
        </div>
      )}
      {loading ? <p className="rd-v2-browse-loading" data-testid="discover-assessment-loading">Checking held evidence against the brief…</p> : null}
      {error ? <p className="rd-v2-discover-error" role="status">{error}</p> : null}
    </section>
  );
}
