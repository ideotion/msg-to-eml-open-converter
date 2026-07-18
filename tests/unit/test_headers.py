from __future__ import annotations

from datetime import datetime, timezone

from msg2eml import headers
from tests.helpers import FakeMsg, FakeRecipient


def test_normalize_mailbox_with_name_and_addr() -> None:
    assert headers.normalize_mailbox("Jane Doe <jane@example.com>") == "Jane Doe <jane@example.com>"


def test_normalize_mailbox_bare_address() -> None:
    assert headers.normalize_mailbox("jane@example.com") == "jane@example.com"


def test_normalize_mailbox_none_or_empty() -> None:
    assert headers.normalize_mailbox(None) is None
    assert headers.normalize_mailbox("   ") is None


def test_grouped_recipients_splits_by_type() -> None:
    msg = FakeMsg(
        recipients=[
            FakeRecipient(email="to@example.com", name="To Person", type=1),
            FakeRecipient(email="cc@example.com", name="Cc Person", type=2),
            FakeRecipient(email="bcc@example.com", name="Bcc Person", type=3),
        ]
    )
    groups = headers.grouped_recipients(msg)
    assert groups["to"] == [("To Person", "to@example.com")]
    assert groups["cc"] == [("Cc Person", "cc@example.com")]
    assert groups["bcc"] == [("Bcc Person", "bcc@example.com")]


def test_grouped_recipients_drops_redundant_name_equal_to_address() -> None:
    msg = FakeMsg(recipients=[FakeRecipient(email="a@example.com", name="a@example.com", type=1)])
    groups = headers.grouped_recipients(msg)
    assert groups["to"] == [("", "a@example.com")]


def test_grouped_recipients_skips_recipients_without_email() -> None:
    msg = FakeMsg(recipients=[FakeRecipient(email="", name="No Address", type=1)])
    groups = headers.grouped_recipients(msg)
    assert groups["to"] == []


def test_grouped_recipients_defaults_unknown_type_to_to() -> None:
    msg = FakeMsg(recipients=[FakeRecipient(email="x@example.com", name="X", type=0)])
    groups = headers.grouped_recipients(msg)
    assert groups["to"] == [("X", "x@example.com")]


def test_address_header_value_joins_multiple_mailboxes() -> None:
    value = headers.address_header_value([("A", "a@example.com"), ("", "b@example.com")])
    assert value == "A <a@example.com>, b@example.com"


def test_resolve_message_id_prefers_native_property() -> None:
    msg = FakeMsg(
        messageId="<native@example.com>", header={"Message-ID": "<from-header@example.com>"}
    )
    message_id, generated = headers.resolve_message_id(msg)
    assert message_id == "<native@example.com>"
    assert generated is False


def test_resolve_message_id_falls_back_to_header() -> None:
    msg = FakeMsg(messageId=None, header={"Message-ID": "<from-header@example.com>"})
    message_id, generated = headers.resolve_message_id(msg)
    assert message_id == "<from-header@example.com>"
    assert generated is False


def test_resolve_message_id_generates_when_absent() -> None:
    msg = FakeMsg(messageId=None, header=None)
    message_id, generated = headers.resolve_message_id(msg)
    assert message_id.startswith("<") and message_id.endswith(">")
    assert generated is True


def test_resolve_in_reply_to_prefers_native_property() -> None:
    msg = FakeMsg(inReplyTo="<parent@example.com>")
    assert headers.resolve_in_reply_to(msg) == "<parent@example.com>"


def test_resolve_in_reply_to_falls_back_to_header() -> None:
    msg = FakeMsg(inReplyTo=None, header={"In-Reply-To": "<parent2@example.com>"})
    assert headers.resolve_in_reply_to(msg) == "<parent2@example.com>"


def test_resolve_in_reply_to_none_when_absent() -> None:
    assert headers.resolve_in_reply_to(FakeMsg(inReplyTo=None, header=None)) is None


def test_resolve_references_reads_raw_header_only() -> None:
    msg = FakeMsg(header={"References": "<r1@example.com> <r2@example.com>"})
    assert headers.resolve_references(msg) == "<r1@example.com> <r2@example.com>"
    assert headers.resolve_references(FakeMsg(header=None)) is None


def test_resolve_date_requires_real_datetime() -> None:
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert headers.resolve_date(FakeMsg(date=dt)) == dt
    assert headers.resolve_date(FakeMsg(date=None)) is None
    assert headers.resolve_date(FakeMsg(date="not-a-date")) is None  # type: ignore[arg-type]
