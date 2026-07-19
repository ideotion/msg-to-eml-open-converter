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


@dataclass
class FakeContact:
    """A minimal stand-in for an extract_msg Contact object."""

    classType: str | None = "IPM.Contact"
    displayName: str | None = None
    givenName: str | None = None
    surname: str | None = None
    middleName: str | None = None
    displayNamePrefix: str | None = None
    generation: str | None = None
    companyName: str | None = None
    jobTitle: str | None = None
    email1EmailAddress: str | None = None
    email2EmailAddress: str | None = None
    email3EmailAddress: str | None = None
    businessTelephoneNumber: str | None = None
    homeTelephoneNumber: str | None = None
    mobileTelephoneNumber: str | None = None
    businessFaxNumber: str | None = None
    homeFaxNumber: str | None = None
    workAddressStreet: str | None = None
    workAddressLocality: str | None = None
    workAddressStateOrProvince: str | None = None
    workAddressPostalCode: str | None = None
    workAddressCountry: str | None = None
    workAddressPostOfficeBox: str | None = None
    homeAddressStreet: str | None = None
    homeAddressLocality: str | None = None
    homeAddressStateOrProvince: str | None = None
    homeAddressPostalCode: str | None = None
    homeAddressCountry: str | None = None
    homeAddressPostOfficeBox: str | None = None
    otherAddressStreet: str | None = None
    otherAddressLocality: str | None = None
    otherAddressStateOrProvince: str | None = None
    otherAddressPostalCode: str | None = None
    otherAddressCountry: str | None = None
    otherAddressPostOfficeBox: str | None = None
    birthday: datetime | None = None
    contactPhoto: bytes | None = None
    body: str | None = None
    webpageUrl: str | None = None

    def __enter__(self) -> FakeContact:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


@dataclass
class FakeTask:
    """A minimal stand-in for an extract_msg Task object."""

    classType: str | None = "IPM.Task"
    subject: str | None = "Test task"
    body: str | None = None
    taskStartDate: datetime | None = None
    taskDueDate: datetime | None = None
    taskStatus: Any = None
    percentComplete: float | None = None
    taskDateCompleted: datetime | None = None
    importance: Any = None

    def __enter__(self) -> FakeTask:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


@dataclass
class FakeCalendarItem:
    """A minimal stand-in for an extract_msg CalendarBase-derived object."""

    classType: str | None = "IPM.Appointment"
    subject: str | None = "Test appointment"
    body: str | None = None
    location: str | None = None
    organizer: str | None = None
    appointmentStartWhole: datetime | None = None
    appointmentEndWhole: datetime | None = None
    appointmentSequence: int | None = None
    appointmentSubType: bool = False
    busyStatus: int | None = None
    isRecurring: bool = False
    recurring: bool = False
    globalObjectID: Any = None
    cleanGlobalObjectID: Any = None
    recipients: list[Any] = field(default_factory=list)

    def __enter__(self) -> FakeCalendarItem:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None
