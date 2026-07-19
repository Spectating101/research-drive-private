"""Dependency-free execution truth for the YZU cluster control plane."""
from ._interop_common import BaseStore, Claim, stage, now_utc, normalize_capabilities
from ._interop_runtime import RuntimeMixin
from ._interop_registry import RegistryMixin
from .interop_connectors import ConnectorMixin
from .interop_fencing import AttemptFenceMixin
from .interop_reliability import ReliabilityMixin
from .interop_resources import ResourceMixin


class InteropStore(
    AttemptFenceMixin,
    ReliabilityMixin,
    ResourceMixin,
    ConnectorMixin,
    RuntimeMixin,
    RegistryMixin,
    BaseStore,
):
    """Durable worker, execution, connector, resource, and asset-registration store."""

    def __init__(self, database=":memory:", *, worker_stale_after_seconds: int = 300) -> None:
        if worker_stale_after_seconds < 1:
            raise ValueError("worker_stale_after_seconds must be positive")
        self.worker_stale_after_seconds = int(worker_stale_after_seconds)
        super().__init__(database)
        self._init_connectors()
        self._init_resources()


__all__ = ["Claim", "InteropStore", "stage", "now_utc", "normalize_capabilities"]
