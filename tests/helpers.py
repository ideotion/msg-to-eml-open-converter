"""Shared duck-typed fakes standing in for extract_msg parsed-message objects.

None of these import extract_msg: they only need to satisfy the attribute
access patterns msg2eml.convert/headers/attachments use, which keeps the
unit tests fast and independent of any real .msg file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FakeRecipient:
    email: str
    name: str = ""
    type: int = 1  # MAPI_TO


@dataclass
class FakeAttachment:
    data: Any
    name: str = "attachment"
    longFilename: str = ""
    shortFilename: str = ""
    mimetype: str | None = None
    cid: str | None = None
    type: int | None = 0  # AttachmentType.DATA

    def getFilename(self) -> str:
        return self.name


@dataclass
class FakeMsg:
    """A minimal stand-in for an extract_msg parsed message."""

    subject: str | None = "Test subject"
    sender: str | None = "Sender Name <sender@example.com>"
    to: str | None = None
    cc: str | None = None
    bcc: str | None = None
    date: datetime | None = None
    messageId: str | None = "<test@example.com>"
    inReplyTo: str | None = None
    header: Any = None
    body: str | None = "Plain text body."
    htmlBody: str | None = None
    rtfBody: bytes | None = None
    classType: str | None = "IPM.Note"
    recipients: list[Any] = field(default_factory=list)
    attachments: list[Any] = field(default_factory=list)
