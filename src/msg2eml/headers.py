"""Header construction helpers: addresses, recipients, and message identifiers.

Recipients are read from ``msg.recipients`` (a list of MAPI recipient
objects with ``.name``/``.email``/``.type``) rather than the ``msg.to`` /
``msg.cc`` / ``msg.bcc`` strings extract-msg also exposes, because those
strings are semicolon-joined display text meant for humans, not a
comma-separated RFC 5322 mailbox list. ``msg.to`` etc. are used only as a
last-resort fallback when a message has no recipient table at all.
"""

from __future__ import annotations

import re
from datetime import datetime
from email.utils import formataddr, make_msgid, parseaddr
from typing import Any

from extract_msg.enums import RecipientType

Mailbox = tuple[str, str]

_HEADER_LINEBREAK_RE = re.compile(r"[\r\n]+")


def sanitize_header_value(value: str) -> str:
    """Strip embedded CR/LF from a value bound for a header.

    ``email.policy.default`` refuses to serialize a header value containing
    a raw line break at all -- it raises ``ValueError`` -- which would fail
    the whole message's conversion over a single stray control character in,
    say, a subject line pulled from a messy or malicious .msg file. Folding
    those characters out here means the header still gets a value (with the
    injection attempt neutralized) and the rest of the conversion proceeds.
    """
    return _HEADER_LINEBREAK_RE.sub(" ", value).strip()


def normalize_mailbox(raw: str | None) -> str | None:
    """Normalize a "Name <addr>" or bare-address string into a clean mailbox string."""
    if not raw or not raw.strip():
        return None
    name, addr = parseaddr(raw)
    if not addr:
        return raw.strip()
    return formataddr((name, addr))


def _recipient_mailbox(recipient: Any) -> Mailbox | None:
    addr = getattr(recipient, "email", None)
    if not addr:
        return None
    name = getattr(recipient, "name", None) or ""
    if name == addr:
        name = ""
    return name, addr


def grouped_recipients(msg: Any) -> dict[str, list[Mailbox]]:
    """Group msg.recipients into to/cc/bcc lists of (name, address) pairs."""
    groups: dict[str, list[Mailbox]] = {"to": [], "cc": [], "bcc": []}
    for recipient in getattr(msg, "recipients", None) or []:
        mailbox = _recipient_mailbox(recipient)
        if mailbox is None:
            continue
        rtype = getattr(recipient, "type", None)
        if rtype == RecipientType.CC:
            groups["cc"].append(mailbox)
        elif rtype == RecipientType.BCC:
            groups["bcc"].append(mailbox)
        else:
            groups["to"].append(mailbox)
    return groups


def address_header_value(mailboxes: list[Mailbox]) -> str:
    """Join (name, addr) pairs into a comma-separated RFC 5322 mailbox list."""
    return ", ".join(formataddr(mailbox) for mailbox in mailboxes)


def resolve_message_id(msg: Any) -> tuple[str, bool]:
    """Return (message_id, was_generated). Generates one if the source has none."""
    candidate = getattr(msg, "messageId", None)
    if candidate:
        candidate = str(candidate).strip()
    if not candidate:
        header = getattr(msg, "header", None)
        header_value = header.get("Message-ID") if header else None
        candidate = header_value.strip() if header_value else None
    if candidate:
        return candidate, False
    return make_msgid(domain="msg2eml.invalid"), True


def resolve_in_reply_to(msg: Any) -> str | None:
    """Return the In-Reply-To header value, if any."""
    candidate = getattr(msg, "inReplyTo", None)
    if candidate and str(candidate).strip():
        return str(candidate).strip()
    header = getattr(msg, "header", None)
    value = header.get("In-Reply-To") if header else None
    return value.strip() if value else None


def resolve_references(msg: Any) -> str | None:
    """Return the References header value, if any.

    extract-msg exposes no dedicated ``references`` property, so this is
    read directly from the raw transport header block when one exists.
    """
    header = getattr(msg, "header", None)
    value = header.get("References") if header else None
    return value.strip() if value else None


def resolve_date(msg: Any) -> datetime | None:
    """Return the message's send date as a datetime, if a valid one exists."""
    value = getattr(msg, "date", None)
    return value if isinstance(value, datetime) else None
