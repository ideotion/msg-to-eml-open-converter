"""Core conversion: dispatch a parsed .msg object to its matching builder.

:func:`_build_for_msg` classifies a parsed .msg object by
:class:`msg2eml.msgclass.MessageKind` and hands it to the builder for that
kind -- :func:`build_eml` for email, or the ``build_ics``/``build_vcard``
functions in :mod:`msg2eml.calendar_convert`, :mod:`msg2eml.contact_convert`,
and :mod:`msg2eml.task_convert` for calendar, contact, and task items. Every
builder is written entirely against duck-typed "parsed message" objects --
only ``getattr``, never ``isinstance`` checks against ``extract_msg``
classes -- so each can be unit tested with simple fakes and doesn't care
whether it's called with a real ``extract_msg`` object or a nested embedded
message object.

Headers of the ``.eml`` output are built with ``email.policy.default`` (not
``utf8=True``): this produces real RFC 2047 encoded headers for non-ASCII
content, which is readable by every standards-compliant client, rather than
raw UTF-8 headers that require SMTPUTF8 support.
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

from msg2eml import calendar_convert, contact_convert, headers, msgclass, rtf, task_convert
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
    output_format: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class BuildOutput:
    """The built output of converting one parsed .msg object.

    ``content`` is always the ready-to-write bytes of the output document,
    regardless of kind. ``email_message`` is populated only when ``kind`` is
    :attr:`msgclass.MessageKind.EMAIL`: a nested email-kind .msg attachment
    must be attached as a ``message/rfc822`` part using the actual
    ``EmailMessage`` object (not raw bytes), so the content manager encodes
    it per RFC 2046 5.2.1 instead of base64-encoding it like an opaque blob.
    """

    kind: msgclass.MessageKind
    extension: str
    maintype: str
    subtype: str
    content: bytes
    email_message: EmailMessage | None = None


def _as_text(value: Any) -> str | None:
    """Decode a body value (bytes or str) to a non-empty str, or None."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not value:
        return None
    return str(value)


def _set_header(email_msg: EmailMessage, name: str, value: str) -> None:
    """Assign a header value, stripped of any embedded CR/LF.

    Every header value in this module ultimately originates from
    attacker-controllable .msg file content, so every assignment goes
    through this one chokepoint rather than trusting each call site to
    remember to sanitize -- see :func:`msg2eml.headers.sanitize_header_value`.
    """
    email_msg[name] = headers.sanitize_header_value(value)


def _set_headers(email_msg: EmailMessage, msg: Any, warnings: list[str]) -> None:
    subject = getattr(msg, "subject", None)
    if subject:
        _set_header(email_msg, "Subject", str(subject))

    sender = headers.normalize_mailbox(getattr(msg, "sender", None))
    if sender:
        _set_header(email_msg, "From", sender)
    else:
        warnings.append("Message has no sender; From header omitted")

    groups = headers.grouped_recipients(msg)
    any_recipients = any(groups.values())
    if any_recipients:
        for header_name, key in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
            if groups[key]:
                _set_header(email_msg, header_name, headers.address_header_value(groups[key]))
    else:
        # No recipient table at all: fall back to extract-msg's raw display strings.
        for header_name, attr in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
            raw = getattr(msg, attr, None)
            if raw:
                _set_header(email_msg, header_name, str(raw))

    date = headers.resolve_date(msg)
    if date is not None:
        _set_header(email_msg, "Date", format_datetime(date))
    else:
        warnings.append("Message has no date; Date header omitted")

    message_id, generated = headers.resolve_message_id(msg)
    _set_header(email_msg, "Message-ID", message_id)
    if generated:
        warnings.append("Message had no Message-ID; a synthetic one was generated")

    in_reply_to = headers.resolve_in_reply_to(msg)
    if in_reply_to:
        _set_header(email_msg, "In-Reply-To", in_reply_to)

    references = headers.resolve_references(msg)
    if references:
        _set_header(email_msg, "References", references)


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
        output = _build_for_msg(nested_msg, nested_warnings, depth + 1)
    except Exception:
        logger.debug("Failed to convert nested .msg attachment %s", index, exc_info=True)
        warnings.append(f"Nested message attachment {index} could not be converted and was skipped")
        return

    warnings.extend(f"(nested attachment {index}) {w}" for w in nested_warnings)
    if output is None:
        # A skip reason was already recorded in nested_warnings above (e.g. a
        # calendar invite or contact card attached as a file, of a kind
        # msg2eml doesn't support embedding as a nested attachment yet).
        return

    if output.email_message is not None:
        title = output.email_message.get("Subject") or "message"
    else:
        # Contacts have no "subject" -- fall back to their display name.
        title = (
            getattr(nested_msg, "subject", None)
            or getattr(nested_msg, "displayName", None)
            or "attachment"
        )
    filename = f"{sanitize_filename(str(title), default='message')}.{output.extension}"

    if output.email_message is not None:
        # message/rfc822 parts are not base64-encoded per RFC 2046 5.2.1; the
        # content manager handles this automatically for Message/EmailMessage payloads.
        email_msg.add_attachment(output.email_message, subtype="rfc822", filename=filename)
    else:
        email_msg.add_attachment(
            output.content, maintype=output.maintype, subtype=output.subtype, filename=filename
        )


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


