"""Shared duck-typed fakes standing in for extract_msg parsed-message objects.

None of these import extract_msg: they only need to satisfy the attribute
access patterns msg2eml.convert/headers/attachments use, which keeps the
unit tests fast and independent of any real .msg file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: The OLE2 Compound File Binary Format signature every real .msg file
#: starts with. msg2eml.convert._open_and_build sniffs this before ever
#: calling extract_msg.openMsg, so any test that exercises that path --
#: even with extract_msg.openMsg itself monkeypatched away -- needs its
#: placeholder file/bytes to start with this, or it never reaches the mock.
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


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

    def __enter__(self) -> FakeMsg:
        """Support use as a stand-in for extract_msg.openMsg()'s context manager result."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None
