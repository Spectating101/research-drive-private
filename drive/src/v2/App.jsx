import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { V2DeskHeader } from "@/v2/V2DeskHeader";
import {
  approveJob,
  describeDataset,
  deskHealth,
  deskResources,
  deskWarm,
  ensureDeskSession,
  discoverHistory,
  facultyProfile,
  libraryOps,
  libraryOverview,
  listAcquisitions,
  listDatasets,
  listJobs,
  listLibraryNav,
  probePublicSource,
  procurementCatalogSummary,
  submitDiscoverCollect,
  submitLibraryJob,
  craftCollectPlan,
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
  synthesisThreadObject,
} from "@/v2/activeObject";
import { BrowsePage } from "@/v2/BrowsePage";
import { ClusterPage } from "@/v2/ClusterPage";
import { computeDatasetOverlap } from "@/v2/clusterOverlap";
import { loadUserEmail, saveUserEmail } from "@/v2/deskSession";
import { readResourcesRollupCache, writeResourcesRollupCache } from "@/v2/resourcesRollupCache";
import { normalizeReleaseTab } from "@/v2/releaseVisibility";
import { HomePage } from "@/v2/HomePage";
import { InspectorRail } from "@/v2/InspectorRail";
import { LibraryPage } from "@/v2/LibraryPage";
import { PreviewModal } from "@/v2/PreviewModal";
import { ProfilePage } from "@/v2/ProfilePage";
import { ResourcesPage } from "@/v2/ResourcesPage";
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
import { displayName, isQueryReadyReadiness } from "@/v2/datasetMeta";
import { buildLab, PILOT_PREVIEW_EMAIL } from "@/v2/profileViewModel";
import { mergeHealth, resolveCatalog } from "@/v2/deskSeed";
import { projectRollupFromHealth } from "@/v2/homeIteration10";
import { buildDeskIntegrationChips } from "@/v2/deskIntegration";
import { loadSettings } from "@/v2/settingsStore";
import { CLUSTER_NAV_DEFERRED } from "@/v2/nav-config.jsx";
import {
  buildAddToLabDisplayText,
  buildAddToLabPrompt,
  discoverCandidateUrl,
} from "@/v2/discoverActions";
import { candidateKey } from "@/v2/candidateKey";
import {
  durableHistoryToEvents,
  enrichHistoryEventsFromJobs,
  mergeHistoryEvents,
} from "@/v2/discoverAdapters";
import { discoverModeFromLegacy, discoverModeToUrlState } from "@/v2/discoverMode";
import { jobToDiscoverHistoryEvent, pendingApprovalJobs } from "@/v2/procurementJobs";
import { discoverCandidateState } from "@/v2/browseMeta";
import { buildRailContext } from "@/v2/railContext";

function readParams() {
  const p = new URLSearchParams(window.location.search);
  const rawTab = p.get("tab") || loadSettings().defaultTab || "home";
  const folder = p.get("folder") || "";
  const q = p.get("q") || "";
  let tab = normalizeReleaseTab(rawTab === "discover" ? "browse" : rawTab);
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
  };
}

