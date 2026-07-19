import { useEffect, useState } from "react";
import {
  BrowseRailPanel,
  ClusterRailPanel,
  DetailPanel,
  EmptyRailPanel,
  HomeAttentionRailPanel,
  LibraryObjectRailPanel,
  PageRailPanel,
  ResourcesRailPanel,
} from "@/v2/RailPanels";
import { ProfileDetailPanel } from "@/v2/ProfilePage";
import { activeObjectSelectionHint } from "@/v2/activeObject";
import { displayName } from "@/v2/datasetMeta";
import { LibraryDatasetRailPanel } from "@/v2/LibraryDatasetRailPanel";
import { ResourcesOverviewRailPanel } from "@/v2/ResourcesOverviewRailPanel";
import { DiscoverHistoryRailPanel } from "@/v2/DiscoverHistoryRailPanel";
import { SynthesisThreadRailPanel } from "@/v2/SynthesisThreadRailPanel";

function railSelectionHint(mainTab, dataset, browseTarget, historyEvent, resourceRow, clusterContext) {
  if (mainTab === "browse" && historyEvent) {
    return historyEvent.target || historyEvent.title || historyEvent.id || "Discover lifecycle item";
  }
  if (mainTab === "browse" && browseTarget) {
    return browseTarget.title || browseTarget.dataset_id || "Discover result";
  }
  if (mainTab === "browse") {
    return "No discover result";
  }
  if (mainTab === "resources" && resourceRow) {
    return resourceRow.label?.split("·")[0]?.trim() || resourceRow.key;
  }
  if (mainTab === "resources") {
    return "Resources";
  }
  if (mainTab === "profile") {
    return "Profile";
  }
  if (mainTab === "settings") {
    return "Desk setup";
  }
  if (mainTab === "synthesis") {
    return "Synthesis";
  }
  if (mainTab === "cluster" && clusterContext?.a && clusterContext?.b) {
    return `${displayName(clusterContext.a)} × ${displayName(clusterContext.b)}`;
  }
  if (mainTab === "cluster") {
    return "No compare selected";
  }
  if (dataset?.dataset_id) {
    return displayName(dataset);
  }
  return "No selection";
}

const MOBILE_RAIL_IDLE_HINTS = new Set([
  "No selection",
  "No discover result",
  "No compare selected",
  "Resources",
  "Profile",
  "Desk setup",
]);

function activeHintBelongsToTab(mainTab, object) {
  if (!object) return false;
  if (mainTab === "library") {
    return ["library_folder", "library_intake", "dataset"].includes(object.kind);
  }
  if (mainTab === "browse") return ["external_candidate", "discover_history"].includes(object.kind);
  if (mainTab === "resources") return object.kind === "resource_row";
  if (mainTab === "home") return ["dataset", "home_attention"].includes(object.kind);
  if (mainTab === "cluster") return object.kind === "comparison";
  if (mainTab === "synthesis") return object.kind === "synthesis_thread";
  return false;
}

