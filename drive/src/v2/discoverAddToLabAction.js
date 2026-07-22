/** Discover Add to lab — sticky primary action contract (label vs busy state). */

export function buildDiscoverAddToLabPrimary({ collectBusy, probeLoading, preflight, onAddToLab, target }) {
  return {
    key: "add-lab",
    label: "Add to lab",
    disabled: probeLoading || collectBusy || !preflight.canAdd,
    busy: collectBusy,
    busyLabel: "Queuing…",
    onClick: () => onAddToLab?.(target),
  };
}

/** Matches RailActionFooter visible / accessible name resolution. */
export function railActionAccessibleName(action) {
  if (!action) return "";
  return action.busy && action.busyLabel ? action.busyLabel : action.label;
}

/** Only enter collect busy state when a connector is ready to queue. */
export function discoverCollectShouldEnterBusyState(connectorId) {
  return Boolean(connectorId);
}
