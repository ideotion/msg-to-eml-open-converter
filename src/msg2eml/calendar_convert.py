"""Build an iCalendar VEVENT (.ics) from an Outlook calendar/meeting .msg object.

Covers ``IPM.Appointment`` and the ``IPM.Schedule.Meeting.*`` family (all of
which extract-msg exposes through the same ``CalendarBase``-derived
property set). This intentionally produces a **standalone** .ics file, not
an invite-shaped email with an embedded ``text/calendar`` part -- see
PLAN.md / the project discussion for why that's a deliberate, separate
follow-up (Thunderbird's plain file-based .ics import has no UID/SEQUENCE
aware update logic, unlike its mail-integrated meeting-invite handling).

Recurring events are exported as a single, non-recurring VEVENT representing
just the master occurrence's start/end time, with a warning -- decoding
MAPI's recurrence blob into an RRULE is out of scope for this pass.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from icalendar import Calendar, Event, vCalAddress, vText

# extract_msg.enums.MeetingRecipientType: ORGANIZER=1,
# SENDABLE_OPTIONAL_ATTENDEE=2, SENDABLE_RESOURCE_OBJECT=3. Anything else
# (including the common case of an unset/0 value) is a required attendee --
# there is no explicit "required" member because it's MAPI's default.
_ORGANIZER_TYPE = 1
_OPTIONAL_TYPE = 2
_RESOURCE_TYPE = 3

# extract_msg.enums.BusyStatus: OL_FREE=0, OL_TENTATIVE=1, OL_BUSY=2,
# OL_OUT_OF_OFFICE=3, OL_WORKING_ELSEWHERE=4.
_FREE_BUSY_STATUS = 0
_TENTATIVE_BUSY_STATUS = 1


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _derive_uid(msg: Any) -> str:
    """Derive a stable UID from extract-msg's Global Object ID (MS-OXOCAL).

    Prefers cleanGlobalObjectID (stable across a recurring series) over the
    plain globalObjectID (which can include exception-specific date info),
    falling back to a random UID if neither is present.
    """
    for attr in ("cleanGlobalObjectID", "globalObjectID"):
        global_id = getattr(msg, attr, None)
        if global_id:
            try:
                return f"{bytes(global_id).hex()}@msg2eml"
            except (TypeError, ValueError):
                continue
    return f"{uuid.uuid4()}@msg2eml"


def _organizer_address(msg: Any) -> vCalAddress | None:
    raw = getattr(msg, "organizer", None)
    if not raw:
        return None
    name, addr = parseaddr(str(raw))
    if not addr:
        return None
    organizer = vCalAddress(f"MAILTO:{addr}")
    if name:
        organizer.params["cn"] = vText(name)
    return organizer


def _attendee_role(recipient_type: Any) -> str | None:
    """iCalendar ROLE for a recipient, or None if they're the organizer.

    The organizer is represented separately via the ORGANIZER property, so
    an attendee whose type identifies them as the organizer is skipped here
    to avoid listing them twice.
    """
    value = _as_int(recipient_type)
    if value == _ORGANIZER_TYPE:
        return None
    if value == _OPTIONAL_TYPE:
        return "OPT-PARTICIPANT"
    if value == _RESOURCE_TYPE:
        return "NON-PARTICIPANT"
    return "REQ-PARTICIPANT"


def _add_attendees(event: Event, msg: Any) -> None:
    for recipient in getattr(msg, "recipients", None) or []:
        addr = getattr(recipient, "email", None)
        if not addr:
            continue
        role = _attendee_role(getattr(recipient, "type", None))
        if role is None:
            continue
        attendee = vCalAddress(f"MAILTO:{addr}")
        attendee.params["role"] = vText(role)
        attendee.params["partstat"] = vText("NEEDS-ACTION")
        name = getattr(recipient, "name", None)
        if name and name != addr:
            attendee.params["cn"] = vText(str(name))
        event.add("attendee", attendee, encode=False)


def _event_status(msg: Any) -> str:
    class_type = (getattr(msg, "classType", None) or "").lower()
    if "cancel" in class_type:
        return "CANCELLED"
    if _as_int(getattr(msg, "busyStatus", None)) == _TENTATIVE_BUSY_STATUS:
        return "TENTATIVE"
    return "CONFIRMED"


def build_ics(msg: Any, *, warnings: list[str] | None = None) -> bytes:
    """Build a standalone iCalendar VEVENT (.ics) document from a calendar .msg object."""
    if warnings is None:
        warnings = []

    calendar = Calendar()
    calendar.add("prodid", "-//msg2eml//msg2eml//EN")
    calendar.add("version", "2.0")

    event = Event()
    subject = getattr(msg, "subject", None)
    event.add("summary", str(subject) if subject else "Untitled event")

    location = getattr(msg, "location", None)
    if location:
        event.add("location", str(location))

    body = getattr(msg, "body", None)
    if body:
        event.add("description", str(body))

    all_day = bool(getattr(msg, "appointmentSubType", False))
    start = getattr(msg, "appointmentStartWhole", None)
    end = getattr(msg, "appointmentEndWhole", None)
    if isinstance(start, datetime):
        event.add("dtstart", start.date() if all_day else start)
    else:
        warnings.append("Event has no start time")
    if isinstance(end, datetime):
        event.add("dtend", end.date() if all_day else end)

    if bool(getattr(msg, "isRecurring", False) or getattr(msg, "recurring", False)):
        warnings.append(
            "Recurring event: only a single occurrence was exported "
            "(the recurrence pattern is not yet converted)"
        )

    organizer = _organizer_address(msg)
    if organizer is not None:
        event["organizer"] = organizer
    else:
        warnings.append("Event has no organizer")

    _add_attendees(event, msg)

    sequence = _as_int(getattr(msg, "appointmentSequence", None))
    if sequence is not None:
        event.add("sequence", sequence)

    event.add("status", _event_status(msg))
    event.add(
        "transp",
        "TRANSPARENT"
        if _as_int(getattr(msg, "busyStatus", None)) == _FREE_BUSY_STATUS
        else "OPAQUE",
    )

    event.add("dtstamp", datetime.now(timezone.utc))
    event["uid"] = _derive_uid(msg)

    calendar.add_component(event)
    return calendar.to_ical()
