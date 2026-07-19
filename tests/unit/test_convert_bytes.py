from __future__ import annotations

from email import policy
from email.parser import BytesParser

import pytest

import msg2eml.convert as convert_module
from msg2eml.convert import convert_bytes
from tests.helpers import FakeMsg


def _stub_open_msg(monkeypatch: pytest.MonkeyPatch, msg: FakeMsg | Exception) -> None:
    def fake_open_msg(_source: object) -> FakeMsg:
        if isinstance(msg, Exception):
            raise msg
        return msg

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)


def test_convert_bytes_returns_eml_bytes_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(subject="Hello"))

    result = convert_bytes(b"fake msg bytes", "message.msg")

    assert result.status == "converted"
    assert result.filename == "message.msg"
    assert result.error is None
    assert result.eml_bytes is not None
    parsed = BytesParser(policy=policy.default).parsebytes(result.eml_bytes)
    assert not parsed.defects
    assert parsed["Subject"] == "Hello"


def test_convert_bytes_reports_skipped_for_non_email_class(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(classType="IPM.Appointment"))

    result = convert_bytes(b"fake msg bytes", "invite.msg")

    assert result.status == "skipped"
    assert result.eml_bytes is None
    assert any("Appointment" in w for w in result.warnings)


def test_convert_bytes_reports_failed_on_corrupt_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_open_msg(monkeypatch, RuntimeError("not a valid OLE2 file"))

    result = convert_bytes(b"garbage", "bad.msg")

    assert result.status == "failed"
    assert result.eml_bytes is None
    assert "not a valid OLE2 file" in (result.error or "")


def test_convert_bytes_passes_raw_bytes_through_to_open_msg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[object] = []

    def fake_open_msg(source: object) -> FakeMsg:
        received.append(source)
        return FakeMsg()

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)

    convert_bytes(b"\xd0\xcf\x11\xe0some bytes", "x.msg")

    assert received == [b"\xd0\xcf\x11\xe0some bytes"]
