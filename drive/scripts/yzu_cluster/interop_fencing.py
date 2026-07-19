"""Attempt fencing and idempotent terminal event handling for YZU workers."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from ._interop_common import TERMINAL, ids, loads, stage


def _optional_equal(existing: Any, incoming: Any) -> bool:
    return incoming is None or existing == incoming


class AttemptFenceMixin:
    """Reject writes from expired attempts and deduplicate terminal event retries."""

    def _check_attempt(self, run_id: str, expected_attempt: int | None) -> None:
        if expected_attempt is None:
            return
        current = int(self._row(run_id)["attempt"])
        if current != int(expected_attempt):
            raise PermissionError(
                f"stale execution attempt: expected {expected_attempt}, current {current}"
            )

    def heartbeat(
        self,
        run_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 120,
        current: float | None = None,
        total: float | None = None,
        next_stage: str | None = None,
        at: str | None = None,
        expected_attempt: int | None = None,
    ) -> dict[str, Any]:
        self._check_attempt(run_id, expected_attempt)
        return super().heartbeat(
            run_id,
            worker_id,
            lease_seconds=lease_seconds,
            current=current,
            total=total,
            next_stage=next_stage,
            at=at,
        )

    def _terminal_replay_matches(
        self,
        row,
        *,
        outputs: Iterable[Any] | None,
        manifest_id: str | None,
        archive_verified: bool | None,
        registry_id: str | None,
        rows: int | None,
        fields: int | None,
        entities: int | None,
        error: str | None,
        retryable: bool | None,
    ) -> bool:
        return all((
            outputs is None or loads(row["outputs"], []) == ids(outputs),
            _optional_equal(row["manifest_id"], manifest_id),
            archive_verified is None or bool(row["archive_verified"]) == bool(archive_verified),
            _optional_equal(row["registry_id"], registry_id),
            _optional_equal(row["rows_count"], rows),
            _optional_equal(row["fields_count"], fields),
            _optional_equal(row["entities_count"], entities),
            _optional_equal(row["error"], error),
            retryable is None or bool(row["retryable"]) == bool(retryable),
        ))

    def record(
        self,
        run_id: str,
        next_stage: str,
        *,
        event_type: str | None = None,
        worker_id: str | None = None,
        current: float | None = None,
        total: float | None = None,
        outputs: Iterable[Any] | None = None,
        manifest_id: str | None = None,
        archive_verified: bool | None = None,
        registry_id: str | None = None,
        rows: int | None = None,
        fields: int | None = None,
        entities: int | None = None,
        error: str | None = None,
        retryable: bool | None = None,
        message: str | None = None,
        payload: Mapping[str, Any] | None = None,
        at: str | None = None,
        expected_attempt: int | None = None,
    ) -> dict[str, Any]:
        self._check_attempt(run_id, expected_attempt)
        row = self._row(run_id)
        target = stage(next_stage)
        if row["stage"] == target and target in TERMINAL:
            if self._terminal_replay_matches(
                row,
                outputs=outputs,
                manifest_id=manifest_id,
                archive_verified=archive_verified,
                registry_id=registry_id,
                rows=rows,
                fields=fields,
                entities=entities,
                error=error,
                retryable=retryable,
            ):
                return self.snapshot(run_id)
            raise ValueError("conflicting terminal event replay")

        return super().record(
            run_id,
            next_stage,
            event_type=event_type,
            worker_id=worker_id,
            current=current,
            total=total,
            outputs=outputs,
            manifest_id=manifest_id,
            archive_verified=archive_verified,
            registry_id=registry_id,
            rows=rows,
            fields=fields,
            entities=entities,
            error=error,
            retryable=retryable,
            message=message,
            payload=payload,
            at=at,
        )

    def record_usage(
        self,
        run_id: str,
        *,
        expected_attempt: int | None = None,
        **values: Any,
    ) -> dict[str, Any]:
        self._check_attempt(run_id, expected_attempt)
        return super().record_usage(run_id, **values)

    def register(
        self,
        run_id: str,
        *,
        expected_attempt: int | None = None,
        **values: Any,
    ) -> dict[str, Any]:
        self._check_attempt(run_id, expected_attempt)
        return super().register(run_id, **values)
