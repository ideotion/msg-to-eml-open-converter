"""Build an iCalendar VTODO (.ics) from an Outlook task (IPM.Task) .msg object.

Written against duck-typed "parsed message" objects, matching the rest of
this package -- see :mod:`msg2eml.convert`. Like vCard, iCalendar's TEXT
values are escaped by the ``icalendar`` library itself, so no separate
CR/LF-injection hardening is needed here (verified empirically: an embedded
newline is rendered as a literal ``\\n`` escape sequence, never a raw line
break).
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone
from typing import Any

from icalendar import Calendar, Todo

# extract_msg.enums.TaskStatus: NOT_STARTED=0, IN_PROGRESS=1, COMPLETE=2,
# WAITING_ON_OTHER=3, DEFERRED=4. iCalendar VTODO STATUS has no direct
# equivalent for "waiting on other"/"deferred", so both fold to NEEDS-ACTION.
_STATUS_MAP: dict[int, str] = {
    0: "NEEDS-ACTION",
    1: "IN-PROCESS",
    2: "COMPLETED",
    3: "NEEDS-ACTION",
    4: "NEEDS-ACTION",
}

# extract_msg.enums.Importance: LOW=0, MEDIUM=1, HIGH=2. iCalendar PRIORITY
# is 1 (highest) - 9 (lowest), 5 is "normal", 0 is undefined.
_PRIORITY_MAP: dict[int, int] = {0: 9, 1: 5, 2: 1}


def _status_value(task_status: Any) -> str:
    try:
        return _STATUS_MAP[int(task_status)]
    except (TypeError, ValueError, KeyError):
        return "NEEDS-ACTION"


def _priority_value(importance: Any) -> int | None:
    try:
        return _PRIORITY_MAP[int(importance)]
    except (TypeError, ValueError, KeyError):
        return None


def _derive_uid(msg: Any) -> str:
    """Derive a stable UID from extract-msg's taskGlobalID when available.

    Falling back to a random one (like msg2eml.headers does for a missing
    Message-ID) is an acceptable simplification here: unlike calendar
    meetings, tasks don't go through a multi-party update/reimport workflow
    where UID stability across conversions is critical.
    """
    global_id = getattr(msg, "taskGlobalID", None)
    if global_id:
        try:
            return f"{bytes(global_id).hex()}@msg2eml"
        except (TypeError, ValueError):
            pass
    return f"{uuid.uuid4()}@msg2eml"


def build_task_ics(msg: Any, *, warnings: list[str] | None = None) -> bytes:
    """Build a standalone iCalendar VTODO (.ics) document from a task .msg object."""
    if warnings is None:
        warnings = []

    calendar = Calendar()
    calendar.add("prodid", "-//msg2eml//msg2eml//EN")
    calendar.add("version", "2.0")

    todo = Todo()
    subject = getattr(msg, "subject", None)
    todo.add("summary", str(subject) if subject else "Untitled task")

    body = getattr(msg, "body", None)
    if body:
        todo.add("description", str(body))

    due = getattr(msg, "taskDueDate", None)
    if isinstance(due, datetime):
        todo.add("due", due)
    else:
        warnings.append("Task has no due date")

    start = getattr(msg, "taskStartDate", None)
    if isinstance(start, datetime):
        todo.add("dtstart", start)

    completed = getattr(msg, "taskDateCompleted", None)
    if isinstance(completed, datetime):
        todo.add("completed", completed)

    percent = getattr(msg, "percentComplete", None)
    if percent is not None:
        with contextlib.suppress(TypeError, ValueError):
            todo.add("percent-complete", max(0, min(100, round(float(percent) * 100))))

    todo.add("status", _status_value(getattr(msg, "taskStatus", None)))

    priority = _priority_value(getattr(msg, "importance", None))
    if priority is not None:
        todo.add("priority", priority)

    todo.add("dtstamp", datetime.now(timezone.utc))
    todo["uid"] = _derive_uid(msg)

    calendar.add_component(todo)
    return calendar.to_ical()