def _build_for_msg(msg: Any, warnings: list[str], depth: int) -> BuildOutput | None:
    """Dispatch a parsed .msg object to the builder matching its message kind.

    Returns ``None`` if the message class isn't a kind msg2eml can convert (a
    "Skipped: ..." warning is appended in that case). Exceptions from the
    underlying builder propagate to the caller.
    """
    class_type = getattr(msg, "classType", None)
    kind = msgclass.classify(class_type)

    if kind is msgclass.MessageKind.EMAIL:
        email_msg = build_eml(msg, warnings=warnings, _depth=depth)
        return BuildOutput(
            kind=kind,
            extension="eml",
            maintype="message",
            subtype="rfc822",
            content=email_msg.as_bytes(),
            email_message=email_msg,
        )
    if kind is msgclass.MessageKind.CALENDAR:
        return BuildOutput(
            kind=kind,
            extension="ics",
            maintype="text",
            subtype="calendar",
            content=calendar_convert.build_ics(msg, warnings=warnings),
        )
    if kind is msgclass.MessageKind.CONTACT:
        return BuildOutput(
            kind=kind,
            extension="vcf",
            maintype="text",
            subtype="vcard",
            content=contact_convert.build_vcard(msg, warnings=warnings),
        )
    if kind is msgclass.MessageKind.TASK:
        return BuildOutput(
            kind=kind,
            extension="ics",
            maintype="text",
            subtype="calendar",
            content=task_convert.build_task_ics(msg, warnings=warnings),
        )

    warnings.append(
        f"Skipped: message class {msgclass.describe(class_type)} is not a supported type"
    )
    return None


_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _looks_like_ole2(source: str | bytes) -> bool:
    """Sniff the OLE2 Compound File Binary Format signature every .msg file has.

    Checked upfront so obviously-invalid input gets one clean, consistent
    error message instead of whatever ``extract_msg.openMsg`` happens to
    raise for it -- notably, handed a short byte string that could plausibly
    be a path, it tries to open it as a file and raises a raw
    ``FileNotFoundError`` quoting the bytes back verbatim, which is a
    confusing message for something that was never meant to be a path.
    """
    if isinstance(source, bytes):
        return source.startswith(_OLE2_MAGIC)
    try:
        with open(source, "rb") as fh:
            return fh.read(len(_OLE2_MAGIC)) == _OLE2_MAGIC
    except OSError:
        return False


def _open_and_build(source: str | bytes, warnings: list[str]) -> BuildOutput | None:
    """Open a .msg source and dispatch it to the builder matching its message kind.

    ``source`` is anything ``extract_msg.openMsg`` accepts -- a file path
    string or raw bytes -- which lets this same helper back both on-disk
    (:func:`convert_file`) and in-memory (:func:`convert_bytes`) conversion,
    so every caller shares one code path for message-kind dispatch and the
    header/body/attachment hardening in :func:`build_eml`.

    Returns ``None`` if the message class isn't a supported kind (a
    "Skipped: ..." warning is appended in that case). Exceptions propagate to
    the caller, which is expected to catch them broadly -- a genuinely
    unreadable/corrupt file must never raise all the way to a batch loop.
    """
    if not _looks_like_ole2(source):
        raise ConversionError("This is not a valid .msg file (not an OLE2 compound file)")

    try:
        opened = extract_msg.openMsg(source)
    except ExMsgBaseException as exc:
        kind = type(exc).__name__
        if kind in {"UnsupportedMSGTypeError", "UnrecognizedMSGTypeError"}:
            warnings.append(f"Skipped: {exc}")
            return None
        raise

    with opened as msg:
        return _build_for_msg(msg, warnings, 0)


def convert_file(input_path: Path, output_path: Path, *, force: bool = False) -> ConversionResult:
    """Convert a single .msg file on disk to its matching output file on disk.

    The output's real extension depends on the source message's kind (e.g.
    ``.eml`` for email, ``.ics`` for calendar/task items, ``.vcf`` for
    contacts), which isn't known until the file is opened and classified --
    so ``output_path``'s extension is only a placeholder, swapped for the
    real one before writing. Never raises: any failure is captured in the
    returned :class:`ConversionResult` with ``status="failed"``, so a batch
    run can continue past malformed or unreadable input files.
    """
    warnings: list[str] = []
    try:
        output = _open_and_build(str(input_path), warnings)
        if output is None:
            return ConversionResult(input_path, "skipped", warnings=warnings)

        final_output_path = output_path.with_suffix(f".{output.extension}")
        if final_output_path.exists() and not force:
            return ConversionResult(
                input_path,
                "failed",
                warnings=warnings,
                error=f"Output file already exists: {final_output_path} (use --force to overwrite)",
            )

        final_output_path.parent.mkdir(parents=True, exist_ok=True)
        final_output_path.write_bytes(output.content)
        return ConversionResult(
            input_path,
            "converted",
            output_path=final_output_path,
            output_format=output.extension,
            warnings=warnings,
        )
    except Exception as exc:
        logger.debug("Failed to convert %s", input_path, exc_info=True)
        return ConversionResult(input_path, "failed", warnings=warnings, error=str(exc))


@dataclass
class BytesConversionResult:
    """Outcome of converting in-memory .msg bytes (used by the local web UI)."""

    filename: str
    status: Status
    output_bytes: bytes | None = None
    output_format: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def convert_bytes(data: bytes, filename: str) -> BytesConversionResult:
    """Convert raw .msg bytes to output bytes, entirely in memory.

    Never raises, for the same reason :func:`convert_file` doesn't: a
    malformed upload must become a "failed" result, not a crash.
    """
    warnings: list[str] = []
    try:
        output = _open_and_build(data, warnings)
        if output is None:
            return BytesConversionResult(filename, "skipped", warnings=warnings)
        return BytesConversionResult(
            filename,
            "converted",
            output_bytes=output.content,
            output_format=output.extension,
            warnings=warnings,
        )
    except Exception as exc:
        logger.debug("Failed to convert %s", filename, exc_info=True)
        return BytesConversionResult(filename, "failed", warnings=warnings, error=str(exc))