export function InspectorRail({
  mainTab,
  railTab,
  onRailTabChange,
  dataset,
  detailLoading,
  clusterContext,
  browseTarget,
  historyEvent,
  historyJob,
  resourceRow,
  resourcesRollup,
  activeObject,
  onPreview,
  onAskAbout,
  onSeeCluster,
  onAddToLab,
  onPreviewExternal,
  onProbeSource,
  probeState,
  onOpenInLibrary,
  labIds,
  browseLifecycle = null,
  onTrackResources,
  onReviewApproval,
  onRetryLifecycleRefresh,
  onReviewHistoryRequest,
  onApproveJob,
  onRefresh,
  onViewActivity,
  onStartLibraryUpload,
  onStartLibraryUrl,
  onStartLibraryProcure,
  onSubmitLibraryUpload,
  onSubmitLibraryUrl,
  onSubmitLibraryProcure,
  askPanel,
  profile = null,
}) {
  let detailPanel;
  if (mainTab === "synthesis" && activeObject?.kind === "synthesis_thread") {
    detailPanel = (
      <SynthesisThreadRailPanel
        thread={activeObject.thread}
        onAskAbout={onAskAbout}
        onOpenInLibrary={onOpenInLibrary}
      />
    );
  } else if (mainTab === "cluster") {
    detailPanel = <ClusterRailPanel compare={clusterContext} onAskAbout={onAskAbout} />;
  } else if (mainTab === "browse") {
    detailPanel = historyEvent ? (
      <DiscoverHistoryRailPanel
        event={historyEvent}
        job={historyJob}
        onAskAbout={onAskAbout}
        onReviewRequest={onReviewHistoryRequest}
      />
    ) : (
      <BrowseRailPanel
        target={browseTarget}
        labIds={labIds}
        onAskAbout={onAskAbout}
        onAddToLab={onAddToLab}
        onPreviewExternal={onPreviewExternal}
        onProbeSource={onProbeSource}
        probeState={probeState}
        onOpenInLibrary={onOpenInLibrary}
        lifecycle={browseLifecycle}
        onTrackResources={onTrackResources}
        onReviewApproval={onReviewApproval}
        onRetryLifecycleRefresh={onRetryLifecycleRefresh}
      />
    );
  } else if (mainTab === "resources") {
    detailPanel = resourceRow ? (
      <ResourcesRailPanel
        row={resourceRow}
        rollup={resourcesRollup}
        onApproveJob={onApproveJob}
        onRefresh={onRefresh}
        onViewActivity={onViewActivity}
        onAskAbout={onAskAbout}
      />
    ) : (
      <ResourcesOverviewRailPanel rollup={resourcesRollup} onViewActivity={onViewActivity} />
    );
  } else if (mainTab === "profile") {
    detailPanel = <ProfileDetailPanel profile={profile} />;
  } else if (mainTab === "settings") {
    detailPanel = <PageRailPanel page="settings" onAskAbout={onAskAbout} />;
  } else if (mainTab === "synthesis") {
    detailPanel = <PageRailPanel page="synthesis" onAskAbout={onAskAbout} />;
  } else if (
    mainTab === "library" &&
    (activeObject?.kind === "library_folder" || activeObject?.kind === "library_intake")
  ) {
    detailPanel = (
      <LibraryObjectRailPanel
        object={activeObject}
        onAskAbout={onAskAbout}
        onStartUpload={onStartLibraryUpload}
        onStartUrl={onStartLibraryUrl}
        onStartProcure={onStartLibraryProcure}
        onSubmitUpload={onSubmitLibraryUpload}
        onSubmitUrl={onSubmitLibraryUrl}
        onSubmitProcure={onSubmitLibraryProcure}
      />
    );
  } else if (mainTab === "library" && dataset?.dataset_id) {
    detailPanel = (
      <LibraryDatasetRailPanel
        dataset={dataset}
        onPreview={onPreview}
        onAskAbout={onAskAbout}
      />
    );
  } else if (mainTab === "library" && !dataset?.dataset_id) {
    detailPanel = <PageRailPanel page="library" onAskAbout={onAskAbout} />;
  } else if (mainTab === "home" && activeObject?.kind === "home_attention") {
    detailPanel = <HomeAttentionRailPanel object={activeObject} onAskAbout={onAskAbout} />;
  } else if (mainTab === "home" && dataset?.dataset_id) {
    detailPanel = (
      <LibraryDatasetRailPanel
        dataset={dataset}
        onPreview={onPreview}
        onAskAbout={onAskAbout}
      />
    );
  } else if (mainTab === "home") {
    detailPanel = <PageRailPanel page="home" onAskAbout={onAskAbout} />;
  } else {
    detailPanel = (
      <DetailPanel
        dataset={dataset}
        loading={detailLoading}
        onPreview={onPreview}
        onAskAbout={onAskAbout}
        onSeeCluster={onSeeCluster}
      />
    );
  }

  const allowActiveHint = activeHintBelongsToTab(mainTab, activeObject);
  const selectionHint =
    (allowActiveHint ? activeObjectSelectionHint(activeObject) : "") ||
    railSelectionHint(mainTab, dataset, browseTarget, historyEvent, resourceRow, clusterContext);

  const [mobileRailOpen, setMobileRailOpen] = useState(false);

  useEffect(() => {
    if (mainTab === "browse") {
      setMobileRailOpen(Boolean(browseTarget || historyEvent) && railTab === "ask");
      return;
    }
    if (mainTab === "home") {
      setMobileRailOpen(railTab === "ask");
      return;
    }
    if (mainTab === "synthesis") {
      setMobileRailOpen(railTab === "ask");
      return;
    }
    if (mainTab === "library" && activeObject?.kind === "library_folder") {
      setMobileRailOpen(false);
      return;
    }
    if (MOBILE_RAIL_IDLE_HINTS.has(selectionHint)) {
      setMobileRailOpen(false);
      return;
    }
    setMobileRailOpen(true);
  }, [selectionHint, mainTab, browseTarget, historyEvent, railTab, activeObject?.kind]);

  return (
    <aside
      className={`yzu-inspector rd-v2-rail${mobileRailOpen ? "" : " rd-v2-rail-collapsed"}`}
      aria-label="Inspector"
    >
      <div className="yzu-inspector-stack rd-v2-rail-stack">
        <div className="rd-v2-rail-chrome">
          <button
            type="button"
            className="rd-v2-rail-mobile-grip"
            aria-expanded={mobileRailOpen}
            onClick={() => setMobileRailOpen((open) => !open)}
          >
            {mobileRailOpen ? "Hide panel" : "Show Detail · Ask"}
          </button>
          <div className="rd-v2-rail-toggle" role="tablist" aria-label="Inspector mode">
            <button
              type="button"
              role="tab"
              aria-selected={railTab === "detail"}
              className={railTab === "detail" ? "on" : ""}
              onClick={() => onRailTabChange("detail")}
            >
              Detail
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={railTab === "ask"}
              className={railTab === "ask" ? "on" : ""}
              onClick={() => onRailTabChange("ask")}
            >
              Ask
            </button>
          </div>
          <p className="rd-v2-rail-selection" title={selectionHint}>
            {selectionHint}
          </p>
        </div>
        <div
          className={`rd-v2-rail-pane${railTab === "detail" ? " rd-v2-rail-pane-on" : ""}`}
          aria-hidden={railTab !== "detail"}
          data-testid="rail-pane-detail"
        >
          {detailPanel}
        </div>
        <div
          className={`rd-v2-rail-pane rd-v2-ask-rail${railTab === "ask" ? " rd-v2-rail-pane-on" : ""}`}
          aria-hidden={railTab !== "ask"}
          data-testid="rail-pane-ask"
        >
          {askPanel}
        </div>
      </div>
    </aside>
  );
}
