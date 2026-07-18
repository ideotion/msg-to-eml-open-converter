from msg2eml.msgclass import MessageKind, classify, describe, is_convertible


def test_classifies_plain_note_as_email() -> None:
    assert classify("IPM.Note") is MessageKind.EMAIL
    assert is_convertible("IPM.Note")


def test_classifies_note_variants_as_email() -> None:
    assert classify("IPM.Note.SMIME") is MessageKind.EMAIL
    assert classify("IPM.Note.SMIME.MultipartSigned") is MessageKind.EMAIL
    assert classify("ipm.note.microsoft.readreceipt") is MessageKind.EMAIL


def test_classifies_calendar_items() -> None:
    assert classify("IPM.Appointment") is MessageKind.CALENDAR
    assert classify("IPM.Schedule.Meeting.Request") is MessageKind.CALENDAR
    assert not is_convertible("IPM.Appointment")


def test_classifies_contact_task_note_post_distlist_journal_document() -> None:
    assert classify("IPM.Contact") is MessageKind.CONTACT
    assert classify("IPM.Task") is MessageKind.TASK
    assert classify("IPM.StickyNote") is MessageKind.NOTE
    assert classify("IPM.Post") is MessageKind.POST
    assert classify("IPM.DistList") is MessageKind.DISTRIBUTION_LIST
    assert classify("IPM.Activity") is MessageKind.JOURNAL
    assert classify("IPM.Document") is MessageKind.DOCUMENT


def test_is_case_insensitive() -> None:
    assert classify("ipm.NOTE") is MessageKind.EMAIL


def test_unknown_or_missing_class_type_does_not_raise() -> None:
    assert classify(None) is MessageKind.UNKNOWN
    assert classify("") is MessageKind.UNKNOWN
    assert classify("IPM.SomethingWeird") is MessageKind.UNKNOWN
    assert not is_convertible(None)


def test_describe_includes_raw_value_and_kind() -> None:
    assert "IPM.Appointment" in describe("IPM.Appointment")
    assert "calendar" in describe("IPM.Appointment")
    assert "(none)" in describe(None)
