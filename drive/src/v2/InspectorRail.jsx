import { useState } from "react";
import {
  BrowseRailPanel,
  ClusterRailPanel,
  DetailPanel,
  EmptyRailPanel,
  HistoryRailPanel,
  HomeAttentionRailPanel,
  LibraryObjectRailPanel,
  PageRailPanel,
  ResourcesRailPanel,
} from "@/v2/RailPanels";
import { ProfileDetailPanel } from "@/v2/ProfilePage";
import { SettingsDetailPanel } from "@/v2/SettingsPage";
import { loadSettings } from "@/v2/settingsStore";
import { activeObjectSelectionHint } from "@/v2/activeObject";
import { displayName } from "@/v2/datasetMeta";

function railSelectionHint(
  mainTab,
  dataset,
  browseTarget,
  resourceRow,
  clusterContext,
  selectedProfileWork = null,
  settingsGroup = "",
) {
  if (mainTab === "browse" && browseTarget) {
    return browseTarget.title || browseTarget.dataset_id || "Discover result";
  }
  if (mainTab === "browse" && dataset?.dataset_id) {
    return `Discover · ${displayName(dataset)}`;
  }
  if (mainTab === "browse") {
    return "Discover";
  }
  if (mainTab === "resources" && resourceRow) {
    return resourceRow.label?.split("·")[0]?.trim() || resourceRow.key;
  }
  if (mainTab === "resources") {
    return "Resources";
  }
  if (mainTab === "profile") {
    if (selectedProfileWork?.title) return selectedProfileWork.title;
    return "Profile";
  }
  if (mainTab === "settings") {
    return "Settings";
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

function activeHintBelongsToTab(mainTab, object) {
  if (!object) return false;
  if (mainTab === "library") {
    return ["library_folder", "library_intake", "dataset"].includes(object.kind);
  }
  if (mainTab === "browse") return ["external_candidate", "history_event"].includes(object.kind);
  if (mainTab === "resources") return object.kind === "resource_row";
  if (mainTab === "home") return ["dataset", "home_attention"].includes(object.kind);
  if (mainTab === "cluster") return object.kind === "comparison";
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
  collectState,
  jobs = [],
  discoverDestination = "",
  discoverDestinationOptions = [],
  onDiscoverDestinationChange,
  catalog = [],
  profile = null,
  selectedProfileWork = null,
  onClearProfileWork,
  onGoTab,
  settingsGroup = "identity",
  onSettingsFocusGroup,
  health = null,
  browsePeerRows = [],
  onSelectBrowsePeer,
  onOpenInLibrary,
  onOpenDiscoverAwaiting,
  labIds,
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
}) {
  let detailPanel;
  if (mainTab === "cluster") {
    detailPanel = <ClusterRailPanel compare={clusterContext} onAskAbout={onAskAbout} />;
  } else if (mainTab === "browse" && activeObject?.kind === "history_event") {
    detailPanel = (
      <HistoryRailPanel
        object={activeObject}
        onAskAbout={onAskAbout}
        onOpenInLibrary={onOpenInLibrary}
      />
    );
  } else if (mainTab === "browse") {
    detailPanel = (
      <BrowseRailPanel
        target={browseTarget}
        contextDataset={dataset}
        labIds={labIds}
        jobs={jobs}
        catalog={catalog}
        profile={profile}
        browsePeerRows={browsePeerRows}
        onSelectBrowsePeer={onSelectBrowsePeer}
        onAskAbout={onAskAbout}
        onAddToLab={onAddToLab}
        onPreviewExternal={onPreviewExternal}
        onProbeSource={onProbeSource}
        probeState={probeState}
        collectState={collectState}
        discoverDestination={discoverDestination}
        discoverDestinationOptions={discoverDestinationOptions}
        onDiscoverDestinationChange={onDiscoverDestinationChange}
        onOpenInLibrary={onOpenInLibrary}
        onApproveJob={onApproveJob}
      />
    );
  } else if (mainTab === "resources") {
    detailPanel = (
      <ResourcesRailPanel
        row={resourceRow}
        rollup={resourcesRollup}
        onApproveJob={onApproveJob}
        onRefresh={onRefresh}
        onViewActivity={onViewActivity}
        onAskAbout={onAskAbout}
        onOpenDiscoverAwaiting={onOpenDiscoverAwaiting}
      />
    );
  } else if (mainTab === "synthesis") {
    detailPanel = <PageRailPanel page="synthesis" onAskAbout={onAskAbout} />;
  } else if (mainTab === "profile") {
    detailPanel = (
      <ProfileDetailPanel
        profile={profile}
        selectedWork={selectedProfileWork}
        onGoTab={onGoTab}
        onClearWork={onClearProfileWork}
        onAskAbout={onAskAbout}
      />
    );
  } else if (mainTab === "settings") {
    detailPanel = (
      <SettingsDetailPanel
        activeGroup={settingsGroup || "identity"}
        settings={loadSettings()}
        health={health}
        onSelectGroup={onSettingsFocusGroup}
      />
    );
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
  } else if (mainTab === "library" && !dataset?.dataset_id) {
    detailPanel = <PageRailPanel page="library" onAskAbout={onAskAbout} />;
  } else if (mainTab === "home" && activeObject?.kind === "home_attention") {
    detailPanel = (
      <HomeAttentionRailPanel
        object={activeObject}
        onAskAbout={onAskAbout}
        onApproveJob={onApproveJob}
        onOpenDiscover={onOpenDiscoverAwaiting}
      />
    );
  } else if (mainTab === "home" && !dataset?.dataset_id) {
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
    railSelectionHint(
      mainTab,
      dataset,
      browseTarget,
      resourceRow,
      clusterContext,
      selectedProfileWork,
      settingsGroup,
    );

  const [mobileRailOpen, setMobileRailOpen] = useState(false);

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
