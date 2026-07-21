import { useCallback, useEffect, useMemo, useState } from "react";
import { V2DeskHeader } from "@/v2/V2DeskHeader";
import {
  approveJob,
  approveSafeJobs,
  describeDataset,
  deskHealth,
  deskResources,
  deskWarm,
  discoverHistory,
  facultyProfile,
  libraryOps,
  libraryOverview,
  listAcquisitions,
  listDatasets,
  listJobs,
  listPartitions,
  previewDiscoverSource,
  probePublicSource,
  procurementCatalogSummary,
  submitDiscoverCollect,
  yzuClusterStatus,
} from "@/v2/api";
import { AskRail } from "@/v2/AskRail";
import {
  datasetObject,
  externalCandidateObject,
  historyEventObject,
  homeAttentionObject,
  libraryIntakeObject,
  resourceObject,
} from "@/v2/activeObject";
import { BrowsePage } from "@/v2/BrowsePage";
import { ClusterPage } from "@/v2/ClusterPage";
import { computeDatasetOverlap } from "@/v2/clusterOverlap";
import { loadUserEmail } from "@/v2/deskSession";
import { HomePage } from "@/v2/HomePage";
import { InspectorRail } from "@/v2/InspectorRail";
import { LibraryPage } from "@/v2/LibraryPage";
import { PreviewModal } from "@/v2/PreviewModal";
import { ProfilePage } from "@/v2/ProfilePage";
import { ResourcesPage } from "@/v2/ResourcesPage";
import { SettingsPage } from "@/v2/SettingsPage";
import { SynthesisPage } from "@/v2/SynthesisPage";
import { Toast, useToast } from "@/v2/toast";
import { V2Sidebar } from "@/v2/V2Sidebar";
import { touchRecent } from "@/v2/recent";
import { mergeHealth, resolveCatalog } from "@/v2/deskSeed";
import { loadSettings } from "@/v2/settingsStore";
import { CLUSTER_NAV_DEFERRED } from "@/v2/nav-config.jsx";
import { browseTargetKey, discoverCandidateUrl } from "@/v2/discoverActions";
import { durableHistoryToEvents, mergeHistoryEvents } from "@/v2/discoverAdapters";
import { discoverModeFromLegacy, discoverModeToUrlState } from "@/v2/discoverMode";
import { discoverCandidateState } from "@/v2/browseMeta";
import { jobToCandidateRow, pendingApprovalJobs } from "@/v2/procurementJobs";
import { buildRailContext } from "@/v2/railContext";
import { DEFAULT_VAULT_DESTINATION, buildVaultDestinationOptions, touchRecentDestination } from "@/v2/vaultDestinations";

function readParams() {
  const p = new URLSearchParams(window.location.search);
  const rawTab = p.get("tab") || loadSettings().defaultTab || "home";
  const folder = p.get("folder") || "";
  const q = p.get("q") || "";
  const rawMode = p.get("mode") || "";
  let tab = rawTab === "discover" ? "browse" : rawTab;
  // Library deep links: folder+dataset without a Discover query belong on Library.
  if (tab === "browse" && folder && !q) {
    tab = "library";
  }
  // Discover has only Explore and History. Legacy modes normalize to an accepted state.
  const discoverState = tab === "browse" ? discoverModeFromLegacy(rawMode) : { mode: "explore", focusAwaiting: false };
  return {
    tab,
    dataset: p.get("dataset") || "",
    folder,
    preview: p.get("preview") === "1",
    q,
    discoverMode: discoverState.mode,
    discoverFocusAwaiting: discoverState.focusAwaiting,
  };
}

function writeParams({ tab, dataset, folder, preview, q, mode }) {
  const p = new URLSearchParams();
  if (tab && tab !== "home") p.set("tab", tab);
  if (folder) p.set("folder", folder);
  if (dataset) p.set("dataset", dataset);
  if (preview) p.set("preview", "1");
  if (q) p.set("q", q);
  const discoverMode = tab === "browse" ? discoverModeToUrlState(mode) : "";
  if (discoverMode) p.set("mode", discoverMode);
  const qs = p.toString();
  const url = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
  window.history.replaceState(null, "", url);
}

const DEFAULT_COMPARE = ["gdelt_asia_daily_country_panel", "ticker_week_country_broadcast_panel"];

function resourceAskPrompt(row) {
  if (!row) return "";
  if (row.kind === "meter") {
    return `Explain this Resources spending meter: ${row.label} (${row.metric}). What drove it, what should I inspect next, and how can we reduce waste?`;
  }
  if (row.kind === "activity") {
    return `Explain this Resources activity event: ${row.label} · ${row.metric} · cost ${row.costLabel}. What happened, what did it consume, and where should I click next?`;
  }
  if (row.kind === "usage") {
    return `Explain this Resources storage item: ${row.label} (${row.metric}). How much quota or headroom remains, what is consuming it, and what should we clean or archive next?`;
  }
  if (row.kind === "metered") {
    return `Explain this metered Resources provider: ${row.label} (${row.metric}). What quota, credential, or usage limit matters before procurement uses it?`;
  }
  if (row.kind === "source") {
    return `Explain this procurement source: ${row.label} at ${row.endpoint || "configured source"}. What can we collect from it, which routes use it, and what limits or credentials apply?`;
  }
  if (row.kind === "layer") {
    return `Explain this procurement route: ${row.label} (${row.metric}). When should Composer use it and what upstream resources does it depend on?`;
  }
  if (row.kind === "compute") {
    return `Explain this compute or queue resource: ${row.label} (${row.metric}). What capacity remains and what could block collection?`;
  }
  if (row.kind === "capacity") {
    return `Explain this Resources capacity item: ${row.label} (${row.metric}). Is it healthy, saturated, or blocked?`;
  }
  if (row.kind === "active" || row.job) {
    return `Explain this active Resources job: ${row.label} (${row.metric}). What will it collect, does it need approval, and what happens next?`;
  }
  return `Explain this Resources row: ${row.label} (${row.metric || row.section || "selected"}).`;
}

