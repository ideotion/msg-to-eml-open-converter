from __future__ import annotations

from typing import Any

import pytest

from msg2eml import rtf

HTML_ENCAPSULATED_RTF = (
    rb"{\rtf1\ansi\ansicpg1252\fromhtml1 \deff0{\fonttbl{\f0\fswiss Helvetica;}}"
    rb"{\*\generator Msg2Eml Test;}\viewkind4\uc1\pard\f0\fs20"
    rb"{\*\htmltag64 <html>}{\*\htmltag64 <body>}"
    rb"Bonjour \'e9 <b>monde<\/b>"
    rb"{\*\htmltag64 <\/body>}{\*\htmltag64 <\/html>}\par}"
)

TEXT_ENCAPSULATED_RTF = (
    rb"{\rtf1\ansi\ansicpg1252\fromtext \deff0{\fonttbl{\f0\fswiss Helvetica;}}"
    rb"\viewkind4\uc1\pard\f0\fs20 Hello plain world\par}"
)

NOT_RTF_AT_ALL = b"this is not rtf data at all"


def test_rtf_to_content_extracts_html() -> None:
    html, text = rtf.rtf_to_content(HTML_ENCAPSULATED_RTF)
    assert html is not None
    assert text is None
    assert "<html>" in html
    assert "monde" in html


def test_rtf_to_content_extracts_plain_text() -> None:
    html, text = rtf.rtf_to_content(TEXT_ENCAPSULATED_RTF)
    assert html is None
    assert text is not None
    assert "Hello plain world" in text


def test_rtf_to_content_returns_none_none_on_garbage_input() -> None:
    html, text = rtf.rtf_to_content(NOT_RTF_AT_ALL)
    assert html is None
    assert text is None


def test_rtf_to_content_handles_generic_exception_from_rtfde(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExplodingDeEncapsulator:
        def __init__(self, _raw_rtf: bytes) -> None:
            pass

        def deencapsulate(self) -> None:
            raise ValueError("simulated internal RTFDE failure")

    monkeypatch.setattr(rtf, "DeEncapsulator", ExplodingDeEncapsulator)
    html, text = rtf.rtf_to_content(HTML_ENCAPSULATED_RTF)
    assert html is None
    assert text is None


def test_rtf_to_content_handles_unknown_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    class WeirdDeEncapsulator:
        def __init__(self, _raw_rtf: bytes) -> None:
            self.content_type = "something-else"
            self.html = "unused"
            self.text = "unused"

        def deencapsulate(self) -> None:
            pass

    monkeypatch.setattr(rtf, "DeEncapsulator", WeirdDeEncapsulator)
    html, text = rtf.rtf_to_content(HTML_ENCAPSULATED_RTF)
    assert html is None
    assert text is None


def test_decompress_if_needed_falls_back_to_original_on_already_plain_rtf() -> None:
    result = rtf._decompress_if_needed(HTML_ENCAPSULATED_RTF)
    assert result == HTML_ENCAPSULATED_RTF


def test_decompress_if_needed_handles_compressed_rtf_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising_decompress(_data: Any) -> bytes:
        raise Exception("Unknown type of RTF compression!")  # noqa: TRY002

    monkeypatch.setattr(rtf.compressed_rtf, "decompress", raising_decompress)
    result = rtf._decompress_if_needed(HTML_ENCAPSULATED_RTF)
    assert result == HTML_ENCAPSULATED_RTF


def test_strip_rtf_controls_extracts_readable_words() -> None:
    text = rtf.strip_rtf_controls(HTML_ENCAPSULATED_RTF)
    assert "monde" in text
    assert "\\" not in text
    assert "{" not in text and "}" not in text
