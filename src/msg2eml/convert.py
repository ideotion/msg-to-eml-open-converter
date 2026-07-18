"""Core conversion: build an ``EmailMessage`` from a parsed .msg object.

:func:`build_eml` is written entirely against duck-typed "parsed message"
objects -- it only ever uses ``getattr``, never ``isinstance`` checks
against ``extract_msg`` classes -- so it can be unit tested with simple
fakes and does not care whether it is called with a real
``extract_msg.Message`` or a nested embedded message object.

Headers are built with ``email.policy.default`` (not ``utf8=True``): this
produces real RFC 2047 encoded headers for non-ASCII content, which is
readable by every standards-compliant client, rather than raw UTF-8
headers that require SMTPUTF8 support.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Literal

import extract_msg
from extract_msg.exceptions import ExMsgBaseException

from msg2eml import headers, msgclass, rtf
from msg2eml.attachments import (
    attachment_filename,
    clean_content_id,
    guess_mime_type,
    is_inline_referenced,
    is_nested_message,
    sanitize_filename,
)
from msg2eml.exceptions import ConversionError

logger = logging.getLogger(__name__)

_EML_POLICY = policy.default
_MAX_NESTING_DEPTH = 10

Status = Literal["converted", "skipped", "failed"]


@dataclass
class ConversionResult:
    """Outcome of converting a single .msg file."""

    input_path: Path
    status: Status
    output_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _as_text(value: Any) -> str | None:
    """Decode a body value (bytes or str) to a non-empty str, or None."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not value:
        return None
    return str(value)


def _set_headers(email_msg: EmailMessage, msg: Any, warnings: list[str]) -> None:
    subject = getattr(msg, "subject", None)
    if subject:
        email_msg["Subject"] = str(subject)

    sender = headers.normalize_mailbox(getattr(msg, "sender", None))
    if sender:
        email_msg["From"] = sender
    else:
        warnings.append("Message has no sender; From header omitted")

    groups = headers.grouped_recipients(msg)
    any_recipients = any(groups.values())
    if any_recipients:
        for header_name, key in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
            if groups[key]:
                email_msg[header_name] = headers.address_header_value(groups[key])
    else:
        # No recipient table at all: fall back to extract-msg's raw display strings.
        for header_name, attr in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
            raw = getattr(msg, attr, None)
            if raw:
                email_msg[header_name] = str(raw)

    date = headers.resolve_date(msg)
    if date is not None:
        email_msg["Date"] = format_datetime(date)
    else:
        warnings.append("Message has no date; Date header omitted")

    message_id, generated = headers.resolve_message_id(msg)
    email_msg["Message-ID"] = message_id
    if generated:
        warnings.append("Message had no Message-ID; a synthetic one was generated")

    in_reply_to = headers.resolve_in_reply_to(msg)
    if in_reply_to:
        email_msg["In-Reply-To"] = in_reply_to

    references = headers.resolve_references(msg)
    if references:
        email_msg["References"] = references


def _set_body(email_msg: EmailMessage, msg: Any, warnings: list[str]) -> str | None:
    """Populate the message body. Returns the HTML body text, if any."""
    plain = _as_text(getattr(msg, "body", None))
    html = _as_text(getattr(msg, "htmlBody", None))

    if not plain and not html:
        rtf_body = getattr(msg, "rtfBody", None)
        if rtf_body:
            rtf_html, rtf_plain = rtf.rtf_to_content(rtf_body)
            if rtf_html:
                html = rtf_html
            elif rtf_plain:
                plain = rtf_plain
            else:
                warnings.append(
                    "RTF body could not be de-encapsulated; using best-effort plain text"
                )
                plain = rtf.strip_rtf_controls(rtf_body) or None

    if plain and html:
        email_msg.set_content(plain)
        email_msg.add_alternative(html, subtype="html")
    elif html:
        email_msg.set_content(html, subtype="html")
    elif plain:
        email_msg.set_content(plain)
    else:
        warnings.append("Message has no body content")
        email_msg.set_content("")

    return html


def _promote_to_related(email_msg: EmailMessage) -> EmailMessage:
    """Return the payload part inline images should be attached to."""
    if email_msg.get_content_type() == "multipart/alternative":
        _plain_part, html_part = email_msg.iter_parts()
        assert isinstance(html_part, EmailMessage)
        return html_part
    return email_msg


