"""Attachment classification helpers: filenames, MIME types, nesting, inlining."""

from __future__ import annotations

import mimetypes
import re
from typing import Any

from extract_msg.enums import AttachmentType

_NESTED_MSG_TYPES = (AttachmentType.MSG, AttachmentType.SIGNED_EMBEDDED)

_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MIME_TOKEN_RE = re.compile(r"^[A-Za-z0-9!#$&.+\-^_]+$")


def is_nested_message(attachment: Any) -> bool:
    """True if this attachment is itself an embedded .msg file."""
    return getattr(attachment, "type", None) in _NESTED_MSG_TYPES


def sanitize_filename(name: str, *, default: str = "attachment") -> str:
    """Strip characters that are unsafe in a MIME filename parameter or on disk."""
    cleaned = _UNSAFE_FILENAME_RE.sub("_", name).strip().strip(".")
    return cleaned[:150] or default


def attachment_filename(attachment: Any, index: int) -> str:
    """Best-effort filename for an attachment; always returns a non-empty, safe name."""
    for attr in ("name", "longFilename", "shortFilename"):
        value = getattr(attachment, attr, None)
        if value:
            return sanitize_filename(str(value))

    getter = getattr(attachment, "getFilename", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = None
        if value:
            return sanitize_filename(str(value))

    return f"attachment_{index}"


def guess_mime_type(attachment: Any, filename: str) -> tuple[str, str]:
    """Return (maintype, subtype) for an attachment, guessing from its filename if unset."""
    mimetype = getattr(attachment, "mimetype", None)
    if not mimetype or "/" not in mimetype:
        mimetype, _ = mimetypes.guess_type(filename)
    if not mimetype:
        mimetype = "application/octet-stream"
    maintype, _, subtype = mimetype.partition("/")
    if not _MIME_TOKEN_RE.match(maintype) or not _MIME_TOKEN_RE.match(subtype):
        return "application", "octet-stream"
    return maintype.lower(), subtype.lower()


def clean_content_id(raw: Any) -> str | None:
    """Normalize a raw Content-ID to a bracket-free, single-line token, or None."""
    if not raw:
        return None
    value = str(raw).strip().strip("<>").strip()
    if not value or "\n" in value or "\r" in value:
        return None
    return value


def is_inline_referenced(cid: str | None, html_body: str | None) -> bool:
    """True if an attachment's Content-ID is referenced by a cid: URL in the HTML body."""
    if not cid or not html_body:
        return False
    return f"cid:{cid}" in html_body
