from __future__ import annotations

from pathlib import Path

from msg2eml.walker import discover_msg_files, resolve_batch_output_path, resolve_single_output_path


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_discover_msg_files_non_recursive_ignores_subfolders(tmp_path: Path) -> None:
    _touch(tmp_path / "a.msg")
    _touch(tmp_path / "sub" / "b.msg")
    found = discover_msg_files(tmp_path, recursive=False)
    assert found == [tmp_path / "a.msg"]


def test_discover_msg_files_recursive_finds_nested(tmp_path: Path) -> None:
    _touch(tmp_path / "a.msg")
    _touch(tmp_path / "sub" / "deep" / "b.msg")
    found = discover_msg_files(tmp_path, recursive=True)
    assert found == sorted([tmp_path / "a.msg", tmp_path / "sub" / "deep" / "b.msg"])


def test_discover_msg_files_ignores_non_msg_and_is_case_insensitive(tmp_path: Path) -> None:
    _touch(tmp_path / "a.msg")
    _touch(tmp_path / "b.MSG")
    _touch(tmp_path / "c.txt")
    found = discover_msg_files(tmp_path, recursive=False)
    assert found == sorted([tmp_path / "a.msg", tmp_path / "b.MSG"])


def test_resolve_single_output_path_defaults_next_to_source(tmp_path: Path) -> None:
    src = tmp_path / "message.msg"
    assert resolve_single_output_path(src, output=None) == tmp_path / "message.eml"


def test_resolve_single_output_path_with_explicit_file(tmp_path: Path) -> None:
    src = tmp_path / "message.msg"
    target = tmp_path / "custom.eml"
    assert resolve_single_output_path(src, output=str(target)) == target


def test_resolve_single_output_path_with_existing_directory(tmp_path: Path) -> None:
    src = tmp_path / "message.msg"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    assert resolve_single_output_path(src, output=str(out_dir)) == out_dir / "message.eml"


def test_resolve_single_output_path_with_trailing_slash_treated_as_directory(
    tmp_path: Path,
) -> None:
    src = tmp_path / "message.msg"
    raw_output = f"{tmp_path / 'does_not_exist_yet'}/"
    result = resolve_single_output_path(src, output=raw_output)
    assert result == tmp_path / "does_not_exist_yet" / "message.eml"


def test_resolve_batch_output_path_defaults_next_to_source(tmp_path: Path) -> None:
    src = tmp_path / "sub" / "message.msg"
    assert resolve_batch_output_path(src, input_root=tmp_path, output=None) == src.with_suffix(
        ".eml"
    )


def test_resolve_batch_output_path_mirrors_relative_structure(tmp_path: Path) -> None:
    src = tmp_path / "sub" / "deep" / "message.msg"
    out_root = tmp_path / "output"
    result = resolve_batch_output_path(src, input_root=tmp_path, output=out_root)
    assert result == out_root / "sub" / "deep" / "message.eml"


# New tests for preserve_structure parameter

def test_resolve_batch_output_path_flat_structure(tmp_path: Path) -> None:
    src = tmp_path / "sub" / "deep" / "message.msg"
    out_root = tmp_path / "output"
    result = resolve_batch_output_path(
        src, input_root=tmp_path, output=out_root, preserve_structure=False
    )
    assert result == out_root / "message.eml"


def test_resolve_batch_output_path_preserve_structure_default(tmp_path: Path) -> None:
    # Default should be preserve_structure=True
    src = tmp_path / "sub" / "deep" / "message.msg"
    out_root = tmp_path / "output"
    result = resolve_batch_output_path(src, input_root=tmp_path, output=out_root)
    assert result == out_root / "sub" / "deep" / "message.eml"


def test_resolve_single_output_path_preserve_structure_with_directory(
    tmp_path: Path,
) -> None:
    src = tmp_path / "message.msg"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # For single file, preserve_structure doesn't affect the result much
    result = resolve_single_output_path(src, output=str(out_dir), preserve_structure=True)
    assert result == out_dir / "message.eml"


def test_resolve_single_output_path_flat_with_directory(tmp_path: Path) -> None:
    src = tmp_path / "message.msg"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = resolve_single_output_path(src, output=str(out_dir), preserve_structure=False)
    assert result == out_dir / "message.eml"