def _add_nested_message(
    email_msg: EmailMessage,
    attachment: Any,
    index: int,
    warnings: list[str],
    depth: int,
) -> None:
    nested_msg = getattr(attachment, "data", None)
    if nested_msg is None:
        warnings.append(f"Nested message attachment {index} has no data; skipped")
        return

    nested_warnings: list[str] = []
    try:
        nested_eml = build_eml(nested_msg, warnings=nested_warnings, _depth=depth + 1)
    except Exception:
        logger.debug("Failed to convert nested .msg attachment %s", index, exc_info=True)
        warnings.append(f"Nested message attachment {index} could not be converted and was skipped")
        return

    warnings.extend(f"(nested attachment {index}) {w}" for w in nested_warnings)
    subject = nested_eml.get("Subject") or "message"
    filename = f"{sanitize_filename(str(subject), default='message')}.eml"
    # message/rfc822 parts are not base64-encoded per RFC 2046 5.2.1; the
    # content manager handles this automatically for Message/EmailMessage payloads.
    email_msg.add_attachment(nested_eml, subtype="rfc822", filename=filename)


def _set_attachments(
    email_msg: EmailMessage,
    msg: Any,
    html_body: str | None,
    warnings: list[str],
    depth: int,
) -> None:
    related_target: EmailMessage | None = None

    for index, attachment in enumerate(getattr(msg, "attachments", None) or []):
        try:
            if is_nested_message(attachment):
                _add_nested_message(email_msg, attachment, index, warnings, depth)
                continue

            data = getattr(attachment, "data", None)
            if not isinstance(data, (bytes, bytearray)):
                warnings.append(f"Attachment {index} has no readable data; skipped")
                continue

            filename = attachment_filename(attachment, index)
            maintype, subtype = guess_mime_type(attachment, filename)
            cid = clean_content_id(
                getattr(attachment, "cid", None) or getattr(attachment, "contentId", None)
            )

            if is_inline_referenced(cid, html_body):
                if related_target is None:
                    related_target = _promote_to_related(email_msg)
                related_target.add_related(
                    bytes(data), maintype, subtype, cid=f"<{cid}>", filename=filename
                )
            else:
                email_msg.add_attachment(
                    bytes(data), maintype=maintype, subtype=subtype, filename=filename
                )
        except Exception:
            logger.debug("Failed to attach attachment %s", index, exc_info=True)
            warnings.append(f"Attachment {index} could not be attached and was skipped")


def build_eml(msg: Any, *, warnings: list[str] | None = None, _depth: int = 0) -> EmailMessage:
    """Build an :class:`EmailMessage` from a parsed .msg object.

    ``msg`` may be a real ``extract_msg.Message`` (or any of its
    subclasses) or a duck-typed fake exposing the same attributes. This
    function does not check the message class -- callers that only want to
    convert top-level email items should check
    :func:`msg2eml.msgclass.is_convertible` first. Nested .msg attachments
    are always converted regardless of their own class, so no attached
    data is silently dropped.
    """
    if warnings is None:
        warnings = []
    if _depth > _MAX_NESTING_DEPTH:
        raise ConversionError("Nested .msg attachments are nested too deeply")

    email_msg = EmailMessage(policy=_EML_POLICY)
    _set_headers(email_msg, msg, warnings)
    html_body = _set_body(email_msg, msg, warnings)
    _set_attachments(email_msg, msg, html_body, warnings, _depth)
    return email_msg


def convert_file(input_path: Path, output_path: Path, *, force: bool = False) -> ConversionResult:
    """Convert a single .msg file on disk to a .eml file on disk.

    Never raises: any failure is captured in the returned
    :class:`ConversionResult` with ``status="failed"``, so a batch run can
    continue past malformed or unreadable input files.
    """
    warnings: list[str] = []
    try:
        if output_path.exists() and not force:
            return ConversionResult(
                input_path,
                "failed",
                warnings=warnings,
                error=f"Output file already exists: {output_path} (use --force to overwrite)",
            )

        try:
            opened = extract_msg.openMsg(str(input_path))
        except ExMsgBaseException as exc:
            kind = type(exc).__name__
            if kind in {"UnsupportedMSGTypeError", "UnrecognizedMSGTypeError"}:
                warnings.append(f"Skipped: {exc}")
                return ConversionResult(input_path, "skipped", warnings=warnings)
            raise

        with opened as msg:
            class_type = getattr(msg, "classType", None)
            if not msgclass.is_convertible(class_type):
                warnings.append(
                    f"Skipped: message class {msgclass.describe(class_type)} "
                    "is not a supported email type"
                )
                return ConversionResult(input_path, "skipped", warnings=warnings)

            email_msg = build_eml(msg, warnings=warnings)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(email_msg.as_bytes())
        return ConversionResult(input_path, "converted", output_path=output_path, warnings=warnings)
    except Exception as exc:
        logger.debug("Failed to convert %s", input_path, exc_info=True)
        return ConversionResult(input_path, "failed", warnings=warnings, error=str(exc))
