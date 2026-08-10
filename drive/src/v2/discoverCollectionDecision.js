function connectorId(probe) {
  return probe?.connector?.connector_id || probe?.connector?.id || "";
}

function accessReason(probe) {
  if (probe?.needs_approval || probe?.license_required || probe?.requires_license_approval) {
    return "This source needs approval before collection.";
  }
  if (probe?.requires_credentials || probe?.credential_required || probe?.access_required) {
    return "This source needs an access or credential decision before collection.";
  }
  if (probe?.error) return String(probe.error);
  return "";
}

export function decideDiscoverCollection({ candidate, probe } = {}) {
  const reason = accessReason(probe);
  if (reason) return { kind: "brief", reason };

  const id = connectorId(probe);
  if (id) return { kind: "direct", connectorId: id };

  const label = candidate?.title || candidate?.name || candidate?.doi || candidate?.url || "This source";
  return {
    kind: "brief",
    reason: `${label} has not produced a collectable connector yet. Review its acquisition route first.`,
  };
}

export function buildVerifiedConnectorProposal({ candidate, probe } = {}) {
  const id = connectorId(probe);
  const candidateKey = String(candidate?.candidate_key || "").trim();
  if (!id || !candidateKey) return null;

  const title = String(candidate?.title || candidate?.name || candidate?.dataset_id || "Selected source").trim();
  const routeId = `connector:${id}:${candidateKey}`.slice(0, 120);
  return {
    id: `verified:${candidateKey}`.slice(0, 120),
    summary: `Use the verified ${id} connector to collect ${title}.`,
    reason: "The connector came from the source probe; collection remains separately reviewable and approval-gated.",
    recommended_route_id: routeId,
    routes: [
      {
        id: routeId,
        title: `Collect with ${id}`,
        connector_id: id,
        candidate_key: candidateKey,
        url: candidate?.url || "",
        summary: "Verified connector route from the latest source probe.",
        access: "Review the source and approve the resulting job before collection runs.",
      },
    ],
  };
}
