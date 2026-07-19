from __future__ import annotations

from datetime import datetime, timezone

from icalendar import Calendar

from msg2eml.task_convert import build_task_ics
from tests.helpers import FakeTask


def _parse_todo(raw: bytes):
    cal = Calendar.from_ical(raw)
    (todo,) = list(cal.walk("VTODO"))
    return todo


def test_minimal_task_produces_valid_vtodo() -> None:
    task = FakeTask(subject="Écrire le rapport")
    warnings: list[str] = []
    raw = build_task_ics(task, warnings=warnings)

    assert raw.startswith(b"BEGIN:VCALENDAR\r\n")
    todo = _parse_todo(raw)
    assert str(todo.get("summary")) == "Écrire le rapport"
    assert todo.get("status") == "NEEDS-ACTION"
    assert any("no due date" in w for w in warnings)


def test_full_task_maps_all_fields() -> None:
    task = FakeTask(
        subject="Finaliser le budget",
        body="Voir avec Étienne pour les chiffres.",
        taskStartDate=datetime(2026, 3, 1, tzinfo=timezone.utc),
        taskDueDate=datetime(2026, 3, 10, 17, 0, tzinfo=timezone.utc),
        taskStatus=1,  # IN_PROGRESS
        percentComplete=0.5,
        importance=2,  # HIGH
    )
    raw = build_task_ics(task)
    todo = _parse_todo(raw)

    assert str(todo.get("summary")) == "Finaliser le budget"
    assert str(todo.get("description")) == "Voir avec Étienne pour les chiffres."
    assert todo.get("dtstart").dt == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert todo.get("due").dt == datetime(2026, 3, 10, 17, 0, tzinfo=timezone.utc)
    assert todo.get("status") == "IN-PROCESS"
    assert int(todo.get("percent-complete")) == 50
    assert int(todo.get("priority")) == 1
    assert todo.get("uid")


def test_completed_task_status_and_completed_date() -> None:
    task = FakeTask(
        subject="Done task",
        taskStatus=2,  # COMPLETE
        taskDateCompleted=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    raw = build_task_ics(task)
    todo = _parse_todo(raw)
    assert todo.get("status") == "COMPLETED"
    assert todo.get("completed").dt == datetime(2026, 1, 5, tzinfo=timezone.utc)


def test_unknown_status_and_importance_degrade_gracefully() -> None:
    task = FakeTask(subject="Weird", taskStatus=99, importance=99)
    raw = build_task_ics(task)
    todo = _parse_todo(raw)
    assert todo.get("status") == "NEEDS-ACTION"
    assert todo.get("priority") is None


def test_task_with_no_subject_gets_placeholder() -> None:
    task = FakeTask(subject=None)
    raw = build_task_ics(task)
    todo = _parse_todo(raw)
    assert str(todo.get("summary")) == "Untitled task"


def test_task_uid_uses_task_global_id_when_present() -> None:
    task = FakeTask(subject="X")
    task.taskGlobalID = b"\x01\x02\x03"  # type: ignore[attr-defined]
    raw = build_task_ics(task)
    todo = _parse_todo(raw)
    assert str(todo.get("uid")) == "010203@msg2eml"


def test_two_tasks_without_global_id_get_different_uids() -> None:
    raw1 = build_task_ics(FakeTask(subject="A"))
    raw2 = build_task_ics(FakeTask(subject="B"))
    uid1 = _parse_todo(raw1).get("uid")
    uid2 = _parse_todo(raw2).get("uid")
    assert str(uid1) != str(uid2)
