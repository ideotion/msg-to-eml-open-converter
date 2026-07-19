from __future__ import annotations

from datetime import date, datetime, timezone

from icalendar import Calendar

from msg2eml.calendar_convert import build_ics
from tests.helpers import FakeCalendarItem, FakeRecipient


def _parse_event(raw: bytes):
    cal = Calendar.from_ical(raw)
    (event,) = list(cal.walk("VEVENT"))
    return event


def test_minimal_event_produces_valid_vevent() -> None:
    item = FakeCalendarItem(
        subject="Réunion budget",
        appointmentStartWhole=datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc),
        appointmentEndWhole=datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc),
    )
    warnings: list[str] = []
    raw = build_ics(item, warnings=warnings)

    assert raw.startswith(b"BEGIN:VCALENDAR\r\n")
    event = _parse_event(raw)
    assert str(event.get("summary")) == "Réunion budget"
    assert event.get("dtstart").dt == datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
    assert event.get("dtend").dt == datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc)
    assert event.get("status") == "CONFIRMED"
    assert event.get("uid")
    assert any("no organizer" in w for w in warnings)


def test_full_event_maps_organizer_attendees_location_sequence() -> None:
    item = FakeCalendarItem(
        subject="Point hebdomadaire",
        location="Salle Étoile",
        body="Ordre du jour: budget, planning.",
        organizer="Organisateur Étienne <organisateur@example.com>",
        appointmentStartWhole=datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc),
        appointmentEndWhole=datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc),
        appointmentSequence=2,
        recipients=[
            FakeRecipient(email="organisateur@example.com", name="Organisateur Étienne", type=1),
            FakeRecipient(email="alice@example.com", name="Alice Dupont", type=0),
            FakeRecipient(email="bob@example.com", name="Bob Optional", type=2),
            FakeRecipient(email="salle@example.com", name="Salle Étoile", type=3),
        ],
    )
    warnings: list[str] = []
    raw = build_ics(item, warnings=warnings)
    event = _parse_event(raw)

    assert str(event.get("location")) == "Salle Étoile"
    assert str(event.get("description")) == "Ordre du jour: budget, planning."
    assert event.get("sequence") == 2
    organizer = event.get("organizer")
    assert str(organizer) == "MAILTO:organisateur@example.com"
    assert str(organizer.params["cn"]) == "Organisateur Étienne"

    attendees = event.get("attendee")
    assert isinstance(attendees, list)
    assert len(attendees) == 3  # organizer recipient excluded, 3 real attendees remain
    by_email = {str(a).replace("MAILTO:", ""): a for a in attendees}
    assert by_email["alice@example.com"].params["role"] == "REQ-PARTICIPANT"
    assert by_email["bob@example.com"].params["role"] == "OPT-PARTICIPANT"
    assert by_email["salle@example.com"].params["role"] == "NON-PARTICIPANT"
    assert warnings == []


def test_all_day_event_uses_date_values() -> None:
    item = FakeCalendarItem(
        subject="Journée entière",
        appointmentStartWhole=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
        appointmentEndWhole=datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc),
        appointmentSubType=True,
    )
    raw = build_ics(item)
    event = _parse_event(raw)
    assert event.get("dtstart").dt == date(2026, 3, 1)
    assert event.get("dtend").dt == date(2026, 3, 2)


def test_recurring_event_warns_and_exports_single_occurrence() -> None:
    item = FakeCalendarItem(
        subject="Réunion hebdomadaire",
        appointmentStartWhole=datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc),
        appointmentEndWhole=datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc),
        isRecurring=True,
    )
    warnings: list[str] = []
    raw = build_ics(item, warnings=warnings)
    event = _parse_event(raw)
    assert "RRULE" not in raw.decode()
    assert event.get("dtstart") is not None
    assert any("Recurring event" in w for w in warnings)


def test_cancelled_meeting_gets_cancelled_status() -> None:
    item = FakeCalendarItem(classType="IPM.Schedule.Meeting.Canceled", subject="Annulée")
    raw = build_ics(item)
    event = _parse_event(raw)
    assert event.get("status") == "CANCELLED"


def test_tentative_busy_status_maps_to_tentative() -> None:
    item = FakeCalendarItem(subject="Tentative", busyStatus=1)
    raw = build_ics(item)
    event = _parse_event(raw)
    assert event.get("status") == "TENTATIVE"


def test_free_busy_status_maps_to_transparent() -> None:
    item = FakeCalendarItem(subject="Free time", busyStatus=0)
    raw = build_ics(item)
    event = _parse_event(raw)
    assert str(event.get("transp")) == "TRANSPARENT"


def test_busy_status_maps_to_opaque() -> None:
    item = FakeCalendarItem(subject="Busy time", busyStatus=2)
    raw = build_ics(item)
    event = _parse_event(raw)
    assert str(event.get("transp")) == "OPAQUE"


def test_uid_derived_from_global_object_id_is_stable() -> None:
    item1 = FakeCalendarItem(subject="A", cleanGlobalObjectID=b"\xaa\xbb\xcc")
    item2 = FakeCalendarItem(subject="A changed", cleanGlobalObjectID=b"\xaa\xbb\xcc")
    uid1 = str(_parse_event(build_ics(item1)).get("uid"))
    uid2 = str(_parse_event(build_ics(item2)).get("uid"))
    assert uid1 == uid2 == "aabbcc@msg2eml"


def test_missing_start_time_warns() -> None:
    item = FakeCalendarItem(subject="No start", appointmentStartWhole=None)
    warnings: list[str] = []
    build_ics(item, warnings=warnings)
    assert any("no start time" in w for w in warnings)
