"""End-to-end structural round-trip tests.

Every .eml msg2eml produces must re-parse cleanly with the stdlib email
package and preserve the full MIME structure: headers, multipart nesting,
inline image Content-IDs, attachment filenames/types, and nested
message/rfc822 parts.
"""

from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

from msg2eml.convert import build_eml
from tests.helpers import FakeAttachment, FakeMsg, FakeRecipient

HTML_BODY = (
    "<html><body><p>Bonjour à tous,</p>"
    '<img src="cid:logo@example.com"><p>À bientôt.</p></body></html>'
)


def _build_kitchen_sink_msg() -> FakeMsg:
    inner = FakeMsg(
        subject="Message original",
        sender="original@example.com",
        body="Corps du message original.",
        recipients=[FakeRecipient(email="dest@example.com", name="Destinataire", type=1)],
    )
    return FakeMsg(
        subject="Compte-rendu de réunion",
        sender="Organisateur <organisateur@example.com>",
        body="Version texte du compte-rendu.",
        htmlBody=HTML_BODY,
        recipients=[
            FakeRecipient(email="alice@example.com", name="Alice Dupont", type=1),
            FakeRecipient(email="bob@example.com", name="Bob Martin", type=1),
            FakeRecipient(email="carla@example.com", name="Carla Échard", type=2),
        ],
        header={"References": "<thread-root@example.com>"},
        inReplyTo="<thread-root@example.com>",
        attachments=[
            FakeAttachment(
                data=b"\x89PNGfakebytes",
                name="logo.png",
                mimetype="image/png",
                cid="logo@example.com",
            ),
            FakeAttachment(
                data=b"%PDF-1.4 fake report contents",
                name="rapport financier.pdf",
                mimetype="application/pdf",
            ),
            FakeAttachment(data=inner, type=1),
        ],
    )


def _write_and_reparse(eml: EmailMessage, path: Path) -> EmailMessage:
    path.write_bytes(eml.as_bytes())
    return BytesParser(policy=policy.default).parsebytes(path.read_bytes())


def test_kitchen_sink_message_roundtrips_with_full_structure(tmp_path: Path) -> None:
    msg = _build_kitchen_sink_msg()
    eml = build_eml(msg)
    parsed = _write_and_reparse(eml, tmp_path / "output.eml")

    assert not parsed.defects
    assert parsed["Subject"] == "Compte-rendu de réunion"
    assert parsed["From"] == "Organisateur <organisateur@example.com>"
    assert parsed["To"] == "Alice Dupont <alice@example.com>, Bob Martin <bob@example.com>"
    assert parsed["Cc"] == "Carla Échard <carla@example.com>"
    assert parsed["In-Reply-To"] == "<thread-root@example.com>"
    assert parsed["References"] == "<thread-root@example.com>"

    assert parsed.get_content_type() == "multipart/mixed"
    top_parts = list(parsed.iter_parts())
    content_types = [p.get_content_type() for p in top_parts]
    assert content_types == [
        "multipart/alternative",
        "application/pdf",
        "message/rfc822",
    ]

    alternative_parts = list(top_parts[0].iter_parts())
    assert [p.get_content_type() for p in alternative_parts] == [
        "text/plain",
        "multipart/related",
    ]
    assert alternative_parts[0].get_content().strip() == "Version texte du compte-rendu."

    related_parts = list(alternative_parts[1].iter_parts())
    assert [p.get_content_type() for p in related_parts] == ["text/html", "image/png"]
    assert "cid:logo@example.com" in related_parts[0].get_content()
    assert related_parts[1]["Content-ID"] == "<logo@example.com>"
    assert related_parts[1].get_content() == b"\x89PNGfakebytes"

    pdf_part = top_parts[1]
    assert pdf_part.get_filename() == "rapport financier.pdf"
    assert pdf_part["Content-Transfer-Encoding"] == "base64"
    assert pdf_part.get_content() == b"%PDF-1.4 fake report contents"

    nested_part = top_parts[2]
    nested_msg = nested_part.get_content()
    assert nested_msg["Subject"] == "Message original"
    assert nested_msg["From"] == "original@example.com"
    assert nested_msg["To"] == "Destinataire <dest@example.com>"
    assert nested_msg.get_content().strip() == "Corps du message original."


def test_minimal_message_roundtrips(tmp_path: Path) -> None:
    msg = FakeMsg(subject="Simple", body="Just text.")
    eml = build_eml(msg)
    parsed = _write_and_reparse(eml, tmp_path / "simple.eml")
    assert not parsed.defects
    assert parsed["Subject"] == "Simple"
    assert parsed.get_content_type() == "text/plain"
    assert parsed.get_content().strip() == "Just text."
