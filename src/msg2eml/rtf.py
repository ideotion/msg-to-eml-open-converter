"""De-encapsulate an Outlook RTF body into HTML or plain text.

``extract-msg`` already hands us a decompressed RTF byte stream via its
``rtfBody`` property, so ``compressed_rtf.decompress`` is used defensively:
it is attempted first, but its output is only kept if it still looks like
RTF (starts with ``{\\rtf``); otherwise the original bytes are used
unchanged. This protects against edge cases where the stream we receive is
still compressed without depending on ``extract-msg`` internals staying the
same across versions.

De-encapsulation itself is delegated to RTFDE, whose Lark-based RTF parser
can raise a wide variety of exceptions -- both its own documented ones and
generic ones (``ValueError``, ``KeyError``, ...) -- when given RTF it
cannot handle. Any failure here must degrade gracefully rather than crash a
batch conversion run, so all of it is caught.
"""

from __future__ import annotations

import logging
import re

import compressed_rtf
from RTFDE.deencapsulate import DeEncapsulator

logger = logging.getLogger(__name__)

_RTF_MAGIC = b"{\\rtf"


def _decompress_if_needed(data: bytes) -> bytes:
    """Best-effort decompression of a possibly LZFu-compressed RTF stream."""
    try:
        decompressed = compressed_rtf.decompress(data)
    except Exception:  # noqa: BLE001 - compressed_rtf raises bare Exception
        return data
    if isinstance(decompressed, str):
        decompressed = decompressed.encode("utf-8", errors="replace")
    return decompressed if decompressed.startswith(_RTF_MAGIC) else data


def _as_text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def rtf_to_content(rtf_data: bytes) -> tuple[str | None, str | None]:
    """De-encapsulate a raw RTF body into (html, plain_text).

    Exactly one of the two return values is populated on success (matching
    RTFDE's ``content_type``: ``"html"`` or ``"text"``). Both are ``None``
    if de-encapsulation fails for any reason; callers should fall back to a
    best-effort plain-text extraction in that case.
    """
    rtf_bytes = _decompress_if_needed(rtf_data)
    try:
        deencapsulator = DeEncapsulator(rtf_bytes)
        deencapsulator.deencapsulate()
    except Exception:
        logger.debug("RTF de-encapsulation failed", exc_info=True)
        return None, None

    if deencapsulator.content_type == "html":
        return _as_text(deencapsulator.html), None
    if deencapsulator.content_type == "text":
        return None, _as_text(deencapsulator.text)
    return None, None


_CONTROL_WORD_RE = re.compile(
    r"\\'[0-9a-fA-F]{2}|\\[a-zA-Z]+-?\d*[ ]?|\\[^a-zA-Z]|[{}]|\r|\n"
)


def strip_rtf_controls(rtf_data: bytes) -> str:
    """Crude last-resort plain-text extraction when de-encapsulation fails.

    Strips RTF control words/groups with a regular expression. This does
    not attempt to be a correct RTF renderer -- it exists only so a message
    whose RTF body cannot be de-encapsulated still gets *some* readable
    text instead of an empty body.
    """
    text = rtf_data.decode("utf-8", errors="replace")
    text = _CONTROL_WORD_RE.sub(" ", text)
    return " ".join(text.split())