export function V2App() {
  const [tab, setTab] = useState(() => readParams().tab);
  const [folderId, setFolderId] = useState(() => readParams().folder);
  const [selectedId, setSelectedId] = useState(() => readParams().dataset);
  const [browseRow, setBrowseRow] = useState(null);
  const [researchBriefContext, setResearchBriefContext] = useState(null);
  const [browseProbe, setBrowseProbe] = useState({ key: "", loading: false, result: null, error: "" });
  const [browseCollect, setBrowseCollect] = useState({ key: "", loading: false, error: "" });
  const [browseJobBindings, setBrowseJobBindings] = useState({});
  const [discoverFilter, setDiscoverFilter] = useState("all");
  const [discoverMode, setDiscoverMode] = useState(() => readParams().discoverMode);
  const [discoverFocusAwaiting, setDiscoverFocusAwaiting] = useState(
    () => readParams().discoverFocusAwaiting,
  );
  const [discoverActivityFilter, setDiscoverActivityFilter] = useState(() =>
    readParams().discoverFocusAwaiting ? "awaiting" : "all",
  );
  const [discoverDestination, setDiscoverDestination] = useState(DEFAULT_VAULT_DESTINATION);
  const [browsePeerRows, setBrowsePeerRows] = useState([]);
  const [destinationRecentsTick, setDestinationRecentsTick] = useState(0);
  const [resourceRow, setResourceRow] = useState(null);
  const [activeObject, setActiveObject] = useState(null);
  const [compareIds, setCompareIds] = useState(DEFAULT_COMPARE);
  const [previewOpen, setPreviewOpen] = useState(() => readParams().preview);
  const [previewMode, setPreviewMode] = useState("lab");
  const [previewTarget, setPreviewTarget] = useState(null);
  const [railTab, setRailTab] = useState("detail");
  const [datasets, setDatasets] = useState([]);
  const [usingSeed, setUsingSeed] = useState(false);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [profile, setProfile] = useState(null);
  const [selectedProfileWork, setSelectedProfileWork] = useState(null);
  const [settingsGroup, setSettingsGroup] = useState("identity");
  const [searchQuery, setSearchQuery] = useState(() => readParams().q);
  const [loadError, setLoadError] = useState("");
  const [health, setHealth] = useState(null);
  const [deskRefreshedAt, setDeskRefreshedAt] = useState(null);
  const [acquisitions, setAcquisitions] = useState([]);
  const [partitions, setPartitions] = useState([]);
  const [ops, setOps] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [overview, setOverview] = useState(null);
  const [catalogSummary, setCatalogSummary] = useState(null);
  const [cluster, setCluster] = useState(null);
  const [resourcesRollup, setResourcesRollup] = useState(undefined);

  const [durableHistoryEvents, setDurableHistoryEvents] = useState([]);
  const [resourcesRefreshedAt, setResourcesRefreshedAt] = useState(null);
  const [resourceMode, setResourceMode] = useState("spending");
  const [activityFilter, setActivityFilter] = useState(null);
  const [pendingAsk, setPendingAsk] = useState("");
  const { toast, show: showToast } = useToast();

  const reloadProfile = useCallback(() => {
    const email = loadUserEmail();
    if (!email) {
      setProfile({ unknown: true });
      return;
    }
    facultyProfile(email)
      .then((data) => {
        const row = data?.found ? data.profile : null;
        // Registry fallback stubs set unknown:true — keep desk unbound, no fabricated name.
        if (!row || row.unknown) {
          setProfile({ email, unknown: true });
          return;
        }
        setProfile(row);
      })
      .catch(() => setProfile({ email, unknown: true }));
  }, []);

  const applyCatalog = useCallback((rows, errMsg = "") => {
    const { catalog, usingSeed: seed } = resolveCatalog(rows);
    setDatasets(catalog);
    setUsingSeed(seed);
    setLoadError(seed ? errMsg : "");
    const ids = catalog.map((d) => d.dataset_id);
    setCompareIds((cur) => {
      const valid = cur.every((id) => ids.includes(id));
      if (valid && cur[0] && cur[1]) return cur;
      const a = ids.find((id) => /gdelt.*asia/i.test(id)) || ids[0];
      const b = ids.find((id) => /ticker.*week/i.test(id)) || ids[1] || ids[0];
      return a && b ? [a, b] : cur;
    });
  }, []);

  const refreshBackend = useCallback(() => {
    listDatasets()
      .then((rows) => applyCatalog(rows))
      .catch((err) => applyCatalog([], err.message));
    deskHealth(false)
      .then((h) => setHealth(mergeHealth(h)))
      .catch(() => setHealth(mergeHealth(null)));
    listAcquisitions(true)
      .then((d) => setAcquisitions(d.acquisitions || []))
      .catch(() => setAcquisitions([]));
    listPartitions()
      .then((rows) => setPartitions(Array.isArray(rows) ? rows : []))
      .catch(() => setPartitions([]));
    libraryOps()
      .then(setOps)
      .catch(() => setOps(null));
    listJobs()
      .then((rows) => setJobs(Array.isArray(rows) ? rows : []))
      .catch(() => setJobs([]));
    libraryOverview()
      .then(setOverview)
      .catch(() => setOverview(null));
    procurementCatalogSummary()
      .then(setCatalogSummary)
      .catch(() => setCatalogSummary(null));
    yzuClusterStatus(false)
      .then(setCluster)
      .catch(() => setCluster(null));
    deskResources(false)
      .then((payload) => {
        setResourcesRollup(payload);
        setResourcesRefreshedAt(Date.now());
      })
      .catch(() => setResourcesRollup((cur) => (cur === undefined ? null : cur)));
    reloadProfile();
    setDeskRefreshedAt(Date.now());
  }, [reloadProfile, applyCatalog]);

  const handleApproveJob = useCallback(
    async (jobId) => {
      if (!jobId) return;
      try {
        await approveJob(jobId);
        showToast(`Job approved · ${String(jobId).slice(0, 8)}…`);
        refreshBackend();
      } catch (err) {
        showToast(err.message || "Approve failed", "error");
      }
    },
    [refreshBackend, showToast],
  );

  const handleApproveSafeJobs = useCallback(async () => {
    try {
      const out = await approveSafeJobs();
      const n = out?.approved?.length ?? out?.approved_count ?? 0;
      showToast(n ? `Approved ${n} safe job(s)` : "No safe pending jobs to approve");
      refreshBackend();
    } catch (err) {
      showToast(err.message || "Bulk approve failed", "error");
    }
  }, [refreshBackend, showToast]);

  useEffect(() => {
    refreshBackend();
  }, [refreshBackend]);

  useEffect(() => {
    deskWarm({ userEmail: loadUserEmail(), background: true }).catch(() => {});
  }, []);

  const askFromPrompt = useCallback((prompt) => {
    if (!prompt) return;
    setPendingAsk(prompt);
    setRailTab("ask");
  }, []);

  // Normalize deep links (e.g. tab=browse + folder=dataset → library) into the address bar.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const rawTab = p.get("tab") || "";
    const rawFolder = p.get("folder") || "";
    const rawQ = p.get("q") || "";
    const needsLibraryRedirect =
      (rawTab === "browse" || rawTab === "discover") && rawFolder && !rawQ && tab === "library";
    const datasetMismatch = Boolean(selectedId && p.get("dataset") !== selectedId);
    if (needsLibraryRedirect || datasetMismatch) {
      writeParams({
        tab,
        folder: folderId,
        dataset: selectedId,
        preview: previewOpen,
        q: tab === "browse" ? searchQuery.trim() : "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot URL normalize on mount
  }, []);

  useEffect(() => {
    if (!datasets.length || selectedId || tab !== "home") return;
    const first = datasets[0];
    const pick = first.dataset_id;
    setSelectedId(pick);
    setActiveObject(datasetObject(first));
    touchRecent(pick);
    writeParams({ tab, folder: folderId, dataset: pick, preview: previewOpen });
  }, [datasets, selectedId, tab, folderId, previewOpen]);

  const catalog = datasets;

  const labIds = useMemo(() => new Set(catalog.map((d) => d.dataset_id)), [catalog]);
  const discoverDestinationOptions = useMemo(
    () => buildVaultDestinationOptions(partitions, profile, undefined),
    [partitions, profile, destinationRecentsTick],
  );

  const handleDiscoverDestinationChange = useCallback((value) => {
    setDiscoverDestination(value);
  }, []);

  useEffect(() => {
    const preferred = profile?.preferred_destination;
    if (preferred) setDiscoverDestination(preferred);
  }, [profile?.preferred_destination]);

  const selectedFromList = useMemo(
    () => catalog.find((d) => d.dataset_id === selectedId) || null,
    [catalog, selectedId],
  );

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailLoading(false);
      return;
    }
    const base = selectedFromList || { dataset_id: selectedId };
    setDetail(base);
    setDetailLoading(true);
    describeDataset(selectedId)
      .then((d) => setDetail((cur) => ({ ...cur, ...d })))
      .catch(() => {})
      .finally(() => setDetailLoading(false));
  }, [selectedId, selectedFromList]);

  const browseTarget = useMemo(() => {
    if (!browseRow) return null;
    const key = browseTargetKey(browseRow);
    const boundId = browseRow.bound_job_id || browseJobBindings[key];
    const boundJob = boundId
      ? jobs.find((j) => j.id === boundId) || browseRow.bound_job
      : browseRow.bound_job;
    if (!boundJob) return browseRow;
    return { ...browseRow, bound_job_id: boundJob.id, bound_job: boundJob };
  }, [browseRow, browseJobBindings, jobs]);
  const browseSelectedId = browseRow ? browseTargetKey(browseRow) : "";
  const browseCollectState =
    browseTarget && browseCollect.key === browseTargetKey(browseTarget)
      ? browseCollect
      : { key: "", loading: false, error: "" };
  const browseProbeState =
    browseProbe.key && browseProbe.key === browseTargetKey(browseTarget)
      ? browseProbe
      : { loading: false, result: null, error: "" };

  const clusterContext = useMemo(() => {
    const [aId, bId] = compareIds;
    const a = catalog.find((d) => d.dataset_id === aId);
    const b = catalog.find((d) => d.dataset_id === bId);
    if (!a || !b) return { a, b };
    const overlap = computeDatasetOverlap(a, b);
    return { a, b, ...overlap };
  }, [compareIds, catalog]);

  const railContext = useMemo(
    () =>
      ({
        ...buildRailContext({
          tab,
          mode: railTab,
          dataset: detail,
        activeObject,
        searchQuery,
        folderId,
          clusterContext,
          profileEmail: profile?.email || loadUserEmail(),
        }),
        research_brief: researchBriefContext || undefined,
      }),
    [tab, railTab, detail, activeObject, searchQuery, folderId, clusterContext, profile, researchBriefContext],
  );

  const syncUrl = useCallback(
    (patch) => {
      const nextTab = patch.tab ?? tab;
      const nextQ =
        patch.q !== undefined
          ? patch.q
          : nextTab === "browse"
            ? searchQuery.trim()
            : "";
      const nextMode =
        patch.mode !== undefined
          ? patch.mode
          : nextTab === "browse"
            ? discoverMode
            : "search";
      const next = {
        tab: nextTab,
        folder: patch.folder ?? folderId,
        dataset: patch.dataset ?? selectedId,
        preview: patch.preview ?? previewOpen,
        q: nextQ,
        mode: nextTab === "browse" ? nextMode : undefined,
      };
      writeParams(next);
    },
    [tab, folderId, selectedId, previewOpen, searchQuery, discoverMode],
  );

  const goTab = useCallback(
    (id) => {
      if (id !== "browse") {
        setDiscoverMode("explore");
        setDiscoverFocusAwaiting(false);
        setDiscoverActivityFilter("all");
        setDiscoverFilter("all");
      }
      if (id !== "profile") setSelectedProfileWork(null);
      if (id !== "settings") setSettingsGroup("identity");
      if (id === "library") {
        setTab(id);
        setSelectedId("");
        setDetail(null);
        setPreviewOpen(false);
        setPreviewTarget(null);
        setActiveObject(null);
        setRailTab("detail");
        syncUrl({ tab: id, dataset: "", preview: false, mode: "explore" });
        return;
      }
      setTab(id);
      syncUrl({ tab: id });
    },
    [syncUrl],
  );

  const selectDataset = useCallback(
    (row) => {
      const id = row.dataset_id || row.id;
      setSelectedId(id);
      setActiveObject(datasetObject(row));
      touchRecent(id);
      setRailTab(loadSettings().onSelect === "ask" ? "ask" : "detail");
      syncUrl({ dataset: id, preview: false });
      setPreviewOpen(false);
    },
    [syncUrl],
  );

  const openPreview = useCallback(
    (row) => {
      const id = row?.dataset_id || selectedId;
      if (!id) return;
      setPreviewTarget(row || selectedFromList || { dataset_id: id });
      setPreviewMode("lab");
      setSelectedId(id);
      setActiveObject(datasetObject(row || selectedFromList || { dataset_id: id }));
      touchRecent(id);
      setPreviewOpen(true);
      setRailTab("detail");
      syncUrl({ dataset: id, preview: true });
    },
    [selectedId, selectedFromList, syncUrl],
  );

  const openPreviewExternal = useCallback(async (row) => {
    if (!row) return;
    setBrowseRow(row);
    setActiveObject(externalCandidateObject(row));
    setPreviewMode("external");
    setRailTab("detail");
    const canPreview =
      row.source_id || row.connector_id || row.candidate_key || row.url || row.dataset_id;
    if (canPreview) {
      try {
        const preview = await previewDiscoverSource({
          sourceId: row.source_id || "",
          connectorId: row.connector_id || "",
          candidateKey: row.candidate_key || "",
          url: discoverCandidateUrl(row) || row.url || "",
          datasetId: row.dataset_id || "",
        });
        setPreviewTarget({ ...row, source_preview: preview });
        setPreviewOpen(true);
        return;
      } catch {
        /* fall through to metadata-only preview */
      }
    }
    setPreviewTarget(row);
    setPreviewOpen(true);
  }, []);

  const askFromSearch = useCallback(() => {
    const q = searchQuery.trim();
    if (q) {
      goTab("browse");
      syncUrl({ tab: "browse", q });
      setPendingAsk(`Find datasets for: ${q}`);
    }
    setRailTab("ask");
  }, [searchQuery, goTab, syncUrl]);

  const submitSearch = useCallback(() => {
    const q = searchQuery.trim();
    if (!q) return;
    goTab("browse");
    syncUrl({ tab: "browse", q });
    setRailTab("detail");
  }, [searchQuery, goTab, syncUrl]);

  const askSearchWeb = useCallback(
    (query) => {
      const q = String(query || searchQuery || "").trim();
      if (!q) return;
      goTab("browse");
      syncUrl({ tab: "browse", q });
      setRailTab("ask");
      setPendingAsk(
        `Find external datasets for: ${q}. Start with open-web discovery, probe promising sources, and propose the safest acquisition plan for this lab.`,
      );
    },
    [searchQuery, goTab, syncUrl],
  );

  const researchFromDiscover = useCallback(({ question, matches = [] } = {}) => {
    const q = String(question || "").trim();
    if (!q) return;
    const evidence = matches
      .slice(0, 6)
      .map((row, index) => {
        const title = row?.title || row?.name || row?.dataset_id || "Untitled evidence";
        const detail = [row?.grain, row?.source, row?.analysis_readiness]
          .filter(Boolean)
          .join(" · ");
        return { rank: index + 1, title, detail, dataset_id: row?.dataset_id || "" };
      });
    setResearchBriefContext({ question: q, semantic_matches: evidence });
    setRailTab("ask");
    setPendingAsk(
      `Assess this research question: ${q}\n\nWhich available evidence can answer it now, what material gaps remain, and what is the safest next research or procurement step? Do not start collection without explicit approval.`,
    );
  }, []);

  const openDiscoverActivity = useCallback(
    ({ job = null, focusAwaiting = false } = {}) => {
      setDiscoverMode("explore");
      setDiscoverFocusAwaiting(Boolean(focusAwaiting || job));
      setDiscoverActivityFilter(focusAwaiting || job ? "awaiting" : "all");
      setDiscoverFilter(focusAwaiting || job ? "awaiting" : "all");
      // Preserve searchQuery — the Explore queue must not wipe the research loop.
      setTab("browse");
      setRailTab("detail");
      syncUrl({
        tab: "browse",
        q: searchQuery.trim(),
        mode: "explore",
      });
      const targetJob =
        (job?.id ? jobs.find((j) => j.id === job.id) : null) ||
        job ||
        (focusAwaiting ? pendingApprovalJobs(jobs)[0] : null);
      if (targetJob) {
        const row = jobToCandidateRow(targetJob);
        if (row) {
          setBrowseRow(row);
          setActiveObject(externalCandidateObject(row));
        }
      } else if (focusAwaiting) {
        setBrowseRow(null);
        setActiveObject(null);
      }
    },
    [jobs, syncUrl, searchQuery],
  );

  const openDiscoverAwaiting = useCallback(
    (job) => openDiscoverActivity({ job, focusAwaiting: true }),
    [openDiscoverActivity],
  );

  const setDiscoverModeSafe = useCallback(
    (rawMode) => {
      const nextState = discoverModeFromLegacy(rawMode);
      const next = nextState.mode;
      setDiscoverMode(next);
      setDiscoverFocusAwaiting(nextState.focusAwaiting);
      setDiscoverActivityFilter("all");
      setDiscoverFilter("all");
      if (next === "explore") {
        setBrowseRow((prev) => (prev?.kind === "job_pending" ? null : prev));
        setActiveObject((prev) => {
          if (prev?.kind === "history_event") return null;
          if (prev?.kind === "external_candidate" && prev?.row?.kind === "job_pending") return null;
          return prev;
        });
      } else {
        setBrowseRow(null);
        setActiveObject((prev) => (prev?.kind === "history_event" ? prev : null));
        setRailTab("detail");
      }
      syncUrl({ tab: "browse", q: searchQuery.trim(), mode: next });
    },
    [searchQuery, syncUrl],
  );

  const askAddToLab = useCallback(
    async (target) => {
      if (!target) return;
      const state = target.discover_state || discoverCandidateState(target, labIds, jobs);
      if (state.key === "in_lab") {
        const id = target.dataset_id;
        if (!id) return;
        setTab("library");
        const row = catalog.find((d) => d.dataset_id === id) || { dataset_id: id, ...target };
        setSelectedId(id);
        setActiveObject(datasetObject(row));
        touchRecent(id);
        setRailTab("detail");
        syncUrl({ tab: "library", dataset: id, preview: false, q: "" });
        showToast("Opened in Library");
        return;
      }

      setActiveObject(externalCandidateObject(target));
      setRailTab("detail");

      const key = browseTargetKey(target);
      const probeResult =
        browseProbe.key === key
          ? browseProbe.result
          : target.probe_snapshot || browseRow?.probe_snapshot || null;
      const connectorId = probeResult?.connector?.connector_id || probeResult?.connector?.id;

      setBrowseCollect({ key, loading: true, error: "" });

      if (connectorId) {
        try {
          const out = await submitDiscoverCollect(connectorId, {
            limit: 200,
            autoApprove: false,
            destination: dest,
            candidateKey: target?.candidate_key || "",
            sourceId: target?.source_id || "",
            url: discoverCandidateUrl(target) || target?.url || "",
            provider: target?.provider || target?.source || "",
            kind: target?.kind || "",
          });
          touchRecentDestination(discoverDestination);
          setDestinationRecentsTick((n) => n + 1);
          const job = out?.job;
          if (job?.id) {
            setBrowseJobBindings((prev) => ({ ...prev, [key]: job.id }));
            const enriched = {
              ...target,
              bound_job_id: job.id,
              bound_job: job,
              destination: discoverDestination,
            };
            setBrowseRow((prev) => (prev && browseTargetKey(prev) === key ? { ...prev, ...enriched } : enriched));
            setActiveObject(externalCandidateObject(enriched));
          }
          refreshBackend();
          setBrowseCollect({ key, loading: false, error: "" });
          showToast(
            job?.status === "pending_approval"
              ? "Collection queued — review and approve below"
              : job?.id
                ? `Collection job queued (${job.id})`
                : "Collection job queued",
          );
          return;
        } catch (err) {
          setBrowseCollect({ key, loading: false, error: err?.message || "Collect failed" });
          showToast(err?.message || "Collect failed", "error");
          return;
        }
      }

      setBrowseCollect({
        key,
        loading: false,
        error: "Probe source first — no connector ready for collection.",
      });
      showToast("Probe source before adding to lab");
    },
    [labIds, jobs, browseProbe, browseRow, catalog, syncUrl, showToast, refreshBackend, discoverDestination],
  );

  const probeDiscoverCandidate = useCallback(async (target) => {
    const url = discoverCandidateUrl(target);
    const key = browseTargetKey(target);
    if (!url) {
      setBrowseProbe({ key, loading: false, result: null, error: "No public URL to probe for this candidate." });
      return;
    }
    setBrowseProbe({ key, loading: true, result: null, error: "" });
    try {
      const out = await probePublicSource(url, target?.title || target?.name || "", {
        candidateKey: target?.candidate_key || "",
        sourceId: target?.source_id || "",
        connectorId: target?.connector_id || "",
        provider: target?.provider || target?.source || "",
        kind: target?.kind || "",
      });
      if (out?.error) {
        setBrowseProbe({ key, loading: false, result: null, error: String(out.error) });
        return;
      }
      setBrowseProbe({ key, loading: false, result: out, error: "" });
      setBrowseRow((prev) =>
        prev && browseTargetKey(prev) === key ? { ...prev, probe_snapshot: out } : prev,
      );
      showToast("Source probed — review connector details");
    } catch (err) {
      setBrowseProbe({ key, loading: false, result: null, error: err?.message || "Probe failed" });
    }
  }, [showToast]);

  const openInLibraryFromDiscover = useCallback(
    (target) => {
      const id = target?.dataset_id;
      if (!id) return;
      setTab("library");
      const row = catalog.find((d) => d.dataset_id === id) || { dataset_id: id, ...target };
      setSelectedId(id);
      setActiveObject(datasetObject(row));
      touchRecent(id);
      setRailTab("detail");
      syncUrl({ tab: "library", dataset: id, preview: false, q: "" });
    },
    [catalog, syncUrl],
  );

  const askAboutSelection = useCallback(
    (target) => {
      if (tab === "browse" && activeObject?.kind === "history_event") {
        setRailTab("ask");
        setPendingAsk(
          `Explain this research trail event: ${activeObject.title}. Reconstruct what happened, what evidence or job it produced, and the safest useful next action.`,
        );
        return;
      }
      if (tab === "browse" && target) {
        const label = target.title || target.dataset_id || target.name || "this Discover candidate";
        setActiveObject(externalCandidateObject(target));
        setRailTab("ask");
        setPendingAsk(
          `Assess this Discover candidate for procurement: ${label}. Verify fit, access terms, probe route, vault destination, and the safest next action.`,
        );
        return;
      }
      if (target?.kind === "library_folder") {
        setRailTab("ask");
        setPendingAsk(
          `Explain this Library branch: ${target.destination}. Summarize holdings, query readiness, missing material, and the next acquisition action.`,
        );
        return;
      }
      if (target?.kind === "library_intake") {
        setRailTab("ask");
        setPendingAsk(`Help finish this Library intake for ${target.destination}.`);
        return;
      }
      if (target?.kind === "home_attention") {
        setActiveObject(target);
        setRailTab("ask");
        setPendingAsk(
          target.row?.prompt || `Explain this Home attention item: ${target.title || "selected work"}.`,
        );
        return;
      }
      if (tab === "resources" && target) {
        setRailTab("ask");
        setPendingAsk(resourceAskPrompt(target));
        return;
      }
      if (tab === "profile") {
        const work = target?.title ? target : selectedProfileWork;
        const label = work?.title || "this work";
        setRailTab("ask");
        setPendingAsk(
          work?.title
            ? `Ask about this work: ${label}. Summarize its contribution, how it fits the desk research context, and the safest next Discover or Lab action.`
            : "Ask about this research profile and its works.",
        );
        return;
      }
      setRailTab("ask");
    },
    [activeObject, selectedProfileWork, tab],
  );

  const focusLibraryFolder = useCallback((object) => {
    if (activeObject?.kind === "library_intake") return;
    setActiveObject(object);
  }, [activeObject?.kind]);

  const changeLibraryFolder = useCallback(
    (id) => {
      setFolderId(id);
      setSelectedId("");
      setDetail(null);
      setPreviewOpen(false);
      setPreviewTarget(null);
      setActiveObject(null);
      setRailTab("detail");
      syncUrl({ folder: id, dataset: "", preview: false });
    },
    [syncUrl],
  );

  const startLibraryIntake = useCallback(
    (mode, folderObject) => {
      setSelectedId("");
      setDetail(null);
      setPreviewOpen(false);
      setPreviewTarget(null);
      setActiveObject(libraryIntakeObject(mode, folderObject));
      setRailTab("detail");
      syncUrl({ folder: folderObject?.folderId ?? folderId, dataset: "", preview: false });
    },
    [folderId, syncUrl],
  );

  const queueLibraryAsk = useCallback(
    (prompt) => {
      setRailTab("ask");
      setPendingAsk(prompt);
      showToast("Queued Ask - Library");
    },
    [showToast],
  );

  const submitLibraryUpload = useCallback(
    (files, intake) => {
      const names = Array.from(files || []).map((file) => file.name).filter(Boolean);
      const destination = intake?.destination || "Lab root";
      const filePart = names.length ? ` Files: ${names.join(", ")}.` : " No files selected yet.";
      queueLibraryAsk(
        `Upload files to ${destination}.${filePart} Confirm destination, ingestion, schema detection, and vault archival.`,
      );
    },
    [queueLibraryAsk],
  );

  const submitLibraryUrl = useCallback(
    (value, intake) => {
      const destination = intake?.destination || "Lab root";
      const targets = String(value || "").trim().replace(/\s+/g, " ");
      queueLibraryAsk(
        `Add URL or DOI to ${destination}. Targets: ${targets}. Probe source, collect metadata, and procure if missing.`,
      );
    },
    [queueLibraryAsk],
  );

  const submitLibraryProcure = useCallback(
    (intake) => {
      const destination = intake?.destination || "Lab root";
      queueLibraryAsk(
        `Procure datasets for ${destination}. Search faculty sources, check the local catalog, probe public sources, and propose acquisition steps.`,
      );
    },
    [queueLibraryAsk],
  );

  const askHomeAttention = useCallback(
    (item) => {
      setActiveObject(homeAttentionObject(item));
      setRailTab("ask");
      setPendingAsk(item?.prompt || `Explain this Home attention item: ${item?.title || "selected work"}.`);
      showToast("Queued Ask - Home");
    },
    [showToast],
  );

  const openHomeAttention = useCallback(
    (item) => {
      if (item?.kind === "approval" || item?.discoverFilter === "awaiting") {
        openDiscoverAwaiting(item?.resourceRow?.job);
        return;
      }
      if (item?.tab === "resources" && item.resourceRow) {
        setResourceMode("spending");
        setActivityFilter(null);
        setResourceRow(item.resourceRow);
        setActiveObject(resourceObject(item.resourceRow));
        setRailTab("detail");
        goTab("resources");
        return;
      }
      goTab(item?.tab || "home");
    },
    [goTab, openDiscoverAwaiting],
  );

  const selectBrowseRow = useCallback((row) => {
    if (!row) {
      setBrowseRow(null);
      setBrowseProbe({ key: "", loading: false, result: null, error: "" });
      setActiveObject((current) => (current?.kind === "external_candidate" ? null : current));
      setRailTab("detail");
      return;
    }
    setBrowseRow(row);
    setBrowseProbe((current) =>
      current.key === browseTargetKey(row)
        ? current
        : { key: "", loading: false, result: null, error: "" },
    );
    setActiveObject(externalCandidateObject(row));
    setRailTab("detail");
  }, []);

  
  useEffect(() => {
    let cancelled = false;
    discoverHistory({ limit: 50 })
      .then((data) => {
        if (!cancelled) setDurableHistoryEvents(durableHistoryToEvents(data));
      })
      .catch(() => {
        if (!cancelled) setDurableHistoryEvents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [jobs]);

  const selectHistoryEvent = useCallback((event) => {
    if (!event) {
      setActiveObject((current) => (current?.kind === "history_event" ? null : current));
      return;
    }
    setBrowseRow(null);
    setActiveObject(historyEventObject(event));
    setRailTab("detail");
  }, []);

  const filteredDatasets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.filter((d) => {
      const text = `${d.dataset_id} ${d.name} ${d.grain} ${d.description || ""}`.toLowerCase();
      return text.includes(q);
    });
  }, [catalog, searchQuery]);

  const headerDsCount = catalog.length || Number(health?.datasets) || 0;
  const headerConnected = catalog.filter((d) =>
    /instant|query/i.test(String(d.analysis_readiness || "")),
  ).length;

  let main;
  switch (tab) {
    case "home":
      main = (
        <HomePage
          datasets={catalog}
          health={health}
          cluster={health?.cluster}
          profile={profile}
          acquisitions={acquisitions}
          partitions={partitions}
          jobs={jobs}
          usingSeed={usingSeed}
          onAskComposer={askFromPrompt}
          onGoTab={goTab}
          onOpenAttention={openHomeAttention}
          onSelectDataset={selectDataset}
          onPreviewDataset={openPreview}
          onSuggestSearch={(q) => {
            setSearchQuery(q);
            goTab("browse");
          }}
          onAskAttention={askHomeAttention}
          onApproveSafeJobs={handleApproveSafeJobs}
        />
      );
      break;
    case "library":
      main = (
        <LibraryPage
          datasets={filteredDatasets}
          partitions={partitions}
          cluster={health?.cluster}
          folderId={folderId}
          onFolderChange={changeLibraryFolder}
          selectedId={selectedId}
          onSelectDataset={selectDataset}
          onPreviewDataset={openPreview}
          onRefresh={refreshBackend}
          onFocusFolder={focusLibraryFolder}
          onStartUpload={(folder) => startLibraryIntake("upload", folder)}
          onStartUrl={(folder) => startLibraryIntake("url", folder)}
          onStartProcure={(folder) => startLibraryIntake("procure", folder)}
        />
      );
      break;
    case "cluster":
      main = (
        <ClusterPage
          datasets={catalog}
          compareIds={compareIds}
          onCompareChange={setCompareIds}
          onGoTab={goTab}
          onAskComposer={askFromPrompt}
        />
      );
      break;
    case "browse":
      main = (
        <BrowsePage
          labIds={labIds}
          selectedId={browseSelectedId}
          searchQuery={searchQuery}
          onSearchChange={(q) => {
            setSearchQuery(q);
            if (discoverMode !== "explore" && discoverMode !== "search") {
              setDiscoverMode("explore");
              setDiscoverFocusAwaiting(false);
              setDiscoverActivityFilter("all");
              setDiscoverFilter("all");
              syncUrl({ tab: "browse", q, mode: "explore" });
            }
          }}
          jobs={jobs}
          jobBindings={browseJobBindings}
          discoverFilter={discoverFilter}
          discoverMode={discoverMode}
          discoverFocusAwaiting={discoverFocusAwaiting}
          onOpenReviewQueue={openDiscoverAwaiting}
          discoverActivityFilter={discoverActivityFilter}
          onDiscoverActivityFilterChange={setDiscoverActivityFilter}
          onDiscoverModeChange={setDiscoverModeSafe}
          profile={profile}
          catalog={catalog}
          contextDataset={detail || selectedFromList}
          onDiscoverFilterChange={setDiscoverFilter}
          usingSeed={usingSeed}
          onSuggestSearch={(q) => {
            setSearchQuery(q);
            setDiscoverMode("explore");
            setDiscoverFocusAwaiting(false);
            setDiscoverActivityFilter("all");
            setDiscoverFilter("all");
            setTab("browse");
            syncUrl({ tab: "browse", q, mode: "explore" });
          }}
          onSearchWeb={askSearchWeb}
          onResearchQuestion={researchFromDiscover}
          onSelectRow={selectBrowseRow}
          onMergedRowsChange={setBrowsePeerRows}
          onApproveSafeJobs={handleApproveSafeJobs}
          historyEvents={mergeHistoryEvents(durableHistoryEvents, resourcesRollup?.activity?.events || [])}
          selectedHistoryId={activeObject?.kind === "history_event" ? activeObject.id : ""}
          onSelectHistoryEvent={selectHistoryEvent}
        />
      );
      break;
    case "synthesis":
      main = <SynthesisPage onAskComposer={askFromPrompt} onToast={showToast} />;
      break;
    case "resources":
      main = (
        <ResourcesPage
          rollup={resourcesRollup}
          rollupLoading={resourcesRollup === undefined}
          health={health}
          ops={ops}
          jobs={jobs}
          catalogSummary={catalogSummary}
          cluster={health?.cluster || cluster}
          datasets={catalog}
          partitions={partitions}
          mode={resourceMode}
          onModeChange={setResourceMode}
          activityFilter={activityFilter}
          onClearActivityFilter={() => setActivityFilter(null)}
          selectedKey={resourceRow?.key}
          onRefresh={refreshBackend}
          refreshedAt={resourcesRefreshedAt}
          onSelectRow={(r) => {
            setResourceRow(r);
            setActiveObject(resourceObject(r));
            setRailTab("detail");
          }}
        />
      );
      break;
    case "profile":
      main = (
        <ProfilePage
          profile={profile}
          datasets={catalog}
          compareIds={compareIds}
          selectedWorkId={selectedProfileWork?.raw || null}
          onSelectWork={(work) => {
            setSelectedProfileWork(work);
            setRailTab("detail");
          }}
          onGoTab={goTab}
          onSuggestSearch={(q) => {
            setSearchQuery(q);
            setDiscoverMode("explore");
            setDiscoverFocusAwaiting(false);
            setDiscoverActivityFilter("all");
            setDiscoverFilter("all");
            setTab("browse");
            syncUrl({ tab: "browse", q, mode: "explore" });
          }}
        />
      );
      break;
    case "settings":
      main = (
        <SettingsPage
          health={health}
          onProfileRefresh={reloadProfile}
          onToast={showToast}
          activeGroup={settingsGroup}
          selectedGroup={settingsGroup}
          onSelectGroup={(group) => {
            setSettingsGroup(group);
            setRailTab("detail");
          }}
        />
      );
      break;
    default:
      main = null;
  }

  const hideRail = false;

  return (
    <div className={`yzu-shell with-inspector rd-theme-light rd-v2-shell${hideRail ? " no-rail" : ""}`}>
      <V2DeskHeader
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSearchSubmit={submitSearch}
        onAskFromSearch={askFromSearch}
        onBrandClick={() => goTab("home")}
        onRetry={refreshBackend}
        headerInitials="YZ"
        datasetCount={headerDsCount}
        usingSeed={usingSeed}
        workCount={Math.max(
          Number(health?.desk?.jobs?.pending_approval) || 0,
          pendingApprovalJobs(jobs).length,
        )}
        onPendingClick={() => openDiscoverAwaiting()}
        discoverOwnsSearch={tab === "browse"}
        deskStatus={
          usingSeed
            ? health?.status === "ok"
              ? "empty"
              : "demo"
            : health?.status === "ok"
              ? "synced"
              : health?.status === "degraded"
                ? "cached"
                : health?.status === "demo"
                  ? "demo"
                  : !health
                    ? "unknown"
                    : datasets.length > 0
                      ? "cached"
                      : "offline"
        }
        refreshedAt={deskRefreshedAt}
      />
      <V2Sidebar tab={tab} onTabChange={goTab} />
      <main className="yzu-main rd-v2-shell-main">
        {main}
        <PreviewModal
          open={previewOpen}
          dataset={previewTarget || detail}
          mode={previewMode}
          usingSeed={usingSeed}
          onAskAbout={() => setRailTab("ask")}
          onClose={() => {
            setPreviewOpen(false);
            setPreviewTarget(null);
            setPreviewMode("lab");
            syncUrl({ preview: false });
          }}
        />
      </main>
      <InspectorRail
        mainTab={tab}
        railTab={railTab}
        onRailTabChange={setRailTab}
        dataset={detail}
        detailLoading={tab === "profile" || tab === "settings" ? false : detailLoading}
        clusterContext={clusterContext}
        browseTarget={browseTarget}
        resourceRow={resourceRow}
        resourcesRollup={resourcesRollup}
        activeObject={activeObject}
        onPreview={() => detail && openPreview(detail)}
        onAskAbout={askAboutSelection}
        onViewActivity={(filter) => {
          setResourceMode("activity");
          setActivityFilter(filter);
          setRailTab("detail");
        }}
        onSeeCluster={CLUSTER_NAV_DEFERRED ? undefined : () => goTab("cluster")}
        onAddToLab={askAddToLab}
        onProbeSource={probeDiscoverCandidate}
        probeState={browseProbeState}
        collectState={browseCollectState}
        jobs={jobs}
        discoverDestination={discoverDestination}
        discoverDestinationOptions={discoverDestinationOptions}
        onDiscoverDestinationChange={handleDiscoverDestinationChange}
        catalog={catalog}
        profile={profile}
        selectedProfileWork={selectedProfileWork}
        onClearProfileWork={() => setSelectedProfileWork(null)}
        onGoTab={goTab}
        settingsGroup={settingsGroup}
        onSettingsFocusGroup={(id) => {
          setSettingsGroup(id);
          setRailTab("detail");
        }}
        health={health}
        browsePeerRows={browsePeerRows}
        onSelectBrowsePeer={selectBrowseRow}
        onApproveSafeJobs={handleApproveSafeJobs}
        onOpenDiscoverAwaiting={openDiscoverAwaiting}
        onOpenInLibrary={openInLibraryFromDiscover}
        labIds={labIds}
        onPreviewExternal={() => browseRow && openPreviewExternal(browseRow)}
        onApproveJob={handleApproveJob}
        onRefresh={refreshBackend}
        onStartLibraryUpload={(folder) => startLibraryIntake("upload", folder)}
        onStartLibraryUrl={(folder) => startLibraryIntake("url", folder)}
        onStartLibraryProcure={(folder) => startLibraryIntake("procure", folder)}
        onSubmitLibraryUpload={submitLibraryUpload}
        onSubmitLibraryUrl={submitLibraryUrl}
        onSubmitLibraryProcure={submitLibraryProcure}
        askPanel={
          <AskRail
            dataset={
              tab === "resources" && resourceRow
                ? {
                    title: `Resources · ${resourceRow.label}`,
                  }
                : tab === "browse"
                  ? activeObject?.kind === "history_event"
                    ? { title: `History · ${activeObject.title}` }
                    : browseTarget
                : tab === "home" && activeObject?.kind === "home_attention"
                  ? {
                      title: `Home · ${activeObject.title}`,
                    }
                : activeObject?.kind === "library_folder" || activeObject?.kind === "library_intake"
                  ? {
                      title: `Library · ${activeObject.title}`,
                    }
                : tab === "profile"
                  ? {
                      title: selectedProfileWork?.title
                        ? `Work · ${selectedProfileWork.title}`
                        : profile?.name_en && !profile.unknown
                          ? `Profile · ${profile.name_en}`
                          : "Profile",
                    }
                : tab === "settings"
                  ? { title: "Settings" }
                : detail
            }
            mainTab={tab}
            searchQuery={searchQuery}
            pendingMessage={pendingAsk}
            onPendingConsumed={() => setPendingAsk("")}
            onCollected={refreshBackend}
            onApproveJob={handleApproveJob}
            onToast={showToast}
            railContext={railContext}
          />
        }
      />
      <Toast toast={toast} />
    </div>
  );
}
