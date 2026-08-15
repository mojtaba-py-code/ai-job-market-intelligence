"""Export job records to multiple formats using pandas.

Records are plain dictionaries so exporters stay decoupled from the ORM. Excel
export requires ``openpyxl`` (a core dependency); JSON and CSV use the stdlib
via pandas.

**Formula injection.** Everything exported here originated on a third-party job
board, so it is untrusted text. Excel, LibreOffice and Google Sheets evaluate any
cell whose value begins with ``=``, ``+``, ``-``, ``@`` or a leading control
character — meaning a posting titled ``=HYPERLINK("http://evil","Click")``, or
one invoking ``WEBSERVICE``/``DDE``, executes when an analyst opens the export.
Escaping happens on the way out, for the sheet-like formats only; JSON is a data
format with no such evaluation and is left byte-for-byte faithful.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence

import pandas as pd

from ...domain.enums import ExportFormat

#: Leading characters a spreadsheet treats as the start of a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@")

#: Leading whitespace/control characters that spreadsheets strip before parsing,
#: which would otherwise smuggle a formula past a naive first-character check.
_CONTROL_PREFIXES = ("\t", "\r", "\n")


def escape_formula(value: object) -> object:
    """Neutralise a value that a spreadsheet would evaluate as a formula.

    Non-string values (numbers, dates, ``None``) are returned untouched — only
    text can carry a formula. Dangerous strings are prefixed with a single
    quote, which every major spreadsheet reads as "treat the rest as literal
    text" and hides from the displayed value.

    Args:
        value: a single cell value.

    Returns:
        The value, escaped if it would otherwise be evaluated.
    """
    if not isinstance(value, str) or not value:
        return value
    if value.lstrip("".join(_CONTROL_PREFIXES)).startswith(_FORMULA_PREFIXES):
        return "'" + value
    if value.startswith(_CONTROL_PREFIXES):
        return "'" + value
    return value


def _to_dataframe(records: Sequence[dict], *, escape: bool) -> pd.DataFrame:
    frame = pd.DataFrame(list(records))
    if escape and not frame.empty:
        # Applied to every cell rather than to columns of a particular dtype:
        # pandas has changed how it infers string columns between releases, and
        # a dtype check that silently stops matching would disable the escaping
        # without failing anything. `escape_formula` passes non-strings straight
        # through, so a blanket sweep costs nothing in correctness.
        frame = frame.map(escape_formula)
    return frame


def export_jobs(records: Sequence[dict], fmt: ExportFormat | str) -> bytes:
    """Serialise *records* to the requested format and return raw bytes.

    Args:
        records: list of flat dictionaries (one per job).
        fmt: one of csv | json | excel.

    Returns:
        The encoded document. CSV and Excel output is escaped against
        spreadsheet formula injection; JSON is not (it is never evaluated).
    """
    fmt = ExportFormat(fmt)

    if fmt is ExportFormat.json:
        return json.dumps(list(records), indent=2, default=str).encode("utf-8")

    frame = _to_dataframe(records, escape=True)

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
