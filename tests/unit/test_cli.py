from __future__ import annotations

import json
from pathlib import Path

import pytest

import msg2eml.convert as convert_module
from msg2eml.cli import main
from tests.helpers import OLE2_MAGIC, FakeMsg


def _stub_open_msg(monkeypatch: pytest.MonkeyPatch, msg: FakeMsg | Exception) -> None:
    def fake_open_msg(_path: str) -> FakeMsg:
        if isinstance(msg, Exception):
            raise msg
        return msg

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)


def _touch(path: Path) -> None:
    """Write a placeholder file with a valid OLE2 signature.

    Content doesn't otherwise matter here since extract_msg.openMsg is
    monkeypatched in every test that uses this -- but convert._open_and_build
    sniffs the OLE2 magic before ever calling it, so the placeholder must
    have one to reach the mock at all.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(OLE2_MAGIC)


def test_main_converts_single_file_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "input.msg")
    _stub_open_msg(monkeypatch, FakeMsg())

    exit_code = main(["input.msg"])

    assert exit_code == 0
    assert (tmp_path / "input.eml").exists()


def test_main_returns_one_on_conversion_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "bad.msg")
    _stub_open_msg(monkeypatch, RuntimeError("corrupt OLE2 structure"))

    exit_code = main(["bad.msg"])

    assert exit_code == 1
    assert not (tmp_path / "bad.eml").exists()


def test_main_skips_non_email_class_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "invite.msg")
    _stub_open_msg(monkeypatch, FakeMsg(classType="IPM.Appointment"))

    exit_code = main(["invite.msg"])

    assert exit_code == 0
    assert not (tmp_path / "invite.eml").exists()
    assert "Skipped" in capsys.readouterr().err


def test_main_refuses_overwrite_without_force_then_succeeds_with_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "input.msg")
    (tmp_path / "input.eml").write_bytes(b"pre-existing")
    _stub_open_msg(monkeypatch, FakeMsg())

    assert main(["input.msg"]) == 1
    assert (tmp_path / "input.eml").read_bytes() == b"pre-existing"

    assert main(["input.msg", "--force"]) == 0
    assert (tmp_path / "input.eml").read_bytes() != b"pre-existing"


def test_main_fatal_exit_code_for_missing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["does-not-exist.msg"]) == 2


def test_main_fatal_exit_code_for_non_msg_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "not-a-msg.txt")
    assert main(["not-a-msg.txt"]) == 2


def test_main_writes_json_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "input.msg")
    _stub_open_msg(monkeypatch, FakeMsg())
    report_path = tmp_path / "report.json"

    main(["input.msg", "--json-report", str(report_path)])

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["status"] == "converted"
    assert data[0]["input_path"] == "input.msg"


def test_main_batch_recursive_mirrors_structure_with_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "top.msg")
    _touch(tmp_path / "sub" / "deep" / "nested.msg")
    _stub_open_msg(monkeypatch, FakeMsg())

    exit_code = main([".", "-r", "-o", "out"])

    assert exit_code == 0
    assert (tmp_path / "out" / "top.eml").exists()
    assert (tmp_path / "out" / "sub" / "deep" / "nested.eml").exists()


def test_main_batch_non_recursive_ignores_subfolders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "top.msg")
    _touch(tmp_path / "sub" / "nested.msg")
    _stub_open_msg(monkeypatch, FakeMsg())

    exit_code = main(["."])

    assert exit_code == 0
    assert (tmp_path / "top.eml").exists()
    assert not (tmp_path / "sub" / "nested.eml").exists()


def test_main_quiet_suppresses_info_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "input.msg")
    _stub_open_msg(monkeypatch, FakeMsg())

    exit_code = main(["input.msg", "--quiet"])

    assert exit_code == 0
    assert capsys.readouterr().err == ""


def test_main_verbose_shows_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "input.msg")
    _stub_open_msg(monkeypatch, FakeMsg(sender=None))

    main(["input.msg", "--verbose"])

    assert "no sender" in capsys.readouterr().err


def test_main_batch_continues_after_one_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _touch(tmp_path / "a.msg")
    _touch(tmp_path / "b.msg")

    calls = {"count": 0}

    def flaky_open_msg(_path: str) -> FakeMsg:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return FakeMsg()

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", flaky_open_msg)

    exit_code = main(["."])

    assert exit_code == 1  # some failures occurred
    assert calls["count"] == 2  # both files were still attempted


def test_main_batch_survives_symlink_pointing_outside_input_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file whose output path can't be resolved (e.g. relative_to raising for
    a symlink escaping the walked root) must be reported as failed, not crash
    the whole batch and take down files that would have converted fine."""
    monkeypatch.chdir(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    real_file = outside_dir / "real.msg"
    _touch(real_file)
    try:
        (input_dir / "linked.msg").symlink_to(real_file)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported on this platform/filesystem")
    _touch(input_dir / "normal.msg")
    _stub_open_msg(monkeypatch, FakeMsg())

    exit_code = main([str(input_dir), "-r", "-o", "out"])

    assert exit_code == 1
    assert (tmp_path / "out" / "normal.eml").exists()
