import { useRef, useState } from "react";
import { buildDiscoverEvaluation } from "@/v2/discoverEvaluation";
import { LIFECYCLE } from "@/v2/discoverLifecycle";
import { displayName } from "@/v2/datasetMeta";
import { EmptyRailState } from "@/v2/EmptyRailState";
import {
  RailDecisionSummary,
  RailEntityHeader,
  RailField,
  RailFieldGrid,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";
import { DetailPanel } from "@/v2/DetailPanel";

function fmtGiB(gib) {
  if (gib == null) return "—";
  return `${gib} GiB`;
}

function shortRailText(value, max = 72) {
  const text = String(value || "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function cleanRailTarget(target) {
  const text = String(target || "");
  return text.startsWith("[context:") && text.includes("]") ? text.split("]").slice(1).join("]").trim() : text;
}

function resourceRailName(row) {
  if (row.key === "vault") return "Drive vault";
  if (row.key === "nvme") return "Working disk";
  if (row.key === "bulk-cache") return "Bulk cache";
  if (row.key === "staging-disk") return "Staging space";
  if (row.key === "tavily") return "Web discovery";
  if (row.key === "huggingface") return "Hugging Face";
  if (row.key === "collect-tokens") return "Collector accounts";
  if (row.key === "source-gdelt") return "GDELT news/events";
  if (row.key === "source-market-filings") return "Market & filings";
  if (row.key === "source-research-catalogs") return "Catalog APIs";
  if (row.key === "route-discovery-intake") return "Discovery & intake";
  if (row.key === "source-public-web") return "Open web";
  if (row.key === "source-remote-tables") return "Remote tables";
  if (row.key === "source-twse") return "TWSE";
  if (row.key === "source-bigquery") return "BigQuery";
  if (row.key === "source-web_generic") return "Public web";
  return row.label?.split("·")[0].trim() || row.key || "Resource";
}

function resourceRailDescription(row) {
  if (row.group) return "Source route group";
  if (row.kind === "source") return "Source route";
  if (row.kind === "metered") return "Account limit";
  if (row.kind === "usage") return "Storage";
  return row.section || row.kind || "Resource";
}

function resourceRailUse(row) {
  if (row.key === "vault") return "Long-term archive";
  if (row.key === "nvme") return "Local working space";
  if (row.key === "bulk-cache") return "Large downloads";
  if (row.key === "staging-disk") return "Before archiving";
  if (row.key === "bigquery") return "Remote table queries";
  if (row.key === "tavily") return "Web search";
  if (row.key === "huggingface") return "Dataset discovery";
  if (row.key === "collect-tokens") return "External account access";
  if (row.key === "source-gdelt") return "News and event data";
  if (row.key === "source-market-filings") return "Official market data and filings";
  if (row.key === "source-research-catalogs") return "Academic metadata and dataset APIs";
  if (row.key === "route-discovery-intake") return "Candidate discovery and URL classification";
  if (row.key === "source-public-web") return "Probe and browser collect";
  if (row.key === "source-remote-tables") return "Dry-run protected remote query";
  if (row.key === "source-sec_edgar") return "Company filings";
  if (row.key === "source-twse") return "Taiwan market data";
  if (row.key === "source-mops") return "Taiwan company filings";
  if (row.key === "source-coingecko") return "Crypto market data";
  if (row.key === "source-bigquery") return "Remote tables";
  if (row.key === "source-datacite") return "Research datasets";
  if (row.key === "source-huggingface") return "Community datasets";
  if (row.key === "source-web_generic") return "Any public URL";
  return row.detail || row.sublabel || row.section || "—";
}

function resourceRailAccess(row) {
  if (row.key === "source-gdelt") return "Queue to collect";
  if (row.key === "source-market-filings") return "Official feeds and queue scripts";
  if (row.key === "source-research-catalogs") return "DOI lookup and dataset import";
  if (row.key === "route-discovery-intake") return "Search and probe before collect";
  if (row.key === "source-public-web") return "Probe, then collect";
  if (row.key === "source-remote-tables") return "Query with dry-run limit";
  if (row.key === "source-sec_edgar") return "Download queue";
  if (row.key === "source-twse") return "Download queue";
  if (row.key === "source-mops") return "Browser collector";
  if (row.key === "source-coingecko") return "API fetch";
  if (row.key === "source-bigquery") return "Remote query";
  if (row.key === "source-datacite") return "DOI lookup";
  if (row.key === "source-huggingface") return "Dataset import";
  if (row.key === "source-web_generic") return "Probe, then collect";
  return row.collect_via || row.routes || row.metric || "Available";
}

function resourceRailLimit(row) {
  if (row.key === "bigquery") {
    const cap = String(row.metric || "").match(/(\d+) GiB\/query cap/)?.[1];
    return cap ? `${cap} GiB cap per query` : "Dry-run protected";
  }
  if (row.key === "tavily") {
    const raw = String(row.metric || "");
    const keys = raw.match(/(\d+) keys/)?.[1];
    const cap = raw.match(/(\d+)\/procure cap/)?.[1];
    const today = raw.match(/(\d+) today/)?.[1];
    return [
      keys ? `${keys} keys ready` : null,
      cap ? `${cap} per request` : null,
      today ? `${today} today` : null,
    ]
      .filter(Boolean)
      .join(" · ") || "Search access";
  }
  if (row.key === "huggingface") return row.metric === "token configured" ? "Token ready" : "Public access";
  if (row.key === "collect-tokens") {
    const profiles = String(row.metric || "").match(/(\d+)\/(\d+) profiles/);
    if (profiles) return `${profiles[1]} of ${profiles[2]} accounts ready`;
  }
  return row.metric || "—";
}

function resourceRailStatus(row) {
  if (row.warn) return "Needs attention";
  if (row.ok === false) return "Offline";
  return "Healthy";
}

const RAIL_ACTION_LABELS = {
  ask: "Ask",
  discover: "Browse",
  query: "Query",
  job_submit: "Job",
  job_approve: "Approved",
  approve_collect: "Collect",
  bq_dry_run: "BQ dry-run",
  bq_read: "BQ read",
};

const PAGE_RAIL_COPY = {
  home: {
    title: "Research Drive",
    desc: "Start from the lab vault, missing-data search, or resource safety checks.",
    fields: [
      ["Use this page", "See what needs attention now"],
      ["Primary move", "Open Library or Discover"],
      ["When blocked", "Check Resources for approvals, limits, or credentials"],
    ],
  },
  library: {
    title: "Library guide",
    desc: "The lab’s working data vault: folders, registered datasets, query readiness, and procurement memory.",
    fields: [
      ["Use this page", "Find data the lab already has"],
      ["Primary move", "Select a dataset or branch"],
      ["When missing", "Add URL / DOI or procure missing data"],
      ["Trust cue", "Rows should show readiness, source, and destination"],
    ],
  },
  profile: {
    title: "Profile context",
    desc: "Faculty profile controls ranking, procurement hints, and research-area context.",
    fields: [
      ["Used for", "Discover ranking"],
      ["Also affects", "Procurement chat"],
      ["Next", "Update email in Settings"],
    ],
  },
  settings: {
    title: "Desk setup",
    desc: "Credentials and display preferences for the research drive.",
    fields: [
      ["Account", "Faculty email"],
      ["Credentials", "BQ, GDrive, DataCite"],
      ["Display", "Default tab and rail mode"],
    ],
  },
};

function pluralCount(value, singular, plural = `${singular}s`) {
  const count = Number(value || 0);
  return `${count} ${count === 1 ? singular : plural}`;
}

function LibraryIntakeRailPanel({ object, onSubmitUpload, onSubmitUrl, onSubmitProcure }) {
  const inputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [target, setTarget] = useState("");
  const names = files.map((file) => file.name).filter(Boolean);
  const mode = object?.mode || "upload";
  const destination = object?.destination || "Lab root";

  const chooseFiles = () => inputRef.current?.click();
  const setPickedFiles = (picked) => setFiles(Array.from(picked || []));

  if (mode === "url") {
    return (
      <RailFrame>
        <RailEntityHeader
          id={object.id}
          title="Add URL / DOI"
          description="Probe a public source, collect metadata, and hand the acquisition plan to Ask."
          pills={<span className="rd-v2-pill ext">Intake</span>}
        />
        <div className="rd-v2-rail-scroll">
          <RailFieldGrid>
            <RailField label="Destination" value={destination} />
            <RailField label="Path" value={object.path} />
          </RailFieldGrid>
          <div className="rd-v2-rail-intake">
            <label htmlFor="rd-v2-rail-url-input">URLs or DOIs</label>
            <textarea
              id="rd-v2-rail-url-input"
              rows={7}
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              placeholder="https://doi.org/10.1234/example&#10;https://data.example.org/dataset"
            />
          </div>
        </div>
        <RailStickyFooter>
          <button
            type="button"
            className="rd-v2-btn sm primary"
            disabled={!target.trim()}
            onClick={() => onSubmitUrl?.(target.trim(), object)}
          >
            Send to Ask
          </button>
        </RailStickyFooter>
      </RailFrame>
    );
  }

  if (mode === "procure") {
    return (
      <RailFrame>
        <RailEntityHeader
          id={object.id}
          title="Procure branch"
          description="Use the current Library branch as the destination and ask the desk to search, probe, and propose acquisition steps."
          pills={<span className="rd-v2-pill ext">Procure</span>}
        />
        <div className="rd-v2-rail-scroll">
          <RailFieldGrid>
            <RailField label="Destination" value={destination} />
            <RailField label="Path" value={object.path} />
            <RailField label="Known data" value={pluralCount(object.counts?.datasets, "dataset")} />
            <RailField label="Query-ready" value={String(object.counts?.queryReady ?? 0)} />
          </RailFieldGrid>
        </div>
        <RailStickyFooter>
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onSubmitProcure?.(object)}>
            Ask to procure
          </button>
        </RailStickyFooter>
      </RailFrame>
    );
  }

  return (
    <RailFrame>
      <RailEntityHeader
        id={object.id}
        title="Upload files"
        description="Stage local files against the current Library branch and hand ingestion to the vault via Ask."
        pills={<span className="rd-v2-pill lab">Upload</span>}
      />
      <div className="rd-v2-rail-scroll">
        <RailFieldGrid>
          <RailField label="Destination" value={destination} />
          <RailField label="Path" value={object.path} />
        </RailFieldGrid>
        <div
          className="rd-v2-rail-upload-zone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            setPickedFiles(event.dataTransfer?.files);
          }}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            aria-label="Choose files to upload"
            onChange={(event) => setPickedFiles(event.target.files)}
          />
          <strong>Drop files here</strong>
          <p>or choose files from disk for vault ingestion.</p>
          <button type="button" className="rd-v2-btn sm" onClick={chooseFiles}>
            Choose files
          </button>
        </div>
        <div className="rd-v2-rail-file-list" aria-label="Selected files">
          {names.length ? names.map((name) => <span key={name}>{name}</span>) : <p>No files selected yet.</p>}
        </div>
      </div>
      <RailStickyFooter>
        <button
          type="button"
          className="rd-v2-btn sm primary"
          disabled={!files.length}
          onClick={() => onSubmitUpload?.(files, object)}
        >
          Send to Ask
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function LibraryObjectRailPanel({
  object,
  onAskAbout,
  onStartUpload,
  onStartUrl,
  onStartProcure,
  onSubmitUpload,
  onSubmitUrl,
  onSubmitProcure,
}) {
  if (object?.kind === "library_intake") {
    return (
      <LibraryIntakeRailPanel
        object={object}
        onSubmitUpload={onSubmitUpload}
        onSubmitUrl={onSubmitUrl}
        onSubmitProcure={onSubmitProcure}
      />
    );
  }

  const folder = object?.kind === "library_folder" ? object : null;
  if (!folder) return null;
  const counts = folder.counts || {};
  const desc = folder.note || "Current vault branch and acquisition destination.";

  return (
    <RailFrame>
      <RailEntityHeader
        id={folder.path || folder.id}
        title={folder.title}
        description={desc}
        pills={<span className="rd-v2-pill lab">{folder.folderId ? "Folder" : "Lab root"}</span>}
      />
      <RailDecisionSummary
        status={
          counts.datasets > 0
            ? `${counts.datasets} dataset${counts.datasets === 1 ? "" : "s"} registered`
            : "No datasets in this branch"
        }
        primary={
          counts.queryReady > 0
            ? "Use now — query-ready data available"
            : "Add or procure data before analysis"
        }
        risk={counts.queryReady === 0 ? "No query-ready holdings here" : "Low"}
        next={
          counts.datasets > 0
            ? "Select a dataset, preview rows, or ask about coverage"
            : "Upload files, add URL / DOI, or procure missing data"
        }
      />
      <div className="rd-v2-rail-scroll">
        <RailFieldGrid>
          <RailField label="Destination" value={folder.destination} />
          <RailField label="Folders" value={pluralCount(counts.folders, "folder")} />
          <RailField label="Datasets" value={pluralCount(counts.datasets, "dataset")} />
          <RailField label="Query-ready" value={String(counts.queryReady ?? 0)} />
          <RailField label="Items" value={pluralCount(counts.items, "item")} />
        </RailFieldGrid>
        <p className="rd-v2-rail-section-label">Branch actions</p>
        <div className="rd-v2-rail-branch-actions">
          <button type="button" onClick={() => onStartUpload?.(folder)}>
            Upload files
          </button>
          <button type="button" onClick={() => onStartUrl?.(folder)}>
            Add URL / DOI
          </button>
          <button type="button" onClick={() => onStartProcure?.(folder)}>
            Procure missing data
          </button>
        </div>
      </div>
      <RailStickyFooter>
        <button type="button" className="rd-v2-btn sm primary" onClick={() => onStartUpload?.(folder)}>
          Upload here
        </button>
        <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(folder)}>
          Ask about branch →
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function PageRailPanel({ page = "home", onAskAbout }) {
  const copy = PAGE_RAIL_COPY[page] || PAGE_RAIL_COPY.home;
  return (
    <RailFrame>
      <RailEntityHeader id={page} title={copy.title} description={copy.desc} />
      <div className="rd-v2-rail-scroll">
        <RailFieldGrid>
          {copy.fields.map(([label, value]) => (
            <RailField key={label} label={label} value={value} />
          ))}
        </RailFieldGrid>
      </div>
      <RailStickyFooter>
        <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.()}>
          Ask about this page →
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function HomeAttentionRailPanel({ object, onAskAbout }) {
  const row = object?.row || {};
  return (
    <RailFrame>
      <RailEntityHeader
        id={row.id || object?.id || "home-attention"}
        title={row.title || object?.title || "Home attention"}
        description={row.detail || "Selected work from the Home attention queue."}
        pills={row.metric ? <span className={`rd-v2-pill${row.warn ? " warn" : ""}`}>{row.metric}</span> : null}
      />
      <div className="rd-v2-rail-scroll">
        <RailFieldGrid>
          <RailField label="Type" value={row.label || row.kind || object?.kind} />
          <RailField label="Next" value={row.next || "Review"} />
          <RailField label="Surface" value={row.tab === "browse" ? "Discover" : row.tab || "home"} />
          {row.resourceRow?.job?.id ? <RailField label="Job ID" value={row.resourceRow.job.id} mono /> : null}
        </RailFieldGrid>
      </div>
      <RailStickyFooter>
        <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(object)}>
          Ask about this →
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function ClusterRailPanel({ compare, onAskAbout }) {
  if (!compare?.a || !compare?.b) {
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState
            title="No compare selected"
            hint="Pick two datasets in Cluster to inspect join-key overlap."
          />
        </div>
      </RailFrame>
    );
  }

  const titleA = displayName(compare.a);
  const titleB = displayName(compare.b);
  const overlapText = compare.shared?.length
    ? `${compare.shared.join(" · ")}${compare.grainMatch ? " · matching grain" : ""}`
    : "Unknown overlap — no shared join keys";

  return (
    <RailFrame>
      <RailEntityHeader
        id={`${compare.a.dataset_id} × ${compare.b.dataset_id}`}
        title="Overlap"
        description={`${titleA} compared with ${titleB}`}
        pills={
          compare.pct != null ? (
            <span className={`rd-v2-pill${compare.pct >= 50 ? "" : compare.pct > 0 ? " warn" : " muted"}`}>
              {compare.pct}% key overlap
            </span>
          ) : null
        }
      />
      <div className="rd-v2-rail-scroll">
        <RailFieldGrid>
          <RailField label="Overlap" value={overlapText} />
          <RailField label="Shared keys" value={(compare.shared || []).join(" · ") || "—"} />
          <RailField
            label="Only A"
            value={(compare.onlyA || []).slice(0, 5).join(" · ") || "—"}
          />
          <RailField
            label="Only B"
            value={(compare.onlyB || []).slice(0, 5).join(" · ") || "—"}
          />
          {compare.join ? <RailField label="Join on" value={compare.join} mono /> : null}
        </RailFieldGrid>
      </div>
      <RailStickyFooter>
        <button type="button" className="rd-v2-btn sm" onClick={onAskAbout}>
          Ask about overlap →
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function BrowseRailPanel({
  target,
  labIds,
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
}) {
  if (!target) {
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

  const evaluation = buildDiscoverEvaluation(target, labIds, probeState);
  const probeLoading = evaluation.probeLoading;
  const submitting = lifecycle?.state === LIFECYCLE.SUBMITTING;
  const targetKey = target?.candidate_key || target?.dataset_id || target?.url || evaluation.title;

  const askPrompts = lifecycle
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
          id: "compare",
          label: "Compare with lab holdings",
          prompt: `Compare ${evaluation.title} with my current lab holdings. Note overlaps and gaps without inventing coverage.`,
        },
        {
          id: "probe_next",
          label: "What should I probe next?",
          prompt: `Given ${evaluation.title}, what should I probe next, and what would still remain unknown after a successful probe?`,
        },
      ];

  const primary = lifecycle?.primaryAction || evaluation.actions.primary;
  const secondary = lifecycle ? lifecycle.secondaryActions || [] : evaluation.actions.secondary;

  const runAction = (id) => {
    if (id === "open_library" || id === "inspect_record") {
      const datasetId = lifecycle?.registeredDatasetId || target?.dataset_id;
      onOpenInLibrary?.(datasetId ? { ...target, dataset_id: datasetId } : target);
    } else if (id === "add_lab") onAddToLab?.(target);
    else if (id === "probe") onProbeSource?.(target);
    else if (id === "preview") onPreviewExternal?.();
    else if (id === "review_approval") onReviewApproval?.(lifecycle?.job || target);
    else if (id === "track_resources") onTrackResources?.(lifecycle?.job || target);
    else if (id === "ask" || id === "review_access") onAskAbout?.(target);
  };

  const pathStages = [
    { id: "submitted", label: "Submitted" },
    { id: "approval", label: "Approval" },
    { id: "queue", label: "Queue" },
    { id: "running", label: "Running" },
    { id: "registered", label: "Registered" },
  ];
  const stageOn = (id) => {
    const s = lifecycle?.state;
    if (!s) return false;
    if (id === "submitted") return true;
    if (id === "approval") return s === LIFECYCLE.APPROVAL_REQUIRED || ["queued", "running", "failed", "completed-unregistered", "registered", "query-ready"].includes(s);
    if (id === "queue") return ["queued", "running", "failed", "completed-unregistered", "registered", "query-ready"].includes(s);
    if (id === "running") return ["running", "failed", "completed-unregistered", "registered", "query-ready"].includes(s);
    if (id === "registered") return ["registered", "query-ready"].includes(s);
    return false;
  };

  return (
    <RailFrame>
      <div
        className="rd-v2-eval-surface"
        data-testid="discover-eval-surface"
        data-taxonomy={evaluation.taxonomyKey}
        data-lifecycle={lifecycle?.state || ""}
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
          <p className="rd-v2-eval-decision-headline">{evaluation.decision.headline}</p>
          <p className="rd-v2-eval-decision-body">{evaluation.decision.body}</p>
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
              {pathStages.map((stage) => (
                <li
                  key={stage.id}
                  className={`${stageOn(stage.id) ? "on" : ""}${
                    lifecycle.state === LIFECYCLE.FAILED && stage.id === "running" ? " failed" : ""
                  }`}
                  data-stage={stage.id}
                >
                  {stage.label}
                </li>
              ))}
            </ol>
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

          <section className="rd-v2-eval-block rd-v2-eval-unknown" aria-label="Still unknown">
            <p className="rd-v2-eval-section-label">Still unknown</p>
            <ul className="rd-v2-eval-checklist">
              {evaluation.unknowns.map((item) => (
                <li key={item}>
                  <span className="rd-v2-eval-mark unknown" aria-hidden="true">
                    ?
                  </span>
                  {item}
                </li>
              ))}
            </ul>
          </section>

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

          <div className="rd-v2-eval-ask-chips" aria-label="Ask about this source">
            <p className="rd-v2-eval-section-label">Ask about this source</p>
            <div className="rd-v2-chips-row">
              {askPrompts.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  className="rd-v2-chip clickable"
                  onClick={() => onAskAbout?.(target, chip.prompt)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <RailStickyFooter>
        {primary ? (
          <button
            type="button"
            className="rd-v2-btn primary sm"
            disabled={submitting || (probeLoading && primary.id === "probe")}
            onClick={() => runAction(primary.id)}
          >
            {submitting
              ? "Submitting…"
              : probeLoading && primary.id === "probe"
                ? "Probing…"
                : primary.label}
          </button>
        ) : null}
        {secondary.map((action) => (
          <button
            key={action.id}
            type="button"
            className="rd-v2-btn sm"
            disabled={submitting || (probeLoading && action.id === "probe")}
            onClick={() => runAction(action.id)}
          >
            {probeLoading && action.id === "probe" ? "Probing…" : action.label}
          </button>
        ))}
      </RailStickyFooter>
    </RailFrame>
  );
}

export function ResourcesRailPanel({ row, rollup, onApproveJob, onRefresh, onViewActivity, onAskAbout }) {
  if (!row) {
    const workers = rollup?.hero?.workers || {};
    const sourceCount = rollup?.connect?.source_count;
    const vault = rollup?.hero?.vault || {};
    return (
      <RailFrame>
        <RailEntityHeader
          id="resources"
          title="Resources"
          description="Select a key resource to inspect access, limits, or activity."
        />
        <div className="rd-v2-rail-scroll">
          <p className="rd-v2-rail-section-label">How to read this page</p>
          <RailFieldGrid>
            <RailField label="Main list" value="Storage, account limits, and source routes" />
            <RailField label="Selection" value="Click any row for details and Ask context" />
            <RailField label="Activity" value="Open the feed for approvals, asks, and metered use" />
            <RailField label="Routes" value={sourceCount != null ? `${sourceCount} configured` : "Configured procurement routes"} />
            <RailField label="Workers" value={`${workers.busy ?? "—"}/${workers.total ?? "—"} busy`} />
            <RailField label="Vault" value={vault.used_tb != null ? `${vault.used_tb}/${vault.cap_tb ?? "?"} TB` : "quota pending"} />
          </RailFieldGrid>
        </div>
        <RailStickyFooter>
          <button type="button" className="rd-v2-btn sm" onClick={() => onViewActivity?.(null)}>
            View activity →
          </button>
        </RailStickyFooter>
      </RailFrame>
    );
  }

  if (row.kind === "activity" && row.event) {
    const ev = row.event;
    const meta = ev.meta || {};
    return (
      <RailFrame>
        <RailEntityHeader
          id={ev.id}
          title={row.label}
          description={row.sublabel}
          pills={<span className="rd-v2-pill">{row.costLabel}</span>}
        />
        <div className="rd-v2-rail-scroll">
          <RailFieldGrid>
            <RailField label="Action" value={ev.action} />
            <RailField label="Target" value={ev.target} />
            <RailField label="Session" value={ev.session_id || "—"} mono />
            {meta.action ? <RailField label="Outcome" value={meta.action} /> : null}
          </RailFieldGrid>
        </div>
        <RailStickyFooter>
          <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(row)}>
            Ask follow-up →
          </button>
        </RailStickyFooter>
      </RailFrame>
    );
  }

  if (row.kind === "statement") {
    return (
      <RailFrame>
        <RailEntityHeader id={row.section || "resources"} title={row.label} description="Resources statement row" />
        <div className="rd-v2-rail-scroll">
          <RailFieldGrid>
            <RailField label="Metric" value={row.metric} />
            <RailField label="Today / state" value={row.sublabel} />
            <RailField label="Detail" value={row.detail} />
          </RailFieldGrid>
        </div>
        <RailStickyFooter>
          {row.section === "metered" ? (
            <button type="button" className="rd-v2-btn sm primary" onClick={() => onViewActivity?.({ meterId: row.meterId })}>
              View activity →
            </button>
          ) : null}
          <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(row)}>
            Ask about this →
          </button>
        </RailStickyFooter>
      </RailFrame>
    );
  }

  if (row.kind === "meter") {
    const drivers = row.drivers || rollup?.spending?.drivers || [];
    const detail = row.detail || {};
    return (
      <RailFrame>
        <RailEntityHeader id={row.key} title={row.label} description="Metered spending" />
        <div className="rd-v2-rail-scroll">
          <RailFieldGrid>
            <RailField label="This period" value={row.metric} />
            {detail.project ? <RailField label="Project" value={detail.project} mono /> : null}
            {detail.default_max_bytes_billed ? (
              <RailField
                label="Query cap"
                value={`${Math.round(detail.default_max_bytes_billed / 1024 ** 3)} GiB`}
              />
            ) : null}
            {detail.keys_loaded != null ? <RailField label="Keys" value={String(detail.keys_loaded)} /> : null}
          </RailFieldGrid>
          {drivers.length > 0 && row.meterId === "bigquery" ? (
            <>
              <p className="rd-v2-rail-section-label">Top BQ drivers</p>
              <RailFieldGrid>
                {drivers.map((d) => (
                  <RailField key={d.target} label={d.target.slice(0, 40)} value={fmtGiB(d.bq_gib)} />
                ))}
              </RailFieldGrid>
            </>
          ) : null}
        </div>
        <RailStickyFooter>
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onViewActivity?.({ meterId: row.meterId })}>
            View activity →
          </button>
          <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(row)}>
            Ask about spend →
          </button>
        </RailStickyFooter>
      </RailFrame>
    );
  }

  if (row.kind === "capacity") {
    return (
      <RailFrame>
        <RailEntityHeader id={row.key} title={row.label} description="Desk capacity" />
        <div className="rd-v2-rail-scroll">
          <RailFieldGrid>
            <RailField label="Status" value={row.metric} />
            <RailField label="Detail" value={row.sublabel || "—"} />
            {row.detail?.mcp != null ? <RailField label="MCP tools" value={String(row.detail.mcp)} /> : null}
            {row.progress != null ? <RailField label="Used" value={`${row.progress}%`} /> : null}
          </RailFieldGrid>
        </div>
        <RailStickyFooter>
          <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(row)}>
            Ask about this →
          </button>
        </RailStickyFooter>
      </RailFrame>
    );
  }

  const shortLabel = resourceRailName(row);
  const fallbackStatus = row.job?.status
    ? String(row.job.status).replace(/_/g, " ")
    : row.warn
      ? "Needs review"
      : row.ok !== false
        ? "Healthy"
        : "Failed";
  const pillLabel = row.warn ? "Check" : row.ok === false ? "Offline" : "Ready";
  const fields =
    row.kind === "source"
      ? [
          [row.group ? "Includes" : "Website", row.endpoint || "—"],
          ["Use", resourceRailUse(row)],
          ["Access", resourceRailAccess(row)],
          ["Status", resourceRailStatus(row)],
        ]
      : row.kind === "metered"
        ? [
            ["Use", resourceRailUse(row)],
            ["Limit", resourceRailLimit(row)],
            ["Status", resourceRailStatus(row)],
          ]
        : row.kind === "usage"
          ? [
              ["Use", resourceRailUse(row)],
              ["Space", row.metric || "—"],
              ["Status", resourceRailStatus(row)],
            ]
          : [
              ["Kind", row.kind || row.section],
              ["Route", row.routes || row.metric || row.detail || "—"],
              ["Status", fallbackStatus],
            ];
  const meterActivityFilter =
    row.kind === "metered" && row.key === "bigquery"
      ? { meterId: "bigquery" }
      : row.kind === "metered" && row.key === "tavily"
        ? { meterId: "tavily" }
        : null;

  return (
    <RailFrame>
      <RailEntityHeader
        id={row.job?.id || row.endpoint || row.section || row.key}
        title={shortLabel}
        pills={
          <span className={`rd-v2-pill${row.warn ? " warn" : row.ok === false ? " fail" : ""}`}>
            {pillLabel}
          </span>
        }
        description={resourceRailDescription(row)}
      />
      <RailDecisionSummary
        status={resourceRailStatus(row) || fallbackStatus}
        primary={
          row.kind === "source"
            ? "Available for discovery/procurement"
            : row.kind === "metered"
              ? "Usable with limit checks"
              : row.kind === "usage"
                ? "Available for storage planning"
                : "Review before action"
        }
        risk={
          row.warn
            ? "Needs attention"
            : row.ok === false
              ? "Offline"
              : row.kind === "metered"
                ? resourceRailLimit(row)
                : "Low"
        }
        next={
          row.job?.status === "pending_approval"
            ? "Approve or reject the job"
            : row.kind === "source"
              ? "Use Discover to search or probe"
              : row.kind === "metered"
                ? "View activity before heavy use"
                : row.kind === "usage"
                  ? "Check capacity before large collection"
                  : "Ask about this resource"
        }
      />
      <div className="rd-v2-rail-scroll">
        <RailFieldGrid>
          {fields.map(([label, value]) => (
            <RailField key={label} label={label} value={value} />
          ))}
          {row.job ? (
            <>
              <RailField label="Job ID" value={row.job.id} mono />
              <RailField label="Job status" value={row.job.status} />
            </>
          ) : null}
          {row.key === "datacite" ? (
            <RailField label="Harvest" value={row.meta?.status || row.meta?.message || "See ops log"} />
          ) : null}
          {row.progress != null ? <RailField label="Progress" value={`${row.progress}%`} /> : null}
        </RailFieldGrid>
      </div>
      <RailStickyFooter>
        {row.job?.status === "pending_approval" ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onApproveJob?.(row.job.id)}>
            Approve job
          </button>
        ) : null}
        {meterActivityFilter ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onViewActivity?.(meterActivityFilter)}>
            View activity →
          </button>
        ) : null}
        <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(row)}>
          Ask about this →
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function EmptyRailPanel() {
  return (
    <RailFrame>
      <div className="rd-v2-rail-scroll">
        <EmptyRailState />
      </div>
    </RailFrame>
  );
}

export { DetailPanel };
