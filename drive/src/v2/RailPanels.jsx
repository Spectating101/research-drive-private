import { useRef, useState } from "react";
import { discoverCandidateState } from "@/v2/browseMeta";
import { browseTargetKey, discoverCandidateUrl } from "@/v2/discoverActions";
import { discoverCollectPreflight } from "@/v2/discoverCollectPreflight";
import { DiscoverComparePanel } from "@/v2/DiscoverComparePanel";
import { DiscoverDestinationField } from "@/v2/DiscoverDestinationField";
import { ProcurementDecisionCard } from "@/v2/ProcurementDecisionCard";
import { displayName, formatMetaValue } from "@/v2/datasetMeta";
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

function railMeta(value, fallback = "—") {
  return formatMetaValue(value) || fallback;
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
  synthesis: {
    title: "Synthesis workspace",
    desc: "Turn several registered holdings into a reusable, query-ready research panel.",
    fields: [
      ["Inputs", "Registered datasets already held by the lab"],
      ["Method", "Join keys, transformations, and coverage checks"],
      ["Primary move", "Choose a research question, then build or refresh its panel"],
      ["Output", "Registered under data_lake/synthesis for reuse"],
    ],
  },
  settings: {
    title: "Settings",
    desc: "Account, credentials, and display preferences for the research drive.",
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

export function HomeAttentionRailPanel({ object, onAskAbout, onApproveJob, onOpenDiscover }) {
  const row = object?.row || {};
  const job = row.resourceRow?.job;
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
          {job?.id ? <RailField label="Job ID" value={job.id} mono /> : null}
        </RailFieldGrid>
        {job ? (
          <ProcurementDecisionCard job={job} title={row.title} onApprove={onApproveJob} />
        ) : null}
      </div>
      <RailStickyFooter>
        {row.kind === "approval" && onOpenDiscover ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onOpenDiscover?.(job)}>
            Open in Discover →
          </button>
        ) : null}
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

export function HistoryRailPanel({ object, onAskAbout, onOpenInLibrary }) {
  const event = object?.event;
  if (!event) {
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState
            title="Select a history event"
            hint="Choose a search, probe, query or procurement outcome to reconstruct its research trail."
          />
        </div>
      </RailFrame>
    );
  }

  const meta = event.meta || {};
  const action = String(event.action || "activity").replace(/_/g, " ");
  const target = cleanRailTarget(event.target) || action;
  const timestamp = event.ts
    ? new Date(event.ts).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Time unavailable";
  const outcome =
    meta.dataset_id
      ? `Registered dataset ${meta.dataset_id}`
      : meta.job_id
        ? `Collection job ${meta.job_id}`
        : meta.total != null
          ? `${meta.total} result${meta.total === 1 ? "" : "s"} recorded`
          : "Recorded in procurement memory";

  return (
    <RailFrame>
      <RailEntityHeader
        id={event.id || event.ts || "history"}
        title={target}
        description="Procurement trail"
        pills={<span className="rd-v2-pill lab">Recorded</span>}
      />
      <RailDecisionSummary
        status={action}
        primary={outcome}
        risk="Append-only record"
        next={meta.dataset_id ? "Open the registered evidence" : "Continue from this research context"}
      />
      <div className="rd-v2-rail-scroll">
        <p className="rd-v2-rail-section-label">Event evidence</p>
        <RailFieldGrid>
          <RailField label="Action" value={action} />
          <RailField label="Time" value={timestamp} />
          <RailField label="Session" value={railMeta(event.session_id)} mono />
          <RailField label="Job" value={railMeta(meta.job_id)} mono />
          <RailField label="Dataset" value={railMeta(meta.dataset_id)} mono />
          <RailField label="Outcome" value={outcome} />
        </RailFieldGrid>
        <div className="rd-v2-history-rail-chain" aria-label="Provenance chain">
          <p className="rd-v2-rail-section-label">Provenance chain</p>
          <ol>
            <li className={/discover|search|ask/.test(String(event.action)) ? "on" : ""}>Search</li>
            <li className={/probe/.test(String(event.action)) ? "on" : ""}>Verify</li>
            <li className={/job|approve|procure|collect/.test(String(event.action)) ? "on" : ""}>Acquire</li>
            <li className={/archive/.test(String(event.action)) ? "on" : ""}>Archive</li>
            <li className={/register|promote/.test(String(event.action)) ? "on" : ""}>Register</li>
          </ol>
        </div>
      </div>
      <RailStickyFooter>
        {meta.dataset_id ? (
          <button
            type="button"
            className="rd-v2-btn primary sm"
            onClick={() => onOpenInLibrary?.({ dataset_id: meta.dataset_id })}
          >
            Open resulting dataset
          </button>
        ) : null}
        <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(event)}>
          Ask about this trail →
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function BrowseRailPanel({
  target,
  contextDataset = null,
  labIds,
  jobs = [],
  catalog = [],
  profile = null,
  browsePeerRows = [],
  onAskAbout,
  onAddToLab,
  onPreviewExternal,
  onProbeSource,
  probeState,
  collectState,
  discoverDestination = "",
  discoverDestinationOptions = [],
  onDiscoverDestinationChange,
  onOpenInLibrary,
  onApproveJob,
}) {
  if (!target) {
    if (contextDataset?.dataset_id) {
      return (
        <RailFrame>
          <RailEntityHeader
            id={contextDataset.dataset_id}
            title={displayName(contextDataset)}
            description="Source discovery context"
            pills={<span className="rd-v2-pill lab">In lab</span>}
          />
          <div className="rd-v2-rail-scroll">
            <section className="rd-v2-rail-value-brief" aria-label="Why this matters">
              <p className="rd-v2-rail-section-label">Why this matters</p>
              <p>
                Registered evidence can be queried now, compared with external sources, and reused in future synthesis without collecting it again.
              </p>
            </section>
            <RailFieldGrid>
              <RailField label="Source confidence" value="High · registered evidence" />
              <RailField
                label="Vault state"
                value={/instant|ready|query/i.test(String(contextDataset.analysis_readiness || ""))
                  ? "Saved · query-ready"
                  : "Registered"}
              />
              <RailField
                label="Next gap"
                value={contextDataset.limitations || "Find complementary coverage"}
              />
              <RailField
                label="Source"
                value={railMeta(contextDataset.source || contextDataset.publisher || contextDataset.backend)}
              />
              <RailField label="Grain" value={railMeta(contextDataset.grain)} />
              <RailField label="Coverage" value={railMeta(contextDataset.coverage || contextDataset.date_range)} />
              <RailField label="Readiness" value={railMeta(contextDataset.analysis_readiness, "Registered")} />
            </RailFieldGrid>
          </div>
          <RailStickyFooter>
            <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(contextDataset)}>
              Ask about this →
            </button>
          </RailStickyFooter>
        </RailFrame>
      );
    }
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState
            title={contextDataset?.dataset_id ? `Discover for ${displayName(contextDataset)}` : "No candidate selected"}
            hint={
              contextDataset?.dataset_id
                ? "Search related sources, then select a candidate to inspect fit, probe access, and add it to the lab."
                : "Search Discover, then select a row to inspect source, probe, destination, and Add to lab."
            }
          />
        </div>
      </RailFrame>
    );
  }

  const title = target.title || target.name || target.dataset_id || "External dataset";
  const state = target.discover_state || discoverCandidateState(target, labIds, jobs);
  const boundJob = target.bound_job || state.boundJob;
  const collectBusy = Boolean(collectState?.loading && collectState?.key);
  const collectError = collectState?.error || "";
  const awaitingApproval = boundJob?.status === "pending_approval";
  const procurementActive = Boolean(
    boundJob && ["pending_approval", "queued", "running"].includes(String(boundJob.status || "")),
  );
  const probeUrl = discoverCandidateUrl(target);
  const probeSummaryText =
    typeof probeState?.result?.summary === "string" ? probeState.result.summary : "";
  const connector = probeState?.result?.connector;
  const connectorSpec = connector?.spec || {};
  const probeLoading = Boolean(probeState?.loading);
  const probeError = probeState?.error || "";
  const probeKey = browseTargetKey(target);
  const probeResult =
    probeState?.key === probeKey ? probeState.result : target.probe_snapshot || null;
  const preflight = discoverCollectPreflight({
    target,
    probeResult,
    boundJob,
    destination: discoverDestination,
  });
  const discoverNext =
    state.key === "in_lab"
      ? "Open the Library record"
      : awaitingApproval
        ? "Approve collection to continue"
        : procurementActive
          ? "Track collection status below"
          : probeSummaryText
            ? "Review probe results, then add to lab"
            : state.key === "probe_ready"
                ? "Probe source, then add to lab"
              : state.key === "queued"
                ? "Review plan and collection destination"
                : probeUrl
                  ? "Probe source and confirm fit"
                  : "Resolve a source link before collection";

  const compactAwaiting = awaitingApproval;

  return (
    <RailFrame className={compactAwaiting ? "rd-v2-rail-awaiting" : ""}>
      <RailEntityHeader
        id={target.dataset_id || target.doi || "external"}
        title={title}
        description={compactAwaiting ? discoverNext : target.description}
        pills={
          <span className={`rd-v2-pill ${state.className}`}>
            {state.label}
          </span>
        }
      />
      {(boundJob || collectError) && (
        <div className="rd-v2-rail-procure-slot">
          <ProcurementDecisionCard
            job={boundJob}
            error={collectError}
            busy={collectBusy}
            title={title}
            onApprove={onApproveJob}
            showApproveButton={!compactAwaiting}
          />
        </div>
      )}
      <div className="rd-v2-discover-compare-slot">
        <DiscoverComparePanel
          target={target}
          catalog={catalog}
          profile={profile}
          peers={browsePeerRows}
          labIds={labIds}
        />
      </div>
      <div className="rd-v2-rail-scroll">
        {!compactAwaiting ? (
          <>
            <div className="rd-v2-rail-fields" aria-label="Candidate fields">
              <RailField
                label="Source"
                value={railMeta(target.source || target.collect_via || target.publisher || target.backend || target.domain)}
              />
              <RailField label="Access" value={railMeta(state.access)} />
              <RailField label="Coverage" value={railMeta(target.coverage || target.subtitle)} />
              <RailField label="Grain" value={railMeta(target.grain)} />
              <RailField label="License" value={railMeta(target.license, "See source terms")} />
              <RailField label="Probe" value={railMeta(state.probe)} />
            </div>
            {state.key !== "in_lab" ? (
              <>
                <p className="rd-v2-rail-section-label">Collection plan</p>
                <DiscoverDestinationField
                  value={discoverDestination}
                  options={discoverDestinationOptions}
                  onChange={onDiscoverDestinationChange}
                  disabled={procurementActive || collectBusy}
                />
                <div className="rd-v2-rail-fields">
                  <RailField label="Connector" value={preflight.connector} mono />
                  <RailField label="On Add to lab" value={preflight.onAdd} />
                  <RailField label="Approval" value={preflight.approval} />
                  <RailField label="Vault path" value={preflight.destination} />
                </div>
              </>
            ) : null}
          </>
        ) : (
          <div className="rd-v2-rail-fields">
            <RailField label="Access" value={railMeta(state.access)} />
            <RailField label="Vault path" value={preflight.destination || discoverDestination} />
            <RailField label="Connector" value={preflight.connector} mono />
          </div>
        )}
        {probeError ? (
          <p className="rd-v2-discover-probe-error">{probeError}</p>
        ) : null}
        {probeSummaryText || connector ? (
          <div className="rd-v2-discover-probe-result" aria-label="Probe result">
            <p className="rd-v2-rail-section-label">Probe result</p>
            {probeSummaryText ? <p className="rd-v2-discover-probe-summary">{probeSummaryText}</p> : null}
            {connector ? (
              <div className="rd-v2-rail-fields">
                <RailField label="Connector" value={connector.connector_id || connector.id || "—"} />
                <RailField label="Access" value={railMeta(connectorSpec.access_mode)} />
                <RailField label="Format" value={railMeta(connectorSpec.content_type)} />
                <RailField
                  label="Files"
                  value={String((connectorSpec.discovered_files || []).length || 0)}
                />
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      <RailStickyFooter>
        {awaitingApproval && boundJob && onApproveJob ? (
          <button
            type="button"
            className="rd-v2-btn primary sm"
            disabled={collectBusy}
            data-testid="discover-approve-sticky"
            onClick={() => onApproveJob(boundJob.id)}
          >
            Approve collection
          </button>
        ) : null}
        {state.key === "in_lab" ? (
          <button type="button" className="rd-v2-btn primary sm" onClick={() => onOpenInLibrary?.(target)}>
            Open in Library
          </button>
        ) : procurementActive && !awaitingApproval ? null : awaitingApproval ? null : (
          <button
            type="button"
            className="rd-v2-btn primary sm"
            onClick={() => onAddToLab?.(target)}
            disabled={probeLoading || collectBusy || !preflight.canAdd}
          >
            {collectBusy ? "Queuing…" : "Add to lab"}
          </button>
        )}
        {state.key !== "in_lab" && probeUrl ? (
          <button
            type="button"
            className="rd-v2-btn sm"
            onClick={() => onProbeSource?.(target)}
            disabled={probeLoading}
          >
            {probeLoading ? "Probing…" : "Probe source"}
          </button>
        ) : null}
        <button type="button" className="rd-v2-btn sm" onClick={onPreviewExternal}>
          Preview source
        </button>
        <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(target)}>
          Ask about this →
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}

export function ResourcesRailPanel({
  row,
  rollup,
  onApproveJob,
  onRefresh,
  onViewActivity,
  onAskAbout,
  onOpenDiscoverAwaiting,
}) {
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
    const jobId = meta.job_id || meta.jobId;
    const jobEvent = ["job_submit", "job_approve", "approve_collect"].includes(ev.action);
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
            {jobId ? <RailField label="Job ID" value={jobId} mono /> : null}
          </RailFieldGrid>
        </div>
        <RailStickyFooter>
          {jobEvent && jobId && onOpenDiscoverAwaiting ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              onClick={() => onOpenDiscoverAwaiting?.({ id: jobId })}
            >
              Review in Discover →
            </button>
          ) : null}
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
          {row.issue?.key === "jobs-pending" && onOpenDiscoverAwaiting ? (
            <button type="button" className="rd-v2-btn sm primary" onClick={() => onOpenDiscoverAwaiting?.()}>
              Open in Discover →
            </button>
          ) : null}
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
  const isReviewQueue = row.key === "jobs-pending" || String(row.issue?.key || "").includes("jobs-pending");
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
          isReviewQueue
            ? "Open Discover to approve each collection job"
            : row.job?.status === "pending_approval"
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
        {isReviewQueue && onOpenDiscoverAwaiting ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onOpenDiscoverAwaiting?.()}>
            Open in Discover →
          </button>
        ) : null}
        {row.job?.status === "pending_approval" && onOpenDiscoverAwaiting ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onOpenDiscoverAwaiting?.(row.job)}>
            Review in Discover →
          </button>
        ) : null}
        {row.job?.status === "pending_approval" ? (
          <button type="button" className="rd-v2-btn sm" onClick={() => onApproveJob?.(row.job.id)}>
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
