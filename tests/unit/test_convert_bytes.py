from __future__ import annotations

from email import policy
from email.parser import BytesParser

import pytest

import msg2eml.convert as convert_module
from msg2eml.convert import convert_bytes
from tests.helpers import OLE2_MAGIC, FakeMsg


def _stub_open_msg(monkeypatch: pytest.MonkeyPatch, msg: FakeMsg | Exception) -> None:
    def fake_open_msg(_source: object) -> FakeMsg:
        if isinstance(msg, Exception):
            raise msg
        return msg

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)


def test_convert_bytes_returns_eml_bytes_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(subject="Hello"))

    result = convert_bytes(OLE2_MAGIC + b"fake msg bytes", "message.msg")

    assert result.status == "converted"
    assert result.filename == "message.msg"
    assert result.error is None
    assert result.eml_bytes is not None
    parsed = BytesParser(policy=policy.default).parsebytes(result.eml_bytes)
    assert not parsed.defects
    assert parsed["Subject"] == "Hello"


def test_convert_bytes_reports_skipped_for_non_email_class(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(classType="IPM.Appointment"))

    result = convert_bytes(OLE2_MAGIC + b"fake msg bytes", "invite.msg")

    assert result.status == "skipped"
    assert result.eml_bytes is None
    assert any("Appointment" in w for w in result.warnings)


def test_convert_bytes_reports_failed_when_open_msg_raises_on_well_formed_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file that passes the OLE2 sniff but is corrupt in a way extract_msg
    itself rejects (e.g. a malformed internal stream) must still fail cleanly."""
    _stub_open_msg(monkeypatch, RuntimeError("corrupt internal MSG structure"))

    result = convert_bytes(OLE2_MAGIC + b"garbage", "bad.msg")

    assert result.status == "failed"
    assert result.eml_bytes is None
    assert "corrupt internal MSG structure" in (result.error or "")


def test_convert_bytes_rejects_non_ole2_input_without_calling_open_msg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Input that doesn't even look like an OLE2 file must fail with a clean
    message and never reach extract_msg.openMsg at all -- regression test for
    extract_msg raising a confusing raw FileNotFoundError for short byte
    strings it mistakes for a file path."""
    called = False

    def fake_open_msg(_source: object) -> FakeMsg:
        nonlocal called
        called = True
        return FakeMsg()

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)

    result = convert_bytes(b"this is not a real msg file\n", "garbage.msg")

    assert result.status == "failed"
    assert result.eml_bytes is None
    assert "OLE2" in (result.error or "")
    assert called is False


def test_convert_bytes_passes_raw_bytes_through_to_open_msg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[object] = []

    def fake_open_msg(source: object) -> FakeMsg:
        received.append(source)
        return FakeMsg()

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)

    payload = OLE2_MAGIC + b"some bytes"
    convert_bytes(payload, "x.msg")

    assert received == [payload]
