from __future__ import annotations

from msg2eml import attachments
from tests.helpers import FakeAttachment


def test_is_nested_message_true_for_msg_and_signed_embedded() -> None:
    assert attachments.is_nested_message(FakeAttachment(data=object(), type=1))
    assert attachments.is_nested_message(FakeAttachment(data=object(), type=6))


def test_is_nested_message_false_for_data_and_unknown() -> None:
    assert not attachments.is_nested_message(FakeAttachment(data=b"x", type=0))
    assert not attachments.is_nested_message(FakeAttachment(data=b"x", type=None))


def test_sanitize_filename_strips_unsafe_characters() -> None:
    assert attachments.sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_sanitize_filename_strips_control_characters_and_newlines() -> None:
    assert "\n" not in attachments.sanitize_filename("evil\r\nX-Injected: 1")


def test_sanitize_filename_falls_back_to_default_when_empty() -> None:
    assert attachments.sanitize_filename("   ...   ") == "attachment"
    assert attachments.sanitize_filename("", default="message") == "message"


def test_attachment_filename_prefers_name_attribute() -> None:
    att = FakeAttachment(data=b"x", name="report.pdf")
    assert attachments.attachment_filename(att, 0) == "report.pdf"


def test_attachment_filename_falls_back_through_chain() -> None:
    att = FakeAttachment(data=b"x", name="", longFilename="", shortFilename="short.txt")
    assert attachments.attachment_filename(att, 0) == "short.txt"


def test_attachment_filename_falls_back_to_generated_name() -> None:
    class NoFilenameAttachment:
        name = ""
        longFilename = ""
        shortFilename = ""
        getFilename = None  # not callable, unlike FakeAttachment's method

    assert attachments.attachment_filename(NoFilenameAttachment(), 3) == "attachment_3"


def test_guess_mime_type_uses_declared_mimetype() -> None:
    att = FakeAttachment(data=b"x", mimetype="image/png")
    assert attachments.guess_mime_type(att, "whatever") == ("image", "png")


def test_guess_mime_type_guesses_from_filename_when_absent() -> None:
    att = FakeAttachment(data=b"x", mimetype=None)
    assert attachments.guess_mime_type(att, "report.pdf") == ("application", "pdf")


def test_guess_mime_type_defaults_to_octet_stream() -> None:
    att = FakeAttachment(data=b"x", mimetype=None)
    assert attachments.guess_mime_type(att, "unknown.xyz123") == ("application", "octet-stream")


def test_guess_mime_type_rejects_invalid_tokens() -> None:
    att = FakeAttachment(data=b"x", mimetype="text/plain\r\nX-Evil: 1")
    assert attachments.guess_mime_type(att, "a.txt") == ("application", "octet-stream")


def test_clean_content_id_strips_brackets_and_whitespace() -> None:
    assert attachments.clean_content_id("<abc123@example.com>") == "abc123@example.com"
    assert attachments.clean_content_id("  abc123@example.com  ") == "abc123@example.com"


def test_clean_content_id_none_for_empty_or_multiline() -> None:
    assert attachments.clean_content_id(None) is None
    assert attachments.clean_content_id("") is None
    assert attachments.clean_content_id("abc\r\nX-Evil: 1") is None


def test_is_inline_referenced_true_when_cid_appears_in_html() -> None:
    assert attachments.is_inline_referenced("img1", '<img src="cid:img1">')


def test_is_inline_referenced_false_without_html_or_cid() -> None:
    assert not attachments.is_inline_referenced(None, '<img src="cid:img1">')
    assert not attachments.is_inline_referenced("img1", None)
    assert not attachments.is_inline_referenced("img2", '<img src="cid:img1">')
