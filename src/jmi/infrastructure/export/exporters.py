"""Export job records to multiple formats using pandas.

Records are plain dictionaries so exporters stay decoupled from the ORM. Excel
export requires ``openpyxl`` (a core dependency); JSON and CSV use the stdlib
via pandas.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence

import pandas as pd

from ...domain.enums import ExportFormat


def _to_dataframe(records: Sequence[dict]) -> pd.DataFrame:
    return pd.DataFrame(list(records))


def export_jobs(records: Sequence[dict], fmt: ExportFormat | str) -> bytes:
    """Serialise *records* to the requested format and return raw bytes.

    Args:
        records: list of flat dictionaries (one per job).
        fmt: one of csv | json | excel.
    """
    fmt = ExportFormat(fmt)

    if fmt is ExportFormat.json:
        return json.dumps(list(records), indent=2, default=str).encode("utf-8")

    frame = _to_dataframe(records)

    if fmt is ExportFormat.csv:
        return frame.to_csv(index=False).encode("utf-8")

    if fmt is ExportFormat.excel:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="jobs")
        return buffer.getvalue()

    raise ValueError(f"Unsupported export format: {fmt}")  # pragma: no cover


def content_type_for(fmt: ExportFormat | str) -> str:
    """Return the MIME type for an export format."""
    fmt = ExportFormat(fmt)
    return {
        ExportFormat.json: "application/json",
        ExportFormat.csv: "text/csv",
        ExportFormat.excel: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[fmt]
