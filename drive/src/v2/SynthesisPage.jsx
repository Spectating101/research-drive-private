import { useCallback, useEffect, useMemo, useState } from "react";
import { getSynthesisProfile, listSynthesisProfiles } from "@/v2/api";
import { Chip, ChipRow, PageShell } from "@/v2/ui";

const FEATURED_ID = "stablecoin_trust_engagement";

function profileTitle(row) {
  return row?.title || row?.id || "Synthesis profile";
}

function sourceCount(row) {
  const candidates = [
    row?.sources,
    row?.source_ids,
    row?.required_sources,
    row?.inputs,
    row?.datasets,
  ];
  for (const value of candidates) {
    if (Array.isArray(value)) return value.length;
  }
  return null;
}

function profileSources(row) {
  const candidates = [
    row?.sources,
    row?.source_ids,
    row?.required_sources,
    row?.inputs,
    row?.datasets,
  ];
  const value = candidates.find((candidate) => Array.isArray(candidate));
  return (value || []).map((source) =>
    typeof source === "string"
      ? source
      : source?.title || source?.name || source?.dataset_id || source?.id,
  ).filter(Boolean);
}

function profileJoinKeys(row) {
  const keys = row?.join_keys || row?.keys || row?.entity_fields || [];
  return Array.isArray(keys) ? keys.filter(Boolean) : [];
}