function writeParams({ tab, dataset, folder, preview, q, mode }) {
  const p = new URLSearchParams();
  if (tab && tab !== "home") p.set("tab", tab);
  if (folder) p.set("folder", folder);
  if (dataset) p.set("dataset", dataset);
  if (preview) p.set("preview", "1");
  if (q) p.set("q", q);
  const modeUrl = discoverModeToUrlState(mode || "explore");
  if (tab === "browse" && modeUrl) p.set("mode", modeUrl);
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
  /** Unbound desk still binds sidebar Active research from EXAMPLE pilot (same as Profile). */
  const [pilotProfile, setPilotProfile] = useState(null);
  /** Bump when touchRecent runs so sidebar Recent recomputes (localStorage alone does not). */
  const [recentEpoch, setRecentEpoch] = useState(0);
  /** Library header filter only — never shared with Discover. */
  const [librarySearchQuery, setLibrarySearchQuery] = useState("");
  /** Discover page search only — never driven by the header catalog pill. */
  const [discoverSearchQuery, setDiscoverSearchQuery] = useState(() => readParams().q);
  const [discoverMode, setDiscoverMode] = useState(() => readParams().discoverMode || "explore");
  const [discoverFocusAwaiting, setDiscoverFocusAwaiting] = useState(() => Boolean(readParams().discoverFocusAwaiting));
  /** One-shot: Explore should hit live source adapters (Search wider / Ask handoff). */
  const [discoverPreferLive, setDiscoverPreferLive] = useState(false);
  const [historyEvents, setHistoryEvents] = useState([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState("");
  const [loadError, setLoadError] = useState("");
  const [health, setHealth] = useState(null);
  const [deskRefreshedAt, setDeskRefreshedAt] = useState(null);
  const [acquisitions, setAcquisitions] = useState([]);
  const [partitions, setPartitions] = useState([]);
  const [shelves, setShelves] = useState([]);
  const [libraryGuide, setLibraryGuide] = useState(null);
  const [ops, setOps] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [overview, setOverview] = useState(null);
  const [catalogSummary, setCatalogSummary] = useState(null);
  const [cluster, setCluster] = useState(null);
  // Cache-first (same as Resources page) so Home headroom is not blocked on /desk/resources.
  const [resourcesRollup, setResourcesRollup] = useState(() => readResourcesRollupCache() ?? undefined);
  const [resourcesRefreshedAt, setResourcesRefreshedAt] = useState(null);
  const [resourceMode, setResourceMode] = useState("sources");
  const [activityFilter, setActivityFilter] = useState(null);
  const [pendingAsk, setPendingAsk] = useState("");
  const { toast, show: showToast, dismissIf: dismissToastIf } = useToast();

  const reloadProfile = useCallback(() => {
    // Showcase soft-default: keep Kong bound when the browser has no faculty email yet
    // (or after a desk outage wiped the visible identity).
    let email = loadUserEmail();
    if (!email) email = saveUserEmail(PILOT_PREVIEW_EMAIL);
    facultyProfile(email)
      .then((data) => {
        if (!data?.found || !data.profile || data.profile.unknown) {
          // Fall back to pilot bind rather than leaving the desk looking empty.
          if (email !== PILOT_PREVIEW_EMAIL) {
            saveUserEmail(PILOT_PREVIEW_EMAIL);
            facultyProfile(PILOT_PREVIEW_EMAIL)
              .then((pilot) => {
                if (pilot?.found && pilot.profile && !pilot.profile.unknown) {
                  setProfile(pilot.profile);
                } else {
                  setProfile({ email: PILOT_PREVIEW_EMAIL, unknown: true });
                }
              })
              .catch(() => setProfile({ email: PILOT_PREVIEW_EMAIL, unknown: true }));
            return;
          }
          setProfile({ email, unknown: true });
          return;
        }
        setProfile(data.profile);
      })
      .catch(() => {
        if (email !== PILOT_PREVIEW_EMAIL) {
          saveUserEmail(PILOT_PREVIEW_EMAIL);
          facultyProfile(PILOT_PREVIEW_EMAIL)
            .then((pilot) => {
              if (pilot?.found && pilot.profile && !pilot.profile.unknown) {
                setProfile(pilot.profile);
              } else {
                setProfile({ email: PILOT_PREVIEW_EMAIL, unknown: true });
              }
            })
            .catch(() => setProfile({ email: PILOT_PREVIEW_EMAIL, unknown: true }));
          return;
        }
        setProfile({ email, unknown: true });
      });
  }, []);

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
    deskHealth(false)
      .then((h) => {
        const merged = mergeHealth(h);
        setHealth(merged);
        setDeskRefreshedAt(Date.now());
        // Paint Home headroom from /health immediately; full /desk/resources hydrates after.
        setResourcesRollup((cur) => {
          if (cur && typeof cur === "object" && cur.status === "ok") return cur;
          if (cur && cur.usage?.vault?.used_tb != null) return cur;
          return projectRollupFromHealth(merged) || cur;
        });
      })
      .catch(() =>
        deskHealth(false)
          .then((h) => {
            const merged = mergeHealth(h);
            setHealth(merged);
            setDeskRefreshedAt(Date.now());
            setResourcesRollup((cur) => {
              if (cur && typeof cur === "object" && cur.status === "ok") return cur;
              if (cur && cur.usage?.vault?.used_tb != null) return cur;
              return projectRollupFromHealth(merged) || cur;
            });
          })
          .catch(() => setHealth(mergeHealth(null))),
      );
    // Optional live probe — never blank the fast health if it times out.
    deskHealth(true)
      .then((h) => {
        setHealth(mergeHealth(h));
        setDeskRefreshedAt(Date.now());
      })
      .catch(() => {});
    listAcquisitions(true)
      .then((d) => setAcquisitions(d.acquisitions || []))
      .catch(() => setAcquisitions([]));
    listLibraryNav()
      .then((payload) => {
        setPartitions(Array.isArray(payload?.partitions) ? payload.partitions : []);
        setShelves(Array.isArray(payload?.shelves) ? payload.shelves : []);
        setLibraryGuide(payload?.guide && typeof payload.guide === "object" ? payload.guide : null);
      })
      .catch(() => {
        setPartitions([]);
        setShelves([]);
        setLibraryGuide(null);
      });
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
        writeResourcesRollupCache(payload);
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
      } catch (err) {
        showToast(err.message || "Approve failed", "error");
      }
    },
    [refreshBackend, showToast],
  );

  useEffect(() => {
    refreshBackend();
  }, [refreshBackend]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await ensureDeskSession().catch(() => ({ ok: false }));
      if (cancelled) return;
      deskWarm({ userEmail: loadUserEmail(), background: true }).catch(() => {});
    })();
    return () => {
      cancelled = true;
    };
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
        q: tab === "browse" ? discoverSearchQuery.trim() : "",
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

  const pageSearchQuery = tab === "browse" ? discoverSearchQuery : tab === "library" ? librarySearchQuery : "";

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
    const enriched = enrichHistoryEventsFromJobs(historyEvents, jobs);
    const durableJobIds = new Set(
      enriched
        .map((event) => event?.meta?.job_id || event?.job_id)
        .filter(Boolean),
    );
    const jobEvents = jobs
      .filter((job) => job?.id && !durableJobIds.has(job.id))
      .map(jobToDiscoverHistoryEvent)
      .filter(Boolean);
    return mergeHistoryEvents(enriched, jobEvents);
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
        searchQuery: pageSearchQuery,
        folderId,
        clusterContext,
        profileEmail: profile?.email || loadUserEmail(),
      }),
    [tab, railTab, detail, activeObject, pageSearchQuery, folderId, clusterContext, profile],
  );

  const syncUrl = useCallback(
    (patch) => {
      const nextTab = patch.tab ?? tab;
      const nextQ =
        patch.q !== undefined
          ? patch.q
          : nextTab === "browse"
            ? discoverSearchQuery.trim()
            : "";
      const next = {
        tab: nextTab,
        folder: patch.folder ?? folderId,
        dataset: patch.dataset ?? selectedId,
        preview: patch.preview ?? previewOpen,
        q: nextQ,
        mode: patch.mode !== undefined ? patch.mode : discoverMode,
      };
      writeParams(next);
    },
    [tab, folderId, selectedId, previewOpen, discoverSearchQuery, discoverMode],
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
      syncUrl({ tab: "browse", q: discoverSearchQuery.trim(), mode: nextState.mode });
    },
    [discoverSearchQuery, syncUrl],
  );

  const openDiscoverAwaiting = useCallback(
    ({ job = null, focusAwaiting = true } = {}) => {
      setDiscoverMode("history");
      setDiscoverFocusAwaiting(false);
      setTab("browse");
      setRailTab("detail");
      syncUrl({ tab: "browse", q: discoverSearchQuery.trim(), mode: "history" });
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
    [jobs, syncUrl, discoverSearchQuery],
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
      const next = normalizeReleaseTab(id);
      if (next === "library") {
        setTab(next);
        setRailTab("detail");
        if (opts.keepSelection) {
          syncUrl({ tab: next, preview: false });
          return;
        }
        setSelectedId("");
        setDetail(null);
        setPreviewOpen(false);
        setPreviewTarget(null);
        setActiveObject(null);
        syncUrl({ tab: next, dataset: "", preview: false });
        return;
      }
      setTab(next);
      syncUrl({ tab: next });
    },
    [syncUrl],
  );

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

  const askSearchWeb = useCallback(
    (query) => {
      const q = String(query || discoverSearchQuery || "").trim();
      if (!q) return;
      // Force Explore to re-query with live adapters, and brief Ask in parallel.
      setDiscoverPreferLive(true);
      setDiscoverSearchQuery(q);
      goTab("browse");
      syncUrl({ tab: "browse", q });
      setRailTab("ask");
      setPendingAsk(
        `Find external datasets for: ${q}. Start with open-web discovery, probe promising sources, and propose the safest acquisition plan for this lab.`,
      );
    },
    [discoverSearchQuery, goTab, syncUrl],
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
      const connectorId = probeResult?.connector?.connector_id || probeResult?.connector?.id;

      if (connectorId) {
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

      setRailTab("ask");
      setPendingAsk({
        prompt: buildAddToLabPrompt(target, probeResult),
        displayText: buildAddToLabDisplayText(target, probeResult),
      });
      showToast("Queued Ask — Request this evidence");
    },
    [labIds, browseProbe, catalog, syncUrl, showToast, refreshBackend, collectSubmittingKey],
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
          setJobs((prev) => {
            const others = (Array.isArray(prev) ? prev : []).filter((j) => j?.id !== job.id);
            return [job, ...others];
          });
        }
        refreshBackend({ preserveJob: job || null });
        setDiscoverModeSafe("history");
        goTab("browse");
        showToast(
          job?.status === "pending_approval"
            ? "Crafted collect plan — approval required"
            : "Crafted collect plan queued",
        );
      } catch (err) {
        setRailTab("ask");
        setPendingAsk({
          prompt: `Craft a generic collect plan for this public URL (HTTP or scrape — not a named vendor module): ${target}`,
          displayText: `Craft collect for ${target}`,
        });
        showToast(err?.message || "Craft failed — opened Ask instead");
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
  }, [discoverSearchQuery, dismissToastIf]);

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

  const libraryNavHaystack = useMemo(() => {
    const byDataset = new Map();
    const shelfById = new Map((shelves || []).map((s) => [String(s.id || ""), s]));
    for (const lane of partitions || []) {
      const sid = String(lane.shelf_id || "");
      const shelf = shelfById.get(sid);
      const nav = [
        shelf?.label,
        shelf?.blurb,
        lane.professor_label,
        lane.subtitle,
        lane.name,
        lane.professor_blurb,
        lane.scope,
        lane.partition_id,
        lane.detail?.partition_id,
      ]
        .filter(Boolean)
        .join(" ");
      const ids = lane.detail?.registry_dataset_ids || lane.registry_dataset_ids || [];
      for (const id of ids) {
        const key = String(id || "");
        if (!key) continue;
        byDataset.set(key, `${byDataset.get(key) || ""} ${nav}`);
      }
    }
    return byDataset;
  }, [partitions, shelves]);

  const filteredDatasets = useMemo(() => {
    const q = librarySearchQuery.trim().toLowerCase();
    if (!q) return catalog;
    const shelfHitIds = new Set();
    const laneByPid = new Map(
      (partitions || []).map((lane) => [
        String(lane.partition_id || lane.detail?.partition_id || ""),
        lane,
      ]),
    );
    for (const shelf of shelves || []) {
      const blob = `${shelf.label || ""} ${shelf.blurb || ""} ${shelf.id || ""}`.toLowerCase();
      if (!blob.includes(q)) continue;
      for (const pid of shelf.partition_ids || []) {
        const lane = laneByPid.get(String(pid));
        for (const id of lane?.detail?.registry_dataset_ids || lane?.registry_dataset_ids || []) {
          if (id) shelfHitIds.add(String(id));
        }
      }
    }
    return catalog.filter((d) => {
      const did = String(d.dataset_id || "");
      if (shelfHitIds.has(did)) return true;
      const nav = libraryNavHaystack.get(did) || "";
      const text = `${did} ${d.name} ${d.display_name || ""} ${d.grain} ${d.description || ""} ${d.one_line || ""} ${d.partition_id || ""} ${nav}`.toLowerCase();
      return text.includes(q);
    });
  }, [catalog, libraryNavHaystack, librarySearchQuery, partitions, shelves]);

  const headerDsCount = catalog.length || Number(health?.datasets) || 0;
  const headerConnected = catalog.filter((d) => isQueryReadyReadiness(d.analysis_readiness)).length;

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
            setDiscoverSearchQuery(q);
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
          shelves={shelves}
          guide={libraryGuide}
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
          searchQuery={librarySearchQuery}
          onSearchChange={setLibrarySearchQuery}
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
          searchQuery={discoverSearchQuery}
          onSearchChange={setDiscoverSearchQuery}
          preferLiveSources={discoverPreferLive}
          onLiveSourcesConsumed={setDiscoverPreferLive}
          jobs={jobs}
          usingSeed={usingSeed}
          probeSnapshots={probeSnapshots}
          discoverMode={discoverMode}
          discoverFocusAwaiting={discoverFocusAwaiting}
          onDiscoverModeChange={setDiscoverModeSafe}
          historyEvents={historyItems}
          selectedHistoryId={selectedHistoryId}
          onSelectHistoryEvent={(event) => {
            setSelectedHistoryId(event?.id || "");
            setActiveObject(discoverHistoryObject(event));
            setRailTab("detail");
          }}
          onSuggestSearch={(q) => {
            setDiscoverSearchQuery(q);
            goTab("browse");
          }}
          onCraftUrl={craftPublicUrlPlan}
          onSearchWeb={askSearchWeb}
          onSelectRow={(row) => {
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
          onGoTab={goTab}
          onOpenDataset={openInLibraryFromDiscover}
          onSelectThread={(thread) => {
            setActiveObject(synthesisThreadObject(thread));
            setRailTab("detail");
          }}
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

  // Keep Detail/Ask rail on Discover Explore empty state — same shell as other pages.
  // (Hiding it via no-rail made Explore look broken; BrowseRailPanel already owns the empty copy.)
  const hideRail = false;

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
          health == null
            ? "syncing"
            : usingSeed
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
        onTrackResources={trackJobInResources}
        onReviewApproval={reviewApprovalInResources}
        onRetryLifecycleRefresh={retryLifecycleRefresh}
        onReviewHistoryRequest={(item) => {
          const job = item?.id && item?.status ? item : selectedHistoryJob;
          if (job) reviewApprovalInResources(job);
        }}
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
            searchQuery={pageSearchQuery}
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
