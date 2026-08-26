"""Physically bounded tabular reads for Synthesis diagnostics and Preview.

This module is deliberately narrower than the production executor reader. Its
contract is not "read every supported research asset at any size"; it is "obtain
a bounded diagnostic window without accidentally materialising the whole asset".
Non-streamable large JSON documents therefore fail closed and should be converted
to JSONL/CSV/Parquet before Preview.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_FALLBACK_BYTES = 16 * 1024 * 1024


def _bounded_json_lines(target: Path, want: int):
    import pandas as pd

    frame = pd.read_json(target, lines=True, nrows=want)
    exact = len(frame) < want
    return frame, len(frame) if exact else None, len(frame), exact


def read_bounded_frame(path: Path, row_cap: int) -> tuple[Any, int | None, int, bool]:
    """Return ``(frame, total_rows, observed_rows, total_exact)``.

    At most ``row_cap + 1`` rows are read for streaming formats. The extra row
    establishes truncation without scanning CSV/JSONL to EOF. Parquet obtains an
    exact row count from metadata while loading only bounded record batches.
    """
    import pandas as pd

    target = Path(path)
    cap = max(1, int(row_cap))
    want = cap + 1
    suffix = target.suffix.lower()

    if suffix == ".parquet":
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(target)
        total_rows = int(parquet.metadata.num_rows)
        frames = []
        remaining = want
        for batch in parquet.iter_batches(batch_size=min(100_000, want)):
            piece = batch.to_pandas()
            if len(piece) > remaining:
                piece = piece.head(remaining)
            frames.append(piece)
            remaining -= len(piece)
            if remaining <= 0:
                break
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return frame, total_rows, len(frame), True

    if suffix == ".csv":
        frame = pd.read_csv(target, nrows=want)
        exact = len(frame) < want
        return frame, len(frame) if exact else None, len(frame), exact

    if suffix in {".jsonl", ".ndjson"}:
        return _bounded_json_lines(target, want)

    if suffix == ".json" or suffix == "":
        # Small JSON documents can be classified exactly without risk. This also
        # preserves production support for dict-of-dicts JSON that is not JSONL.
        if target.stat().st_size <= MAX_FALLBACK_BYTES:
            try:
                raw = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    full = pd.DataFrame(raw)
                elif isinstance(raw, dict):
                    if raw and all(isinstance(v, dict) for v in raw.values()):
                        full = pd.DataFrame(list(raw.values()))
                    else:
                        full = pd.json_normalize(raw)
                else:
                    raise ValueError("unsupported json shape for bounded read")
                return full.head(want), len(full), min(len(full), want), True
            except json.JSONDecodeError:
                return _bounded_json_lines(target, want)

        # A large .json/extensionless file may actually be JSONL. Trying the
        # lines reader with nrows is physically bounded; if it is a monolithic
        # JSON array/object pandas rejects it and we fail closed below.
        try:
            return _bounded_json_lines(target, want)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                "bounded diagnostic read cannot safely stream this large JSON document; "
                "convert it to JSONL/CSV/Parquet first"
            ) from exc

    if target.stat().st_size > MAX_FALLBACK_BYTES:
        raise ValueError(
            f"bounded diagnostic read does not stream {suffix or 'this'} format above "
            f"{MAX_FALLBACK_BYTES} bytes"
        )

    from scripts.research_data_mcp.synthesis_executor import _read_frame

    full = _read_frame(target)
    return full.head(want), len(full), min(len(full), want), True
