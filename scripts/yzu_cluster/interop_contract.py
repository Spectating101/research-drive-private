"""Dependency-free execution truth for the YZU cluster control plane.

This reference module can be imported or transplanted into the private
YzuOrchestrator. It emits the additive contracts consumed by Research Drive.
"""
from ._interop_common import BaseStore, Claim, stage, now_utc, normalize_capabilities
from ._interop_runtime import RuntimeMixin
from ._interop_registry import RegistryMixin


class InteropStore(RuntimeMixin, RegistryMixin, BaseStore):
    """Durable worker, execution, lease, retry, and asset-registration store."""


__all__ = ["Claim", "InteropStore", "stage", "now_utc", "normalize_capabilities"]