function latestDate(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

export function SynthesisPage({ onAskComposer, onToast }) {
  const [catalog, setCatalog] = useState(null);
  const [selectedId, setSelectedId] = useState(FEATURED_ID);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const profiles = catalog?.profiles || [];
  const latest = catalog?.latest || {};

  const loadCatalog = useCallback(async () => {
    try {
      const out = await listSynthesisProfiles();
      setCatalog(out);
      setError("");
    } catch (err) {
      setError(err.message || String(err));
    }
  }, []);

  const loadDetail = useCallback(async (profileId, { refresh = false } = {}) => {
    if (!profileId) return;
    setBusy(true);
    try {
      const out = await getSynthesisProfile(profileId, { refresh });
      setDetail(out);
      setError("");
      if (refresh) onToast?.(`Synthesis run finished · ${profileId}`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [onToast]);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const featured = useMemo(
    () => profiles.find((p) => p.id === FEATURED_ID) || profiles.find((p) => !latest[p.id]) || profiles[0] || null,
    [profiles, latest],
  );
  const selectedProfile = useMemo(
    () => profiles.find((p) => p.id === selectedId) || null,
    [profiles, selectedId],
  );

  const gaps = detail?.manifest?.gaps || detail?.gaps || [];
  const gapRows = Array.isArray(gaps) ? gaps : gaps?.rows || [];
  const summary = detail?.summary || latest[selectedId]?.summary || {};
  const previewRows = detail?.preview_rows || detail?.manifest?.preview_rows || [];
  const builtPanels = profiles.filter((row) => latest[row.id]);
  const otherRecipes = profiles.filter((row) => row.id !== featured?.id);
  const selectedSourceCount = sourceCount(selectedProfile);
  const selectedSources = profileSources(selectedProfile);
  const selectedJoinKeys = profileJoinKeys(selectedProfile);
  const featuredBuilt = featured ? Boolean(latest[featured.id]) : false;
  const gapCount = detail?.gap_count ?? gapRows.length ?? 0;

  const askAboutGaps = (profileId = selectedId) => {
    const sample = gapRows.slice(0, 5).map((g) => g.entity_id || g.id || g.label).filter(Boolean);
    onAskComposer?.(
      `Review synthesis profile ${profileId}. Gap count: ${gapRows.length}. Sample gaps: ${sample.join(", ") || "none"}. Which sources should we procure next to close the biggest holes?`,
    );
  };

  const selectAndMaybeRun = (profileId, refresh = false) => {
    setSelectedId(profileId);
    if (refresh) loadDetail(profileId, { refresh: true });
  };

  return (
    <PageShell
      className="rd-v2-synthesis-page"
      title="Synthesis"
      lead="Answer a research question by joining several Lab holdings into one panel."
      footer="Built panels land in data_lake/synthesis/ — open them from Ask or Library after a run."
    >
      {error ? <p className="rd-v2-error-banner">{error}</p> : null}

      <section
        className="rd-v2-synthesis-flow"
        aria-label="How synthesis works"
        data-testid="synthesis-flow"
      >
        <ol>
          <li>
            <span className="rd-v2-synthesis-step">1</span>
            <strong>Inputs</strong>
            <span>
              {selectedSources.length
                ? selectedSources.join(" · ")
                : "Pick a question, then select registered evidence"}
            </span>
          </li>
          <li>
            <span className="rd-v2-synthesis-step">2</span>
            <strong>Join / transform</strong>
            <span>
              {selectedJoinKeys.length
                ? selectedJoinKeys.join(" + ")
                : `${selectedSourceCount ?? "—"} registered sources`}
            </span>
          </li>
          <li>
            <span className="rd-v2-synthesis-step">3</span>
            <strong>Coverage check</strong>
            <span>
              {summary.entity_count != null ? `${summary.entity_count} entities` : "Entity coverage pending"}
              {" · "}
              {gapCount > 0 ? `${gapCount} gaps` : "No reported gaps"}
            </span>
          </li>
          <li>
            <span className="rd-v2-synthesis-step">4</span>
            <strong>Registered output</strong>
            <span>
              {latest[selectedId]?.generated_at
                ? `Reusable panel · built ${latestDate(latest[selectedId].generated_at)}`
                : "Build, preview and save to the lab"}
            </span>
          </li>
        </ol>
      </section>

      <section className="rd-v2-synthesis-built" aria-label="Built research panels">
        <div className="rd-v2-synthesis-built-head">
          <h2>Already built</h2>
          <span>{builtPanels.length} panel{builtPanels.length === 1 ? "" : "s"}</span>
        </div>
        {builtPanels.length ? (
          <div className="rd-v2-synthesis-built-list">
            {builtPanels.slice(0, 4).map((row) => {
              const hit = latest[row.id];
              return (
                <button
                  key={row.id}
                  type="button"
                  className={`rd-v2-synthesis-built-row${row.id === selectedId ? " on" : ""}`}
                  onClick={() => setSelectedId(row.id)}
                >
                  <strong>{profileTitle(row)}</strong>
                  <span>{latestDate(hit?.generated_at) || "built"}</span>
                  <em>
                    {hit?.summary?.entity_count != null
                      ? `${hit.summary.entity_count} entities`
                      : row.type || row.id}
                  </em>
                </button>
              );
            })}
          </div>
        ) : (
          <p className="muted small">Nothing built yet. Start with the question below.</p>
        )}
      </section>

      {featured ? (
        <section
          className="rd-v2-home-synthesis"
          aria-label={featuredBuilt ? "Featured built panel" : "Answer next"}
        >
          <div>
            <span className="rd-v2-pill">{featuredBuilt ? "Built · refresh anytime" : "Answer next"}</span>
            <h2>{profileTitle(featured)}</h2>
            <p>
              {featured.description ||
                "Build this panel when the question needs several source layers already in the vault."}
            </p>
            {featured.research_questions?.length ? (
              <>
                <p className="rd-v2-synthesis-q-label">Questions this panel can support</p>
                <ul className="rd-v2-synthesis-questions">
                  {featured.research_questions.slice(0, 3).map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
          <div className="rd-v2-synthesis-card-actions">
            <button
              type="button"
              className="rd-v2-btn sm primary"
              disabled={busy}
              onClick={() => selectAndMaybeRun(featured.id, true)}
            >
              {busy && selectedId === featured.id
                ? "Running…"
                : featuredBuilt
                  ? "Refresh panel"
                  : "Build panel"}
            </button>
            <button
              type="button"
              className="rd-v2-btn sm"
              disabled={busy}
              onClick={() => {
                setSelectedId(featured.id);
                askAboutGaps(featured.id);
              }}
            >
              Ask about gaps →
            </button>
          </div>
        </section>
      ) : null}

      {otherRecipes.length ? (
        <section className="rd-v2-synthesis-other" aria-label="Other recipes">
          <div className="rd-v2-synthesis-built-head">
            <h2>Other recipes</h2>
            <button type="button" className="rd-v2-linkish" onClick={loadCatalog}>
              Refresh
            </button>
          </div>
          <div className="rd-v2-synthesis-list">
            {otherRecipes.map((row) => {
              const hit = latest[row.id];
              const active = row.id === selectedId;
              return (
                <article key={row.id} className={`rd-v2-synthesis-card${active ? " active" : ""}`}>
                  <button
                    type="button"
                    className="rd-v2-synthesis-card-main rd-v2-synthesis-card-hit"
                    onClick={() => setSelectedId(row.id)}
                  >
                    <strong>{profileTitle(row)}</strong>
                    <span className="muted small">
                      {[row.type || row.id, sourceCount(row) != null ? `${sourceCount(row)} sources` : ""]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                    {hit?.generated_at ? (
                      <span className="muted small">Built {latestDate(hit.generated_at)}</span>
                    ) : (
                      <span className="muted small">Not built yet</span>
                    )}
                  </button>
                  <div className="rd-v2-synthesis-card-actions">
                    <button
                      type="button"
                      className="rd-v2-btn sm"
                      disabled={busy}
                      onClick={() => selectAndMaybeRun(row.id, true)}
                    >
                      {hit ? "Refresh" : "Run"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {selectedId && detail ? (
        <section className="rd-v2-cluster-synthesis" aria-label="Synthesis detail">
          <div className="rd-v2-synthesis-built-head">
            <h2>{profileTitle(selectedProfile)} — latest output</h2>
          </div>
          <ChipRow>
            {selectedSourceCount != null ? <Chip>sources {selectedSourceCount}</Chip> : null}
            {summary.entity_count != null ? <Chip>entities {summary.entity_count}</Chip> : null}
            {detail.gap_count != null ? <Chip warn={detail.gap_count > 0}>gaps {detail.gap_count}</Chip> : null}
            {detail.generated_at ? <Chip>built {String(detail.generated_at).slice(0, 19)}</Chip> : null}
          </ChipRow>

          {previewRows.length ? (
            <>
              <h3 className="rd-v2-subhead">Sample rows</h3>
              <ul className="rd-v2-ask-artifacts compact">
                {previewRows.slice(0, 6).map((row, idx) => (
                  <li key={idx} className="rd-v2-ask-artifact-row mono small">
                    {typeof row === "object"
                      ? Object.entries(row)
                          .slice(0, 5)
                          .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                          .join(" · ")
                      : String(row)}
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          {gapRows.length ? (
            <>
              <h3 className="rd-v2-subhead">Coverage gaps to procure next</h3>
              <ul className="rd-v2-ask-artifacts">
                {gapRows.slice(0, 8).map((g, idx) => (
                  <li key={g.entity_id || g.id || idx} className="rd-v2-ask-artifact-row">
                    <strong>{g.entity_id || g.label || g.id || "gap"}</strong>
                    <span className="muted small">{g.missing_source || g.reason || g.kind || "missing source"}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted small">No missing coverage reported. Refresh after new vault material lands.</p>
          )}
        </section>
      ) : null}
    </PageShell>
  );
}
