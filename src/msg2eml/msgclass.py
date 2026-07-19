"""Classification of Outlook message classes (PidTagMessageClass).

Only plain email items (``IPM.Note`` and its variants, e.g. S/MIME signed
mail) are convertible to .eml. Everything else -- calendar items, contacts,
tasks, sticky notes, distribution lists, journal entries, and documents --
is detected so callers can skip it with an explicit warning instead of
producing a nonsensical or broken .eml file.
"""

from __future__ import annotations

from enum import Enum


class MessageKind(Enum):
    """The kind of Outlook item a message class string represents."""

    EMAIL = "email"
    CALENDAR = "calendar"
    CONTACT = "contact"
    TASK = "task"
    NOTE = "note"
    POST = "post"
    DISTRIBUTION_LIST = "distribution_list"
    JOURNAL = "journal"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


# Ordered by specificity: longer/more specific prefixes are irrelevant here
# since none of these prefixes overlap, but order is kept alphabetical by
# kind for readability.
_PREFIX_KINDS: tuple[tuple[str, MessageKind], ...] = (
    ("ipm.note", MessageKind.EMAIL),
    ("ipm.appointment", MessageKind.CALENDAR),
    ("ipm.schedule.meeting", MessageKind.CALENDAR),
    ("ipm.contact", MessageKind.CONTACT),
    ("ipm.task", MessageKind.TASK),
    ("ipm.stickynote", MessageKind.NOTE),
    ("ipm.post", MessageKind.POST),
    ("ipm.distlist", MessageKind.DISTRIBUTION_LIST),
    ("ipm.activity", MessageKind.JOURNAL),
    ("ipm.document", MessageKind.DOCUMENT),
)


def classify(class_type: str | None) -> MessageKind:
    """Classify a raw PidTagMessageClass string into a :class:`MessageKind`.

    Matching is a case-insensitive prefix match, e.g. ``IPM.Note.SMIME``
    and ``IPM.Appointment.Recall`` both match their respective base kind.
    A missing or empty class type is reported as :attr:`MessageKind.UNKNOWN`
    rather than raising, since some malformed .msg files lack the property
    entirely.
    """
    if not class_type:
        return MessageKind.UNKNOWN
    normalized = class_type.strip().lower()
    for prefix, kind in _PREFIX_KINDS:
        if normalized.startswith(prefix):
            return kind
    return MessageKind.UNKNOWN


def is_convertible(class_type: str | None) -> bool:
    """Return True if a message of this class should be converted to .eml."""
    return classify(class_type) is MessageKind.EMAIL


def describe(class_type: str | None) -> str:
    """Human-readable description of a message class, for warning messages."""
    kind = classify(class_type)
    label = class_type if class_type else "(none)"
    return f"{label} ({kind.value})"
