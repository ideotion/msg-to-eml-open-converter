from __future__ import annotations

from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest

from msg2eml.convert import build_eml
from msg2eml.exceptions import ConversionError
from tests.helpers import FakeAttachment, FakeMsg, FakeRecipient

UTC_DATE = datetime(2024, 5, 1, 10, 30, tzinfo=timezone.utc)


def _roundtrip(eml: EmailMessage) -> EmailMessage:
    parsed = BytesParser(policy=policy.default).parsebytes(eml.as_bytes())
    assert not parsed.defects
    return parsed


def test_plain_and_html_body_produces_multipart_alternative() -> None:
    msg = FakeMsg(body="Plain body", htmlBody="<p>HTML body</p>")
    eml = build_eml(msg)
    assert eml.get_content_type() == "multipart/alternative"
    parts = list(eml.iter_parts())
    assert [p.get_content_type() for p in parts] == ["text/plain", "text/html"]
    assert parts[0].get_content().strip() == "Plain body"
    assert "HTML body" in parts[1].get_content()


def test_html_only_body_is_single_html_part() -> None:
    msg = FakeMsg(body=None, htmlBody="<p>Only HTML</p>")
    eml = build_eml(msg)
    assert eml.get_content_type() == "text/html"


def test_plain_only_body_is_single_plain_part() -> None:
    msg = FakeMsg(body="Only plain", htmlBody=None)
    eml = build_eml(msg)
    assert eml.get_content_type() == "text/plain"


def test_no_body_at_all_produces_empty_plain_part_with_warning() -> None:
    msg = FakeMsg(body=None, htmlBody=None, rtfBody=None)
    warnings: list[str] = []
    eml = build_eml(msg, warnings=warnings)
    assert eml.get_content_type() == "text/plain"
    assert any("no body content" in w for w in warnings)


HTML_ENCAPSULATED_RTF = (
    rb"{\rtf1\ansi\ansicpg1252\fromhtml1 \deff0{\fonttbl{\f0\fswiss Helvetica;}}"
    rb"{\*\htmltag64 <html>}{\*\htmltag64 <body>}De-encapsulated"
    rb"{\*\htmltag64 <\/body>}{\*\htmltag64 <\/html>}\par}"
)

NOT_REALLY_RTF = b"not rtf at all, de-encapsulation will fail"


def test_rtf_only_body_deencapsulates_to_html() -> None:
    msg = FakeMsg(body=None, htmlBody=None, rtfBody=HTML_ENCAPSULATED_RTF)
    eml = build_eml(msg)
    assert eml.get_content_type() == "text/html"
    assert "De-encapsulated" in eml.get_content()


def test_rtf_deencapsulation_failure_falls_back_to_stripped_text() -> None:
    msg = FakeMsg(body=None, htmlBody=None, rtfBody=NOT_REALLY_RTF)
    warnings: list[str] = []
    eml = build_eml(msg, warnings=warnings)
    assert eml.get_content_type() == "text/plain"
    assert any("could not be de-encapsulated" in w for w in warnings)


def test_headers_are_set_and_survive_roundtrip() -> None:
    msg = FakeMsg(
        subject="Hello",
        sender="Sender Name <sender@example.com>",
        date=UTC_DATE,
        messageId="<msg1@example.com>",
        inReplyTo="<parent@example.com>",
        header={"References": "<r1@example.com>"},
        recipients=[
            FakeRecipient(email="to@example.com", name="To Person", type=1),
            FakeRecipient(email="cc@example.com", name="Cc Person", type=2),
        ],
    )
    eml = build_eml(msg)
    parsed = _roundtrip(eml)
    assert parsed["Subject"] == "Hello"
    assert parsed["From"] == "Sender Name <sender@example.com>"
    assert parsed["To"] == "To Person <to@example.com>"
    assert parsed["Cc"] == "Cc Person <cc@example.com>"
    assert parsed["Message-ID"] == "<msg1@example.com>"
    assert parsed["In-Reply-To"] == "<parent@example.com>"
    assert parsed["References"] == "<r1@example.com>"
    assert parsed["Date"] is not None


def test_missing_sender_and_date_are_omitted_with_warnings() -> None:
    msg = FakeMsg(sender=None, date=None, messageId=None, header=None)
    warnings: list[str] = []
    eml = build_eml(msg, warnings=warnings)
    parsed = _roundtrip(eml)
    assert parsed["From"] is None
    assert parsed["Date"] is None
    assert parsed["Message-ID"] is not None  # synthetic id still generated
    assert any("no sender" in w for w in warnings)
    assert any("no date" in w for w in warnings)
    assert any("synthetic" in w for w in warnings)


def test_non_ascii_headers_are_rfc2047_encoded_and_roundtrip_cleanly() -> None:
    msg = FakeMsg(
        subject="Réunion : café à Nîmes",
        sender="François Müller <francois@example.com>",
        recipients=[FakeRecipient(email="elodie@example.com", name="Élodie Petit", type=1)],
    )
    eml = build_eml(msg)
    raw = eml.as_bytes()
    assert b"R\xc3\xa9union" not in raw  # header bytes must be RFC 2047 encoded, not raw UTF-8
    parsed = _roundtrip(eml)
    assert parsed["Subject"] == "Réunion : café à Nîmes"
    assert parsed["From"] == "François Müller <francois@example.com>"
    assert parsed["To"] == "Élodie Petit <elodie@example.com>"


