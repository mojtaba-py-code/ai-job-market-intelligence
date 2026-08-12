"""Text cleaning and normalisation utilities."""

from __future__ import annotations

import html
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
# `<[^>]+>` looks equivalent but is quadratic on input like "<<<<<<<...": the
# negated class matches `<` as well, so every opening bracket starts a candidate
# run that scans to the end of the string before failing. Excluding `<` from the
# body means a run can never span another tag opener, and the scan stays linear.
_HTML_TAG = re.compile(r"<[^<>]+>")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space and strip ends."""
    return _WHITESPACE.sub(" ", text).strip()


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    without_tags = _HTML_TAG.sub(" ", text)
    return html.unescape(without_tags)


def clean_text(text: str | None, *, keep_newlines: bool = False) -> str:
    """Full cleaning pass suitable for descriptions.

    - unescape/strip HTML
    - normalise unicode to NFKC
    - drop control characters
    - collapse whitespace (optionally preserving paragraph breaks)
    """
    if not text:
        return ""

    text = strip_html(text)
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL.sub("", text)

    if keep_newlines:
        lines = [normalize_whitespace(line) for line in text.splitlines()]
        # Preserve paragraph breaks but collapse runs of 3+ blank lines to one.
        text = "\n".join(lines)
        return _MULTI_NEWLINE.sub("\n\n", text).strip()

    return normalize_whitespace(text)


def tokenize(text: str) -> list[str]:
    """Lightweight word tokenizer (alphanumeric + a few tech symbols)."""
    return re.findall(r"[a-zA-Z0-9+#.]+", text.lower())
