import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { V2DeskHeader } from "@/v2/V2DeskHeader";
import {
  approveJob,
  cancelJob,
  craftCollectPlan,
  collectSynthesisMissingEvidence,
  createDiscoverIntent,
  describeDataset,
  deskHealth,
  deskResources,
  deskWarm,
  ensureDeskSession,
  discoverHistory,
  facultyProfile,
  getSynthesisDiscoverHandoff,
  libraryOps,
  libraryOverview,
  linkSynthesisConversation,
  listAcquisitions,
  listDatasets,
  listJobs,
  listPartitions,
  probePublicSource,
  reviewDiscoverIntent,
  selectDiscoverIntentRoute,
  setDiscoverIntentProposal,
  submitDiscoverIntent,
  submitLibraryJob,
  submitLibraryUrl as submitLibraryUrlIntake,
  procurementCatalogSummary,
  submitDiscoverCollect,
  yzuClusterStatus,
} from "@/v2/api";
import { AskRail } from "@/v2/AskRail";
import {
  datasetObject,
  discoverHistoryObject,
  externalCandidateObject,
  homeAttentionObject,
  libraryIntakeObject,
  resourceObject,
  synthesisDiscoverHandoffObject,
  synthesisThreadObject,
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
import { ResearchContextOverlay } from "@/v2/ResearchContextOverlay";
import { SettingsPage } from "@/v2/SettingsPage";
import { SynthesisPage } from "@/v2/SynthesisPage";
import {
  buildDiscoverLifecycle,
  isLifecycleActive,
  resourceRowForJob,
} from "@/v2/discoverLifecycle";
import { Toast, useToast } from "@/v2/toast";
import { V2Sidebar } from "@/v2/V2Sidebar";
import { recentDatasets, touchRecent } from "@/v2/recent";
import { displayName } from "@/v2/datasetMeta";
import { buildLab, PILOT_PREVIEW_EMAIL } from "@/v2/profileViewModel";
import { mergeHealth, resolveCatalog } from "@/v2/deskSeed";
import { buildDeskIntegrationChips } from "@/v2/deskIntegration";
import { loadSettings } from "@/v2/settingsStore";
import { CLUSTER_NAV_DEFERRED } from "@/v2/nav-config.jsx";
import {
  buildAddToLabDisplayText,
  buildAddToLabPrompt,
  discoverCandidateUrl,
} from "@/v2/discoverActions";
import { candidateKey } from "@/v2/candidateKey";
import { buildVerifiedConnectorProposal, decideDiscoverCollection } from "@/v2/discoverCollectionDecision";
import { classifyLibraryIntakeTarget } from "@/v2/libraryIntake";
import { durableHistoryToEvents, mergeHistoryEvents } from "@/v2/discoverAdapters";
import { discoverModeFromLegacy, discoverModeToUrlState } from "@/v2/discoverMode";
import { jobToDiscoverHistoryEvent, pendingApprovalJobs } from "@/v2/procurementJobs";
import { discoverCandidateState } from "@/v2/browseMeta";
import { buildRailContext } from "@/v2/railContext";

function readParams() {
  const p = new URLSearchParams(window.location.search);
  const rawTab = p.get("tab") || loadSettings().defaultTab || "home";
  const folder = p.get("folder") || "";
  const q = p.get("q") || "";
  let tab = rawTab === "discover" ? "browse" : rawTab;
  // Library deep links: folder+dataset without a Discover query belong on Library.
  if (tab === "browse" && folder && !q) {
    tab = "library";
  }
  const discoverState = discoverModeFromLegacy(p.get("mode") || "");
  return {
    tab,
    dataset: p.get("dataset") || "",
    folder,
    preview: p.get("preview") === "1",
    q,
    discoverMode: discoverState.mode,
    discoverFocusAwaiting: discoverState.focusAwaiting,
    synthesisThreadId: p.get("synthesis_thread") || "",
    synthesisEvidenceId: p.get("synthesis_evidence") || "",
  };
}

function writeParams({ tab, dataset, folder, preview, q, mode, synthesisThreadId, synthesisEvidenceId }) {
  const p = new URLSearchParams();
  if (tab && tab !== "home") p.set("tab", tab);
  if (folder) p.set("folder", folder);
  if (dataset) p.set("dataset", dataset);
  if (preview) p.set("preview", "1");
  if (q) p.set("q", q);
  const modeUrl = discoverModeToUrlState(mode || "explore");
  if (tab === "browse" && modeUrl) p.set("mode", modeUrl);
  if (tab === "browse" && synthesisThreadId) p.set("synthesis_thread", synthesisThreadId);
  if (tab === "browse" && synthesisEvidenceId) p.set("synthesis_evidence", synthesisEvidenceId);
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
  const [browseProbe, setBrowseProbe] = useState({ candidateKey: "", loading: false, result: null, error: "" });
  const [browseIntent, setBrowseIntent] = useState(null);
  const [browseIntentBusy, setBrowseIntentBusy] = useState(false);
  const [collectSubmittingKey, setCollectSubmittingKey] = useState("");
  const [lifecycleRefreshFailed, setLifecycleRefreshFailed] = useState(false);
  const lifecycleLastKnownRef = useRef(null);
  const jobsPollRef = useRef(null);
  /** Candidate-bound probe stamps for Discover taxonomy (survives selection changes). */
  const [probeSnapshots, setProbeSnapshots] = useState({});
  /** Race-safe selected Discover identity — updated on selection, read after async probe. */
  const browseSelectedKeyRef = useRef("");
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
  const [researchContextOpen, setResearchContextOpen] = useState(false);
  const accountTriggerRef = useRef(null);
  /** Unbound desk still binds sidebar Active research from EXAMPLE pilot (same as Profile). */
  const [pilotProfile, setPilotProfile] = useState(null);
  /** Bump when touchRecent runs so sidebar Recent recomputes (localStorage alone does not). */
  const [recentEpoch, setRecentEpoch] = useState(0);
  const [searchQuery, setSearchQuery] = useState(() => readParams().q);
  const [discoverMode, setDiscoverMode] = useState(() => readParams().discoverMode || "explore");
  const [discoverFocusAwaiting, setDiscoverFocusAwaiting] = useState(() => Boolean(readParams().discoverFocusAwaiting));
  const [historyEvents, setHistoryEvents] = useState([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState("");
  const [synthesisDiscoverHandoff, setSynthesisDiscoverHandoff] = useState(null);
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
  const [resourcesRefreshedAt, setResourcesRefreshedAt] = useState(null);
  const [resourceMode, setResourceMode] = useState("sources");
  const [activityFilter, setActivityFilter] = useState(null);
  const [pendingAsk, setPendingAsk] = useState("");
  const [focusSynthesisThreadId, setFocusSynthesisThreadId] = useState("");
  const { toast, show: showToast, dismissIf: dismissToastIf } = useToast();

  const reloadProfile = useCallback(() => {
    const email = loadUserEmail();
    facultyProfile(email)
      .then((data) => {
        if (!data?.found || !data.profile || data.profile.unknown) {
          setProfile({ email, unknown: true });
          return;
        }
        setProfile(data.profile);
      })
      .catch(() => setProfile({ email, unknown: true }));
  }, []);

  const openResearchContext = useCallback((trigger) => {
    accountTriggerRef.current = trigger || null;
    setResearchContextOpen(true);
  }, []);

  const clearResearchContext = useCallback(() => {
    window.localStorage.removeItem("procure_user_email");
    window.localStorage.removeItem("rd_v2_settings.email");
    reloadProfile();
    showToast("Research context cleared");
  }, [reloadProfile, showToast]);

  useEffect(() => {
    if (profile && !profile.unknown) {
      setPilotProfile(null);
      return undefined;
    }
    let cancelled = false;
    facultyProfile(PILOT_PREVIEW_EMAIL)
      .then((data) => {
        if (cancelled) return;
        if (data?.found && data.profile && !data.profile.unknown) setPilotProfile(data.profile);
      })
      .catch(() => {
        if (!cancelled) setPilotProfile(null);
      });
    return () => {
      cancelled = true;
    };
  }, [profile]);

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

  const refreshBackend = useCallback((opts = {}) => {
    const preserveJob = opts?.preserveJob || null;
    listDatasets()
      .then((rows) => applyCatalog(rows))
      .catch(async (err) => {
        try {
          const h = await deskHealth(true);
          if (h?.status === "ok") {
            const rows = await listDatasets();
            applyCatalog(rows);
            return;
          }
        } catch {
          /* fall through to demo seed */
        }
        applyCatalog([], err.message);
      });
    deskHealth(true)
      .then((h) => setHealth(mergeHealth(h)))
      .catch(() => deskHealth().then((h) => setHealth(mergeHealth(h))).catch(() => setHealth(mergeHealth(null))));
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
      .then((rows) => {
        const list = Array.isArray(rows) ? rows : [];
        if (preserveJob?.id && !list.some((j) => j?.id === preserveJob.id)) {
          setJobs([preserveJob, ...list]);
        } else {
          setJobs(list);
        }
        setLifecycleRefreshFailed(false);
      })
      .catch(() => {
        setLifecycleRefreshFailed(true);
      });
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
    discoverHistory({ limit: 50 })
      .then((data) => setHistoryEvents(mergeHistoryEvents(durableHistoryToEvents(data), [])))
      .catch(() => {});
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
        return true;
      } catch (err) {
        showToast(err.message || "Approve failed", "error");
        return false;
      }
    },
    [refreshBackend, showToast],
  );

  const handleCancelJob = useCallback(async (jobId) => {
    if (!jobId) return false;
    try {
      await cancelJob(jobId);
      await refreshBackend();
      showToast("Job cancelled");
      return true;
    } catch (error) {
      showToast(error?.message || "Could not cancel this job");
      return false;
    }
  }, [refreshBackend, showToast]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await ensureDeskSession().catch(() => ({ ok: false }));
      if (cancelled) return;
      // Protected desk reads must follow cookie bootstrap. Starting them in a
      // separate effect races the initial session and creates avoidable 401s.
      refreshBackend();
      deskWarm({ userEmail: loadUserEmail(), background: true }).catch(() => {});
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshBackend]);

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
    // Do not touchRecent here — Home auto-select must not rewrite recent history.
    writeParams({ tab, folder: folderId, dataset: pick, preview: previewOpen });
  }, [datasets, selectedId, tab, folderId, previewOpen]);

  const catalog = datasets;

  const labIds = useMemo(() => new Set(catalog.map((d) => d.dataset_id)), [catalog]);

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

  const browseTarget = browseRow;
  const browseSelectedId = browseRow ? candidateKey(browseRow) : "";
  const historyItems = useMemo(() => {
    const durableJobIds = new Set(
      historyEvents
        .map((event) => event?.meta?.job_id || event?.job_id)
        .filter(Boolean),
    );
    const jobEvents = jobs
      .filter((job) => job?.id && !durableJobIds.has(job.id))
      .map(jobToDiscoverHistoryEvent)
      .filter(Boolean);
    return mergeHistoryEvents(historyEvents, jobEvents);
  }, [historyEvents, jobs]);
  const selectedHistoryEvent = useMemo(
    () => historyItems.find((event) => event?.id === selectedHistoryId) || null,
    [historyItems, selectedHistoryId],
  );
  const selectedHistoryJob = useMemo(() => {
    const jobId = selectedHistoryEvent?.meta?.job_id || selectedHistoryEvent?.job_id || "";
    return jobs.find((job) => job?.id === jobId) || null;
  }, [jobs, selectedHistoryEvent]);
  const browseProbeState =
    browseProbe.candidateKey && browseProbe.candidateKey === candidateKey(browseTarget)
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
      buildRailContext({
        tab,
        mode: railTab,
        dataset: detail,
        activeObject,
        searchQuery,
        folderId,
        clusterContext,
        profileEmail: profile?.email || loadUserEmail(),
      }),
    [tab, railTab, detail, activeObject, searchQuery, folderId, clusterContext, profile],
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
      const next = {
        tab: nextTab,
        folder: patch.folder ?? folderId,
        dataset: patch.dataset ?? selectedId,
        preview: patch.preview ?? previewOpen,
        q: nextQ,
        mode: patch.mode !== undefined ? patch.mode : discoverMode,
      synthesisThreadId: patch.synthesisThreadId || "",
      synthesisEvidenceId: patch.synthesisEvidenceId || "",
      };
      writeParams(next);
    },
    [tab, folderId, selectedId, previewOpen, searchQuery, discoverMode],
  );

  const setDiscoverModeSafe = useCallback(
    (rawMode) => {
      const nextState = discoverModeFromLegacy(rawMode);
      setDiscoverMode(nextState.mode);
      setDiscoverFocusAwaiting(nextState.focusAwaiting);
      if (nextState.mode === "history") {
        setBrowseRow(null);
        setActiveObject((current) => (current?.kind === "external_candidate" ? null : current));
        setRailTab("detail");
      } else {
        setSelectedHistoryId("");
        setActiveObject((current) => (current?.kind === "discover_history" ? null : current));
      }
      syncUrl({ tab: "browse", q: searchQuery.trim(), mode: nextState.mode });
    },
    [searchQuery, syncUrl],
  );

  const openDiscoverAwaiting = useCallback(
    ({ job = null, focusAwaiting = true } = {}) => {
      setDiscoverMode("history");
      setDiscoverFocusAwaiting(false);
      setTab("browse");
      setRailTab("detail");
      syncUrl({ tab: "browse", q: searchQuery.trim(), mode: "history" });
      const targetJob =
        (job?.id ? jobs.find((j) => j.id === job.id) : null) ||
        job ||
        (focusAwaiting ? pendingApprovalJobs(jobs)[0] : null);
      if (targetJob) {
        const event = jobToDiscoverHistoryEvent(targetJob);
        setBrowseRow(null);
        setSelectedHistoryId(event?.id || "");
        setActiveObject(discoverHistoryObject(event));
      } else {
        setBrowseRow(null);
        setSelectedHistoryId("");
        setActiveObject(null);
      }
    },
    [jobs, syncUrl, searchQuery],
  );

  // Durable Discover History (optional endpoint — ignore failures).
  useEffect(() => {
    if (tab !== "browse") return undefined;
    let cancelled = false;
    discoverHistory({ limit: 50 })
      .then((data) => {
        if (cancelled) return;
        setHistoryEvents(mergeHistoryEvents(durableHistoryToEvents(data), []));
      })
      .catch(() => {
        if (!cancelled) setHistoryEvents((cur) => cur);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, jobs]);


  const goTab = useCallback(
    (id, opts = {}) => {
      if (id === "library") {
        setTab(id);
        setRailTab("detail");
        if (opts.keepSelection) {
          syncUrl({ tab: id, preview: false });
          return;
        }
        setSelectedId("");
        setDetail(null);
        setPreviewOpen(false);
        setPreviewTarget(null);
        setActiveObject(null);
        syncUrl({ tab: id, dataset: "", preview: false });
        return;
      }
      setTab(id);
      syncUrl({ tab: id });
    },
    [syncUrl],
  );

  const routeSynthesisHandoff = useCallback(
    ({ field, handoff, thread }) => {
      const evidenceLabel = field?.label || field?.dataset_id || "selected evidence";
      const objective = handoff?.objective || thread?.objective || "";
      const grain = handoff?.required_grain || "";
      const query = [evidenceLabel, grain].filter(Boolean).join(" ");
      const durableHandoff = {
        thread_id: thread?.id || handoff?.thread_id || "",
        thread_title: thread?.title || "",
        objective,
        required_grain: grain,
        selected_field: {
          id: field?.id || field?.dataset_id || "",
          label: evidenceLabel,
          status: field?.status || "",
          role: field?.role || field?.eyebrow || "",
          grain: field?.grain || "",
          coverage: field?.coverage || "",
          interpretation: field?.interpretation || "",
        },
        held_evidence: handoff?.held_evidence || [],
        missing_evidence: handoff?.missing_evidence || [],
        collect_intents: handoff?.collect_intents || [],
        fake_collection: false,
      };
      setSynthesisDiscoverHandoff(durableHandoff);
      setSearchQuery(query);
      setBrowseRow(null);
      setBrowseProbe({ candidateKey: "", loading: false, result: null, error: "" });
      setActiveObject(synthesisDiscoverHandoffObject(durableHandoff));
      setRailTab("detail");
      setTab("browse");
      syncUrl({
        tab: "browse",
        q: query,
        mode: "explore",
        synthesisThreadId: durableHandoff.thread_id,
        synthesisEvidenceId: durableHandoff.selected_field.id,
      });
    },
    [syncUrl],
  );

  const returnToSynthesis = useCallback(() => {
    const threadId = synthesisDiscoverHandoff?.thread_id;
    if (!threadId) return;
    setFocusSynthesisThreadId(threadId);
    setSynthesisDiscoverHandoff(null);
    setRailTab("detail");
    setTab("synthesis");
    syncUrl({ tab: "synthesis" });
  }, [synthesisDiscoverHandoff, syncUrl]);

  const submitSynthesisHandoffCollection = useCallback(async () => {
    const handoff = synthesisDiscoverHandoff;
    const threadId = handoff?.thread_id;
    const evidenceId = handoff?.selected_field?.id;
    if (!threadId || !evidenceId) return;
    try {
      const out = await collectSynthesisMissingEvidence(threadId, { evidenceIds: [evidenceId] });
      const submitted = Array.isArray(out?.submitted) ? out.submitted : [];
      if (!submitted.length) {
        const reason = out?.skipped?.[0]?.reason || "no resolvable collection route";
        showToast(`This evidence gap cannot be requested yet: ${reason}`);
        return;
      }
      refreshBackend();
      showToast(`Evidence request submitted — ${submitted.length} approval-gated job${submitted.length === 1 ? "" : "s"} created`);
    } catch (error) {
      showToast(error?.message || "Could not request this Synthesis evidence");
    }
  }, [refreshBackend, showToast, synthesisDiscoverHandoff]);

  const linkActiveSynthesisConversation = useCallback(
    ({ sessionId, conversationId } = {}) => {
      const threadId =
        activeObject?.kind === "synthesis_thread" ? activeObject.thread?.id || activeObject.id : "";
      if (!threadId || !sessionId) return;
      linkSynthesisConversation(threadId, { sessionId, conversationId }).catch(() => {
        showToast("Conversation continued, but could not be linked to the Synthesis thread");
      });
    },
    [activeObject, showToast],
  );

  useEffect(() => {
    const route = readParams();
    if (
      tab !== "browse" ||
      !route.synthesisThreadId ||
      !route.synthesisEvidenceId ||
      synthesisDiscoverHandoff?.thread_id === route.synthesisThreadId &&
        synthesisDiscoverHandoff?.selected_field?.id === route.synthesisEvidenceId
    ) {
      return;
    }
    let cancelled = false;
    getSynthesisDiscoverHandoff(route.synthesisThreadId)
      .then((handoff) => {
        if (cancelled) return;
        const field = (handoff?.missing_evidence || []).find(
          (item) => String(item?.id || item?.evidence_id || item?.dataset_id || "") === route.synthesisEvidenceId,
        );
        if (!field) return;
        const durableHandoff = {
          thread_id: route.synthesisThreadId,
          objective: handoff.objective || "",
          required_grain: handoff.required_grain || "",
          selected_field: {
            id: route.synthesisEvidenceId,
            label: field.label || field.dataset_id || "Selected evidence",
            status: field.status || "missing",
            role: field.role || "",
            grain: field.grain || "",
            coverage: field.coverage || "",
            interpretation: field.interpretation || "",
          },
          held_evidence: handoff.held_evidence || [],
          missing_evidence: (handoff.missing_evidence || []).filter(
            (item) => String(item?.id || item?.evidence_id || item?.dataset_id || "") === route.synthesisEvidenceId,
          ),
          collect_intents: (handoff.collect_intents || []).filter(
            (item) => String(item?.id || item?.evidence_id || item?.dataset_id || "") === route.synthesisEvidenceId,
          ),
          fake_collection: false,
        };
        setSynthesisDiscoverHandoff(durableHandoff);
        setActiveObject(synthesisDiscoverHandoffObject(durableHandoff));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [tab, synthesisDiscoverHandoff]);

  const selectDataset = useCallback(
    (row) => {
      const id = row?.dataset_id || row?.id;
      if (!id) return;
      setSelectedId(id);
      setDetail(row);
      setActiveObject(datasetObject(row));
      touchRecent(id);
      setRecentEpoch((n) => n + 1);
      setRailTab(loadSettings().onSelect === "ask" ? "ask" : "detail");
      syncUrl({ dataset: id, preview: false });
      setPreviewOpen(false);
    },
    [syncUrl],
  );

  /** Home Continue / Recent — land Library with asset rail in one write (no clear-then-select race). */
  const openLibraryDataset = useCallback(
    (row) => {
      const id = row?.dataset_id || row?.id;
      if (!id) {
        goTab("library");
        return;
      }
      setTab("library");
      setSelectedId(id);
      setDetail(row);
      setActiveObject(datasetObject(row));
      setPreviewOpen(false);
      setPreviewTarget(null);
      touchRecent(id);
      setRecentEpoch((n) => n + 1);
      setRailTab(loadSettings().onSelect === "ask" ? "ask" : "detail");
      syncUrl({ tab: "library", dataset: id, preview: false });
    },
    [goTab, syncUrl],
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
      setRecentEpoch((n) => n + 1);
      setPreviewOpen(true);
      setRailTab("detail");
      syncUrl({ dataset: id, preview: true });
    },
    [selectedId, selectedFromList, syncUrl],
  );

  const openPreviewExternal = useCallback((row) => {
    if (!row) return;
    browseSelectedKeyRef.current = candidateKey(row);
    setBrowseRow(row);
    setActiveObject(externalCandidateObject(row));
    setPreviewTarget(row);
    setPreviewMode("external");
    setPreviewOpen(true);
    setRailTab("detail");
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

  const askAddToLab = useCallback(
    async (target) => {
      if (!target) return;
      const state = target.discover_state || discoverCandidateState(target, labIds);
      if (state.key === "in_lab") {
        const id = target.dataset_id;
        if (!id) return;
        setTab("library");
        const row = catalog.find((d) => d.dataset_id === id) || { dataset_id: id, ...target };
        setSelectedId(id);
        setDetail(row);
        setActiveObject(datasetObject(row));
        touchRecent(id);
        setRecentEpoch((n) => n + 1);
        setRailTab("detail");
        syncUrl({ tab: "library", dataset: id, preview: false, q: "" });
        showToast("Opened in Library");
        return;
      }

      const key = candidateKey(target);
      if (collectSubmittingKey && collectSubmittingKey === key) return;

      setActiveObject(externalCandidateObject(target));
      setBrowseRow(target);
      browseSelectedKeyRef.current = key;

      const probeResult = browseProbe.candidateKey === key ? browseProbe.result : null;
      const decision = decideDiscoverCollection({ candidate: target, probe: probeResult });
      const connectorId = decision.connectorId;

      if (decision.kind === "direct" && connectorId) {
        setCollectSubmittingKey(key);
        setRailTab("detail");
        try {
          const out = await submitDiscoverCollect(connectorId, {
            limit: 200,
            autoApprove: false,
            candidateKey: key,
            sourceIdentity: target?.source || target?.collect_via || "",
            datasetId: target?.dataset_id || "",
            doi: target?.doi || "",
            url: discoverCandidateUrl(target) || "",
          });
          const job = out?.job;
          if (job) {
            setJobs((prev) => {
              const others = (Array.isArray(prev) ? prev : []).filter((j) => j?.id !== job.id);
              return [job, ...others];
            });
          }
          setLifecycleRefreshFailed(false);
          // Refresh catalog/ops, but preserve the exact submitted job if listJobs
          // has not indexed it yet (common race right after collect).
          refreshBackend({ preserveJob: job || null });
          setRailTab("detail");
          showToast(
            job?.status === "pending_approval"
              ? "Collection submitted — approval required"
              : "Collection job queued — track it in Resources",
          );
        } catch (err) {
          setRailTab("ask");
          setPendingAsk({
            prompt: buildAddToLabPrompt(target, probeResult),
            displayText: buildAddToLabDisplayText(target, probeResult),
          });
          showToast(err?.message || "Collect failed — queued Ask instead");
        } finally {
          setCollectSubmittingKey("");
        }
        return;
      }

      setCollectSubmittingKey(key);
      try {
        let intent = await createDiscoverIntent({
          researchNeed: searchQuery || target?.title || target?.name || "Evaluate this source for collection",
          title: target?.title || target?.name || target?.dataset_id || "",
          candidate: {
            ...target,
            candidate_key: key,
            probe_snapshot: probeResult || undefined,
          },
        });
        const proposal = buildVerifiedConnectorProposal({ candidate: target, probe: probeResult });
        if (proposal && intent?.id) {
          intent = await setDiscoverIntentProposal(intent.id, proposal);
        }
        setBrowseIntent({ ...intent, reason: decision.reason || "" });
        setRailTab("detail");
        showToast(
          proposal
            ? "Acquisition brief ready — review its route before submitting"
            : "Acquisition brief saved — a verified route is still required",
        );
      } catch (err) {
        showToast(err?.message || "Could not create an acquisition brief");
      } finally {
        setCollectSubmittingKey("");
      }
    },
    [
      labIds,
      browseProbe,
      catalog,
      syncUrl,
      showToast,
      refreshBackend,
      collectSubmittingKey,
      searchQuery,
    ],
  );

  const craftPublicUrlPlan = useCallback(
    async (url) => {
      const target = String(url || "").trim();
      if (!target) return;
      try {
        const crafted = await craftCollectPlan({
          researchNeed: `Craft a generic collect plan for ${target}`,
          url: target,
        });
        const plan = crafted?.plan || crafted;
        if (!plan || typeof plan !== "object") {
          throw new Error("Craft returned no collect plan");
        }
        const out = await submitLibraryJob({
          title: plan.title || `Craft collect · ${target}`,
          plan,
          autoApprove: false,
          request: {
            craft: true,
            url: target,
            rationale: crafted?.rationale,
          },
        });
        const job = out?.job || out;
        if (job?.id) {
          setJobs((current) => [job, ...(current || []).filter((row) => row?.id !== job.id)]);
        }
        refreshBackend({ preserveJob: job || null });
        setDiscoverModeSafe("history");
        goTab("browse");
        showToast(
          job?.status === "pending_approval"
            ? "Crafted collect plan — approval required"
            : "Crafted collect plan queued",
        );
      } catch (error) {
        setRailTab("ask");
        setPendingAsk({
          prompt: `Craft a generic collect plan for this public URL (HTTP or scrape — not a named vendor module): ${target}`,
          displayText: `Craft collect for ${target}`,
        });
        showToast(error?.message || "Could not craft a collection plan");
      }
    },
    [refreshBackend, showToast, setDiscoverModeSafe, goTab],
  );

  const probeDiscoverCandidate = useCallback(async (target) => {
    const url = discoverCandidateUrl(target);
    const key = candidateKey(target);
    if (!url) {
      setBrowseProbe({ candidateKey: key, loading: false, result: null, error: "No public URL to probe for this candidate." });
      return;
    }
    setBrowseProbe({ candidateKey: key, loading: true, result: null, error: "" });
    try {
      const out = await probePublicSource(url, target?.title || target?.name || "", { candidateKey: key });
      // Ignore stale responses if selection changed mid-flight (ref is race-safe).
      const stillSelected = browseSelectedKeyRef.current === key;
      if (out?.error) {
        if (stillSelected) {
          setBrowseProbe({ candidateKey: key, loading: false, result: null, error: String(out.error) });
        }
        return;
      }
      const stamped = { ...out, candidate_key: key };
      // Stamp probe on the candidate even if selection moved — taxonomy needs bound evidence.
      setProbeSnapshots((prev) => ({ ...prev, [key]: stamped }));
      if (!stillSelected) return;
      setBrowseProbe({ candidateKey: key, loading: false, result: stamped, error: "" });
      setBrowseRow((current) =>
        current && candidateKey(current) === key
          ? { ...current, probe_snapshot: stamped }
          : current,
      );
      const label = String(target?.title || target?.name || target?.dataset_id || "Source").trim();
      showToast(`${label} probed — review verified evidence`, {
        scope: "discover-probe",
        candidateKey: key,
      });
    } catch (err) {
      if (browseSelectedKeyRef.current !== key) return;
      setBrowseProbe({
        candidateKey: key,
        loading: false,
        result: null,
        error: err?.message || "Probe failed",
      });
    }
  }, [showToast]);

  const browseLifecycle = useMemo(() => {
    const key = browseTarget ? candidateKey(browseTarget) : "";
    const submitting = Boolean(key && collectSubmittingKey === key);
    const prior = lifecycleLastKnownRef.current;
    const lastKnown =
      prior && key && prior.candidateKey === key ? prior : null;
    const life = buildDiscoverLifecycle({
      row: browseTarget,
      jobs,
      catalog,
      labIds,
      submitting,
      refreshFailed: lifecycleRefreshFailed,
      lastKnown,
    });
    if (life && life.state !== "submitting") {
      lifecycleLastKnownRef.current = life;
    }
    if (!browseTarget) lifecycleLastKnownRef.current = null;
    return life;
  }, [browseTarget, jobs, catalog, labIds, collectSubmittingKey, lifecycleRefreshFailed]);

  const trackJobInResources = useCallback(
    (jobOrTarget) => {
      const job = jobOrTarget?.id && jobOrTarget?.status ? jobOrTarget : browseLifecycle?.job;
      const row = resourceRowForJob(job);
      if (!row) {
        goTab("resources");
        setResourceMode("sources");
        return;
      }
      setResourceMode("sources");
      setActivityFilter(null);
      setResourceRow(row);
      setActiveObject(resourceObject(row));
      setRailTab("detail");
      goTab("resources");
    },
    [browseLifecycle, goTab],
  );

  const reviewApprovalInResources = useCallback(
    (jobOrTarget) => {
      // Authority: pending approvals stay in Discover (Explore queue / Detail), not Resources.
      const job = jobOrTarget?.bound_job || jobOrTarget;
      openDiscoverAwaiting({ job: job?.id ? job : null, focusAwaiting: true });
    },
    [openDiscoverAwaiting],
  );

  const retryLifecycleRefresh = useCallback(() => {
    setLifecycleRefreshFailed(false);
    listJobs()
      .then((rows) => {
        setJobs(Array.isArray(rows) ? rows : []);
        setLifecycleRefreshFailed(false);
      })
      .catch(() => setLifecycleRefreshFailed(true));
  }, []);

  const reviewCollectionBrief = useCallback(async (intent, decision) => {
    if (!intent?.id) return;
    setBrowseIntentBusy(true);
    try {
      const next = await reviewDiscoverIntent(intent.id, decision);
      setBrowseIntent((current) => (current?.id === intent.id ? { ...next, reason: current.reason || "" } : current));
      showToast("Collection route accepted — select or submit it when ready");
    } catch (error) {
      showToast(error?.message || "Could not review the collection route");
    } finally {
      setBrowseIntentBusy(false);
    }
  }, [showToast]);

  const selectCollectionBriefRoute = useCallback(async (intent, routeId) => {
    if (!intent?.id || !routeId) return;
    setBrowseIntentBusy(true);
    try {
      const next = await selectDiscoverIntentRoute(intent.id, routeId);
      setBrowseIntent((current) => (current?.id === intent.id ? { ...next, reason: current.reason || "" } : current));
    } catch (error) {
      showToast(error?.message || "Could not select this collection route");
    } finally {
      setBrowseIntentBusy(false);
    }
  }, [showToast]);

  const submitCollectionBrief = useCallback(async (intent) => {
    if (!intent?.id) return;
    setBrowseIntentBusy(true);
    try {
      const out = await submitDiscoverIntent(intent.id);
      const nextIntent = out?.intent || intent;
      const job = out?.job;
      setBrowseIntent((current) => (current?.id === intent.id ? { ...nextIntent, reason: current.reason || "" } : current));
      if (job?.id) {
        setJobs((current) => [job, ...(current || []).filter((row) => row?.id !== job.id)]);
        refreshBackend({ preserveJob: job });
      }
      showToast(job?.status === "pending_approval" ? "Collection submitted — approval required" : "Collection submitted");
    } catch (error) {
      showToast(error?.message || "Could not submit the collection request");
    } finally {
      setBrowseIntentBusy(false);
    }
  }, [refreshBackend, showToast]);

  // Poll jobs while selected Discover candidate has a nonterminal exact job.
  useEffect(() => {
    if (tab !== "browse" || !browseTarget || !isLifecycleActive(browseLifecycle)) {
      if (jobsPollRef.current) {
        window.clearInterval(jobsPollRef.current);
        jobsPollRef.current = null;
      }
      return undefined;
    }
    const tick = () => {
      listJobs()
        .then((rows) => {
          setJobs(Array.isArray(rows) ? rows : []);
          setLifecycleRefreshFailed(false);
        })
        .catch(() => setLifecycleRefreshFailed(true));
    };
    jobsPollRef.current = window.setInterval(tick, 4000);
    return () => {
      if (jobsPollRef.current) {
        window.clearInterval(jobsPollRef.current);
        jobsPollRef.current = null;
      }
    };
  }, [tab, browseTarget, browseLifecycle]);

  const openInLibraryFromDiscover = useCallback(
    (target) => {
      const id = target?.dataset_id;
      if (!id) return;
      setTab("library");
      const row = catalog.find((d) => d.dataset_id === id) || { dataset_id: id, ...target };
      setSelectedId(id);
      setDetail(row);
      setActiveObject(datasetObject(row));
      touchRecent(id);
      setRecentEpoch((n) => n + 1);
      setRailTab("detail");
      syncUrl({ tab: "library", dataset: id, preview: false, q: "" });
    },
    [catalog, syncUrl],
  );

  const askAboutSelection = useCallback(
    (target, promptOverride) => {
      if (tab === "browse" && target) {
        const label = target.title || target.dataset_id || target.name || "this Discover candidate";
        if (target.kind === "discover_history") {
          setRailTab("ask");
          const override = typeof promptOverride === "string" && promptOverride.trim() ? promptOverride.trim() : "";
          setPendingAsk(
            override ||
              {
                prompt: `Explain this Discover lifecycle item: ${label}. Summarize its durable state, what is verified, what is still unknown, and the safest next action. Do not claim collection, registration, or query readiness unless the record proves it.`,
                displayText: `Explain this lifecycle item: ${label}`,
              },
          );
          return;
        }
        setActiveObject(externalCandidateObject(target));
        setRailTab("ask");
        if (promptOverride && typeof promptOverride === "object") {
          setPendingAsk(promptOverride);
          return;
        }
        const override =
          typeof promptOverride === "string" && promptOverride.trim() ? promptOverride.trim() : "";
        setPendingAsk(
          override ||
            {
              prompt: `Assess this Discover source for research use: ${label}. Summarize what is verified, what remains unknown, access/acquisition constraints, and the safest next action. Do not invent legal clearance or query readiness.`,
              displayText: `Assess this source: ${label}`,
            },
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
      setRailTab("ask");
    },
    [tab],
  );

  useEffect(() => {
    setBrowseRow(null);
    browseSelectedKeyRef.current = "";
    setBrowseProbe({ candidateKey: "", loading: false, result: null, error: "" });
    setProbeSnapshots({});
    setActiveObject((current) => (current?.kind === "external_candidate" ? null : current));
    dismissToastIf((t) => t.scope === "discover-probe");
  }, [searchQuery, dismissToastIf]);

  const focusLibraryFolder = useCallback((object) => {
    setActiveObject((current) => {
      if (current?.kind === "library_intake") return current;
      if (current?.kind === "dataset") return current;
      return object;
    });
  }, []);

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

  const submitLibraryUpload = useCallback((files) => {
    const names = Array.from(files || []).map((file) => file.name).filter(Boolean);
    showToast(
      names.length
        ? "Local file staging is not connected yet. Use a URL/DOI or archive the files before requesting intake."
        : "Local file staging is not connected yet.",
    );
  }, [showToast]);

  const submitLibraryUrl = useCallback(
    async (value) => {
      const target = classifyLibraryIntakeTarget(value);
      if (!target) {
        showToast("Enter one valid http(s) URL or DOI.");
        return;
      }
      try {
        const out = await submitLibraryUrlIntake(target);
        const job = out?.job;
        if (job?.id) {
          setJobs((current) => [job, ...(current || []).filter((row) => row?.id !== job.id)]);
          refreshBackend({ preserveJob: job });
        }
        showToast(
          job?.status === "pending_approval"
            ? "Evidence intake submitted — approval required"
            : "Evidence intake submitted",
        );
      } catch (error) {
        showToast(error?.message || "Could not submit evidence intake");
      }
    },
    [refreshBackend, showToast],
  );

  const submitLibraryProcure = useCallback(
    (intake) => {
      const destination = intake?.destination || "this Library branch";
      setSearchQuery(destination);
      setDiscoverModeSafe("explore");
      goTab("browse");
      showToast("Search Discover to evaluate evidence for this Library branch");
    },
    [goTab, setDiscoverModeSafe, showToast],
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
      if (item?.tab === "browse" || item?.discoverMode === "history") {
        setDiscoverModeSafe("history");
        goTab("browse");
        setRailTab("detail");
        return;
      }
      if (item?.tab === "resources" && item.resourceRow) {
        setResourceMode("sources");
        setActivityFilter(null);
        setResourceRow(item.resourceRow);
        setActiveObject(resourceObject(item.resourceRow));
        setRailTab("detail");
        goTab("resources");
        return;
      }
      goTab(item?.tab || "home");
    },
    [goTab, setDiscoverModeSafe],
  );

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
          profile={profile && !profile.unknown ? profile : pilotProfile || profile}
          resourcesRollup={resourcesRollup}
          acquisitions={acquisitions}
          partitions={partitions}
          jobs={jobs}
          usingSeed={usingSeed}
          onAskComposer={askFromPrompt}
          onGoTab={goTab}
          onOpenAttention={openHomeAttention}
          onSelectDataset={openLibraryDataset}
          onPreviewDataset={openPreview}
          onAskAttention={askHomeAttention}
          onSuggestSearch={(q) => {
            setSearchQuery(q);
            goTab("browse");
          }}
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
          catalog={catalog}
          selectedId={browseSelectedId}
          searchQuery={searchQuery}
          jobs={jobs}
          usingSeed={usingSeed}
          probeSnapshots={probeSnapshots}
          discoverMode={discoverMode}
          discoverFocusAwaiting={discoverFocusAwaiting}
          onDiscoverModeChange={setDiscoverModeSafe}
          historyEvents={historyItems}
          selectedHistoryId={selectedHistoryId}
          synthesisHandoff={synthesisDiscoverHandoff}
          onRequestSynthesisEvidence={submitSynthesisHandoffCollection}
          onReturnToSynthesis={returnToSynthesis}
          onDismissSynthesisHandoff={() => {
            setSynthesisDiscoverHandoff(null);
            setActiveObject((current) => (current?.kind === "synthesis_discover_handoff" ? null : current));
            syncUrl({ tab: "browse", q: searchQuery, mode: "explore" });
          }}
          onSelectHistoryEvent={(event) => {
            setSelectedHistoryId(event?.id || "");
            setActiveObject(discoverHistoryObject(event));
            setRailTab("detail");
          }}
          onSuggestSearch={(q) => {
            setSynthesisDiscoverHandoff(null);
            setSearchQuery(q);
            goTab("browse");
          }}
          onCraftUrl={craftPublicUrlPlan}
          onSearchWeb={askSearchWeb}
          onSelectRow={(row) => {
            setSynthesisDiscoverHandoff(null);
            const nextKey = candidateKey(row);
            browseSelectedKeyRef.current = nextKey;
            dismissToastIf(
              (t) => t.scope === "discover-probe" && t.candidateKey && t.candidateKey !== nextKey,
            );
            const stamped =
              probeSnapshots[nextKey] && !row.probe_snapshot
                ? { ...row, probe_snapshot: probeSnapshots[nextKey] }
                : row;
            setBrowseRow(stamped);
            setBrowseIntent(null);
            setBrowseProbe((current) =>
              current.candidateKey === nextKey
                ? current
                : probeSnapshots[nextKey]
                  ? { candidateKey: nextKey, loading: false, result: probeSnapshots[nextKey], error: "" }
                  : { candidateKey: "", loading: false, result: null, error: "" },
            );
            setActiveObject(externalCandidateObject(stamped));
            setRailTab("detail");
          }}
        />
      );
      break;
    case "synthesis":
      main = (
        <SynthesisPage
          datasets={catalog}
          compareIds={compareIds}
          onCompareChange={setCompareIds}
          onAskComposer={askFromPrompt}
          onApproveJob={handleApproveJob}
          onDiscoverHandoff={routeSynthesisHandoff}
          onGoTab={goTab}
          onOpenDataset={openInLibraryFromDiscover}
          onSelectThread={(thread) => {
            setActiveObject(synthesisThreadObject(thread));
            setRailTab("detail");
          }}
          focusThreadId={focusSynthesisThreadId}
          onFocusThreadConsumed={() => setFocusSynthesisThreadId("")}
        />
      );
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
          onGoTab={goTab}
          onProfileRefresh={reloadProfile}
          onSuggestSearch={(q) => {
            setSearchQuery(q);
            setTab("browse");
            syncUrl({ tab: "browse", q });
          }}
        />
      );
      break;
    case "settings":
      main = (
        <SettingsPage
          health={health}
          resourcesRollup={resourcesRollup}
          onProfileRefresh={reloadProfile}
          onToast={showToast}
        />
      );
      break;
    default:
      main = null;
  }

  // Explore is intentionally canvas-first until a researcher selects a row.
  // An explicit wider-source request is different: it deliberately seeds Ask,
  // so keeping the rail hidden would strand the conversation it just opened.
  const hideRail = tab === "browse" && !browseTarget && !selectedHistoryEvent && railTab !== "ask";

  const activeResearch = useMemo(() => {
    const source = profile && !profile.unknown ? profile : pilotProfile;
    const lab = buildLab(source || null);
    const primaryTrack =
      Array.isArray(source?.research_tracks) && source.research_tracks.length
        ? source.research_tracks.find((t) => t?.phase === "active_grant") || source.research_tracks[0]
        : null;
    const trackTitle =
      typeof primaryTrack === "string"
        ? primaryTrack
        : primaryTrack?.title || primaryTrack?.name || "";
    const title =
      (source &&
        (trackTitle ||
          source.research_direction ||
          source.current_research ||
          source.name_en)) ||
      "Active research";
    const emphases = [
      ...(Array.isArray(source?.specialties) ? source.specialties : []),
      ...(Array.isArray(source?.research_emphases) ? source.research_emphases : []),
      ...(Array.isArray(lab?.themes) ? lab.themes : []),
      ...(Array.isArray(source?.themes) ? source.themes : []),
    ]
      .map((item) => (typeof item === "string" ? item : item?.label || item?.name))
      .filter(Boolean)
      .slice(0, 3);
    return { title: String(title).slice(0, 96), emphases };
  }, [profile, pilotProfile]);

  const sidebarRecent = useMemo(
    () =>
      recentDatasets(datasets, 4).map((ds) => ({
        id: ds.dataset_id,
        title: displayName(ds),
        dataset: ds,
      })),
    [datasets, recentEpoch],
  );

  return (
    <div className={`yzu-shell with-inspector rd-theme-light rd-v2-shell${hideRail ? " no-rail" : ""}`}>
      <V2DeskHeader
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSearchSubmit={askFromSearch}
        onAskFromSearch={askFromSearch}
        onBrandClick={() => goTab("home")}
        onRetry={refreshBackend}
        headerInitials="YZ"
        datasetCount={headerDsCount}
        usingSeed={usingSeed}
        workCount={Math.max(
          Number(health?.desk?.jobs?.pending_approval ?? 0),
          pendingApprovalJobs(jobs).length,
        )}
        onPendingClick={() => openDiscoverAwaiting()}
        deskStatus={
          usingSeed
            ? health?.status === "ok"
              ? "empty"
              : "demo"
            : health?.status === "degraded"
              ? "degraded"
              : health?.status === "ok" || datasets.length > 0
                ? "ok"
                : health?.status || "unknown"
        }
        refreshedAt={deskRefreshedAt}
        integrationChips={usingSeed ? [] : buildDeskIntegrationChips(health)}
        activeResearchTitle={activeResearch.title}
        currentPage={tab}
        discoverOwnsSearch={tab === "browse"}
        profile={profile}
        onOpenResearchContext={openResearchContext}
        onClearContext={clearResearchContext}
      />
      <V2Sidebar
        tab={tab}
        onTabChange={goTab}
        activeResearch={activeResearch}
        recentItems={sidebarRecent}
        onOpenRecent={(item) => {
          if (item?.dataset) openLibraryDataset(item.dataset);
        }}
      />
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
      <ResearchContextOverlay
        open={researchContextOpen}
        profile={profile}
        onProfileRefresh={reloadProfile}
        restoreFocusRef={accountTriggerRef}
        onClose={() => setResearchContextOpen(false)}
        onGoTab={(nextTab) => {
          setResearchContextOpen(false);
          goTab(nextTab);
        }}
        onSuggestSearch={(query) => {
          setResearchContextOpen(false);
          setSearchQuery(query);
          goTab("browse");
        }}
        onChangeContext={() => {
          setResearchContextOpen(false);
          goTab("settings");
        }}
      />
      <InspectorRail
        mainTab={tab}
        railTab={railTab}
        onRailTabChange={setRailTab}
        dataset={detail}
        detailLoading={detailLoading}
        clusterContext={clusterContext}
        browseTarget={browseTarget}
        historyEvent={selectedHistoryEvent}
        historyJob={selectedHistoryJob}
        resourceRow={resourceRow}
        resourcesRollup={resourcesRollup}
        activeObject={activeObject}
        profile={profile}
        onPreview={() => detail && openPreview(detail)}
        onAskAbout={askAboutSelection}
        onViewActivity={(filter) => {
          setResourceMode("usage");
          setActivityFilter(filter);
          setRailTab("detail");
        }}
        onSeeCluster={CLUSTER_NAV_DEFERRED ? undefined : () => goTab("cluster")}
        onAddToLab={askAddToLab}
        onProbeSource={probeDiscoverCandidate}
        probeState={browseProbeState}
        onOpenInLibrary={openInLibraryFromDiscover}
        labIds={labIds}
        browseLifecycle={browseLifecycle}
        collectionBrief={browseIntent}
        collectionBriefBusy={browseIntentBusy}
        onReviewCollectionBrief={reviewCollectionBrief}
        onSelectCollectionRoute={selectCollectionBriefRoute}
        onSubmitCollectionBrief={submitCollectionBrief}
        onTrackResources={trackJobInResources}
        onReviewApproval={reviewApprovalInResources}
        onRetryLifecycleRefresh={retryLifecycleRefresh}
        searchQuery={searchQuery}
        catalog={catalog}
        onReviewHistoryRequest={(item) => {
          const job = item?.id && item?.status ? item : selectedHistoryJob;
          if (job) reviewApprovalInResources(job);
        }}
        onPreviewExternal={() => browseRow && openPreviewExternal(browseRow)}
        onApproveJob={handleApproveJob}
        onCancelJob={handleCancelJob}
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
                  ? selectedHistoryEvent
                    ? { ...selectedHistoryEvent, title: selectedHistoryEvent.target || selectedHistoryEvent.title, kind: "discover_history" }
                    : browseTarget
                : tab === "home" && activeObject?.kind === "home_attention"
                  ? {
                      title: `Home · ${activeObject.title}`,
                    }
                : activeObject?.kind === "library_folder" || activeObject?.kind === "library_intake"
                  ? {
                      title: `Library · ${activeObject.title}`,
                    }
                : tab === "synthesis"
                  ? activeObject?.kind === "synthesis_thread"
                    ? { title: activeObject.title, kind: "synthesis_thread" }
                    : { title: "Synthesis studio", kind: "synthesis_thread" }
                : tab === "profile"
                  ? {
                      title:
                        profile?.name_en && !profile.unknown
                          ? `Profile · ${profile.name_en}`
                          : "Profile",
                    }
                : tab === "settings"
                  ? { title: "Desk setup" }
                : detail
            }
            mainTab={tab}
            searchQuery={searchQuery}
            pendingMessage={pendingAsk}
            onPendingConsumed={() => setPendingAsk("")}
            onCollected={refreshBackend}
            onApproveJob={handleApproveJob}
            onToast={showToast}
            onConversation={linkActiveSynthesisConversation}
            railContext={railContext}
          />
        }
      />
      <Toast toast={toast} />
    </div>
  );
}