def test_regular_attachment_is_base64_with_preserved_filename_and_mimetype() -> None:
    msg = FakeMsg(
        attachments=[
            FakeAttachment(data=b"\x89PNG-fake", name="rapport.pdf", mimetype="application/pdf")
        ]
    )
    eml = build_eml(msg)
    assert eml.get_content_type() == "multipart/mixed"
    parts = list(eml.iter_parts())
    attachment_part = parts[1]
    assert attachment_part.get_content_type() == "application/pdf"
    assert attachment_part.get_filename() == "rapport.pdf"
    assert attachment_part["Content-Transfer-Encoding"] == "base64"
    assert attachment_part.get_content() == b"\x89PNG-fake"


def test_attachment_with_non_ascii_filename_survives_roundtrip() -> None:
    msg = FakeMsg(
        attachments=[FakeAttachment(data=b"data", name="logo été.png", mimetype="image/png")]
    )
    eml = build_eml(msg)
    parsed = _roundtrip(eml)
    attachment_part = list(parsed.iter_parts())[1]
    assert attachment_part.get_filename() == "logo été.png"


def test_inline_image_referenced_by_cid_becomes_multipart_related() -> None:
    msg = FakeMsg(
        body=None,
        htmlBody='<html><body><img src="cid:img1@example.com"></body></html>',
        attachments=[
            FakeAttachment(
                data=b"\x89PNG", name="inline.png", mimetype="image/png", cid="img1@example.com"
            )
        ],
    )
    eml = build_eml(msg)
    assert eml.get_content_type() == "multipart/related"
    parsed = _roundtrip(eml)
    assert parsed.get_content_type() == "multipart/related"
    parts = list(parsed.iter_parts())
    assert parts[0].get_content_type() == "text/html"
    assert parts[1].get_content_type() == "image/png"
    assert parts[1]["Content-ID"] == "<img1@example.com>"
    assert "cid:img1@example.com" in parts[0].get_content()


def test_inline_image_with_plain_and_html_alternative() -> None:
    msg = FakeMsg(
        body="Plain fallback",
        htmlBody='<html><body><img src="cid:img1@example.com"></body></html>',
        attachments=[
            FakeAttachment(data=b"\x89PNG", name="inline.png", mimetype="image/png", cid="img1")
        ],
    )
    eml = build_eml(msg)
    parsed = _roundtrip(eml)
    assert parsed.get_content_type() == "multipart/alternative"
    plain_part, related_part = list(parsed.iter_parts())
    assert plain_part.get_content_type() == "text/plain"
    assert related_part.get_content_type() == "multipart/related"


def test_attachment_not_referenced_by_cid_is_regular_attachment_even_with_cid_set() -> None:
    msg = FakeMsg(
        body=None,
        htmlBody="<html><body>No image reference here</body></html>",
        attachments=[
            FakeAttachment(
                data=b"\x89PNG", name="unused.png", mimetype="image/png", cid="unused-cid"
            )
        ],
    )
    eml = build_eml(msg)
    assert eml.get_content_type() == "multipart/mixed"


def test_nested_msg_attachment_becomes_message_rfc822() -> None:
    inner = FakeMsg(subject="Inner message", sender="inner@example.com", body="Inner body")
    outer = FakeMsg(
        subject="Outer message",
        body="See attached",
        attachments=[FakeAttachment(data=inner, type=1)],  # AttachmentType.MSG
    )
    eml = build_eml(outer)
    assert eml.get_content_type() == "multipart/mixed"
    parts = list(eml.iter_parts())
    nested_part = parts[1]
    assert nested_part.get_content_type() == "message/rfc822"
    assert nested_part["Content-Transfer-Encoding"] != "base64"
    inner_msg = nested_part.get_content()
    assert inner_msg["Subject"] == "Inner message"
    assert inner_msg["From"] == "inner@example.com"


def test_nested_msg_conversion_failure_is_recorded_as_warning_not_raised() -> None:
    class ExplodingInner:
        subject = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

    outer = FakeMsg(
        subject="Outer",
        body="See attached",
        attachments=[FakeAttachment(data=ExplodingInner(), type=1)],
    )
    warnings: list[str] = []
    eml = build_eml(outer, warnings=warnings)
    assert any("could not be converted" in w for w in warnings)
    # the outer message itself must still be produced, with just the body (no nested part)
    assert eml.get_content_type() == "text/plain"


def test_excessive_nesting_depth_raises_conversion_error() -> None:
    msg = FakeMsg(subject="deep")
    with pytest.raises(ConversionError):
        build_eml(msg, _depth=11)


def test_broken_attachment_is_skipped_with_warning_not_fatal() -> None:
    class BrokenAttachment:
        type = 0
        data = "not bytes"  # deliberately wrong type
        name = "broken"

    msg = FakeMsg(attachments=[BrokenAttachment()])
    warnings: list[str] = []
    eml = build_eml(msg, warnings=warnings)
    assert eml.get_content_type() != "multipart/mixed"
    assert any("no readable data" in w for w in warnings)


def test_recipients_fallback_to_raw_strings_when_no_recipient_table() -> None:
    msg = FakeMsg(to="fallback@example.com", cc=None, bcc=None, recipients=[])
    eml = build_eml(msg)
    parsed = _roundtrip(eml)
    assert "fallback@example.com" in str(parsed["To"])
