import { useCallback, useEffect, useMemo, useState } from "react";
import { V2DeskHeader } from "@/v2/V2DeskHeader";
import {
  approveJob,
  describeDataset,
  deskHealth,
  deskResources,
  deskWarm,
  facultyProfile,
  libraryOps,
  libraryOverview,
  listAcquisitions,
  listDatasets,
  listJobs,
  listPartitions,
  probePublicSource,
  procurementCatalogSummary,
  submitDiscoverCollect,
  yzuClusterStatus,
} from "@/v2/api";
import { AskRail } from "@/v2/AskRail";
import {
  datasetObject,
  externalCandidateObject,
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
import { Toast, useToast } from "@/v2/toast";
import { V2Sidebar } from "@/v2/V2Sidebar";
import { touchRecent } from "@/v2/recent";
import { mergeHealth, resolveCatalog } from "@/v2/deskSeed";
import { loadSettings } from "@/v2/settingsStore";
import { CLUSTER_NAV_DEFERRED } from "@/v2/nav-config.jsx";
import {
  buildAddToLabDisplayText,
  buildAddToLabPrompt,
  discoverCandidateUrl,
} from "@/v2/discoverActions";
import { candidateKey } from "@/v2/candidateKey";
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
  return {
    tab,
    dataset: p.get("dataset") || "",
    folder,
    preview: p.get("preview") === "1",
    q,
  };
}

function writeParams({ tab, dataset, folder, preview, q }) {
  const p = new URLSearchParams();
  if (tab && tab !== "home") p.set("tab", tab);
  if (folder) p.set("folder", folder);
  if (dataset) p.set("dataset", dataset);
  if (preview) p.set("preview", "1");
  if (q) p.set("q", q);
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
  const [resourcesRefreshedAt, setResourcesRefreshedAt] = useState(null);
  const [resourceMode, setResourceMode] = useState("spending");
  const [activityFilter, setActivityFilter] = useState(null);
  const [pendingAsk, setPendingAsk] = useState("");
  const { toast, show: showToast } = useToast();

  const reloadProfile = useCallback(() => {
    const email = loadUserEmail();
    facultyProfile(email)
      .then((data) => setProfile(data?.found ? data.profile : { email, unknown: true }))
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
      };
      writeParams(next);
    },
    [tab, folderId, selectedId, previewOpen, searchQuery],
  );

  const goTab = useCallback(
    (id) => {
      if (id === "library") {
        setTab(id);
        setSelectedId("");
        setDetail(null);
        setPreviewOpen(false);
        setPreviewTarget(null);
        setActiveObject(null);
        setRailTab("detail");
        syncUrl({ tab: id, dataset: "", preview: false });
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

  const openPreviewExternal = useCallback((row) => {
    if (!row) return;
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
        setActiveObject(datasetObject(row));
        touchRecent(id);
        setRailTab("detail");
        syncUrl({ tab: "library", dataset: id, preview: false, q: "" });
        showToast("Opened in Library");
        return;
      }

      setActiveObject(externalCandidateObject(target));
      setRailTab("ask");

      const key = candidateKey(target);
      const probeResult = browseProbe.candidateKey === key ? browseProbe.result : null;
      const connectorId = probeResult?.connector?.connector_id || probeResult?.connector?.id;

      if (connectorId) {
        try {
          const out = await submitDiscoverCollect(connectorId, {
            limit: 200,
            autoApprove: false,
            candidateKey: key,
            source: target?.source || target?.collect_via || "",
            datasetId: target?.dataset_id || "",
            doi: target?.doi || "",
            url: discoverCandidateUrl(target) || "",
          });
          const job = out?.job;
          refreshBackend();
          setPendingAsk({
            prompt: `${buildAddToLabPrompt(target, probeResult)}\n\nCollection job queued: ${job?.id || "see Resources → Active jobs"}.`,
            displayText: buildAddToLabDisplayText(target, probeResult, job?.id),
          });
          showToast(job?.id ? "Collection job queued — track it in Resources" : "Collection job queued");
          return;
        } catch (err) {
          setPendingAsk({
            prompt: buildAddToLabPrompt(target, probeResult),
            displayText: buildAddToLabDisplayText(target, probeResult),
          });
          showToast(err?.message || "Collect failed — queued Ask instead");
          return;
        }
      }

      setPendingAsk({
        prompt: buildAddToLabPrompt(target, probeResult),
        displayText: buildAddToLabDisplayText(target, probeResult),
      });
      showToast("Queued Ask — Add to lab");
    },
    [labIds, browseProbe, catalog, syncUrl, showToast, refreshBackend],
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
      // Ignore stale responses if selection changed mid-flight
      if (out?.error) {
        setBrowseProbe((cur) =>
          cur.candidateKey === key
            ? { candidateKey: key, loading: false, result: null, error: String(out.error) }
            : cur,
        );
        return;
      }
      setBrowseProbe((cur) =>
        cur.candidateKey === key
          ? { candidateKey: key, loading: false, result: out, error: "" }
          : cur,
      );
      if (candidateKey(target) === key) {
        showToast("Source probed — review connector details");
      }
    } catch (err) {
      setBrowseProbe((cur) =>
        cur.candidateKey === key
          ? { candidateKey: key, loading: false, result: null, error: err?.message || "Probe failed" }
          : cur,
      );
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
      setRailTab("ask");
    },
    [tab],
  );

  useEffect(() => {
    setBrowseRow(null);
    setBrowseProbe({ candidateKey: "", loading: false, result: null, error: "" });
    setActiveObject((current) => (current?.kind === "external_candidate" ? null : current));
  }, [searchQuery]);

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
    [goTab],
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
          onAskAttention={askHomeAttention}
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
          jobs={jobs}
          usingSeed={usingSeed}
          onSuggestSearch={(q) => {
            setSearchQuery(q);
            goTab("browse");
          }}
          onSearchWeb={askSearchWeb}
          onSelectRow={(row) => {
            setBrowseRow(row);
            setBrowseProbe((current) =>
              current.candidateKey === candidateKey(row)
                ? current
                : { key: "", loading: false, result: null, error: "" },
            );
            setActiveObject(externalCandidateObject(row));
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
          onSuggestSearch={(q) => {
            setSearchQuery(q);
            setTab("browse");
            syncUrl({ tab: "browse", q });
          }}
        />
      );
      break;
    case "settings":
      main = <SettingsPage health={health} onProfileRefresh={reloadProfile} onToast={showToast} />;
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
        onSearchSubmit={askFromSearch}
        onAskFromSearch={askFromSearch}
        onBrandClick={() => goTab("home")}
        onRetry={refreshBackend}
        headerInitials="YZ"
        datasetCount={headerDsCount}
        usingSeed={usingSeed}
        workCount={health?.desk?.jobs?.pending_approval ?? 0}
        deskStatus={
          usingSeed
            ? health?.status === "ok"
              ? "empty"
              : "demo"
            : health?.status === "ok" || datasets.length > 0
              ? "ok"
              : health?.status || "unknown"
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
        detailLoading={detailLoading}
        clusterContext={clusterContext}
        browseTarget={browseTarget}
        resourceRow={resourceRow}
        resourcesRollup={resourcesRollup}
        activeObject={activeObject}
        profile={profile}
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
                  ? browseTarget
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
            railContext={railContext}
          />
        }
      />
      <Toast toast={toast} />
    </div>
  );
}
