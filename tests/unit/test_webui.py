from __future__ import annotations

from pathlib import Path

import pytest

flask_installed = pytest.importorskip("flask", reason="flask (the 'ui' extra) is not installed")

import msg2eml.convert as convert_module  # noqa: E402
from msg2eml.webui.app import create_app  # noqa: E402
from tests.helpers import OLE2_MAGIC, FakeCalendarItem, FakeContact, FakeMsg  # noqa: E402


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _stub_open_msg(monkeypatch: pytest.MonkeyPatch, msg: object) -> None:
    def fake_open_msg(_source: object) -> object:
        if isinstance(msg, Exception):
            raise msg
        return msg

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)


def _write_msg(path: Path, extra: bytes = b"rest of fake msg") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(OLE2_MAGIC + extra)


def test_index_serves_the_page(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"msg2eml" in response.data


def test_static_assets_are_served(client) -> None:
    css = client.get("/static/style.css")
    js = client.get("/static/app.js")
    assert css.status_code == 200
    assert js.status_code == 200
    assert b"prefers-color-scheme" in css.data
    assert b"/api/convert" in js.data


def test_browse_lists_subfolders_and_direct_msg_files(client, tmp_path: Path) -> None:
    (tmp_path / "Archive").mkdir()
    (tmp_path / "Q1").mkdir()
    (tmp_path / ".hidden").mkdir()
    _write_msg(tmp_path / "standalone.msg")
    (tmp_path / "readme.txt").write_text("not a msg file")

    response = client.get(f"/api/browse?path={tmp_path}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["path"] == str(tmp_path)
    assert data["parent"] == str(tmp_path.parent)
    assert data["folders"] == ["Archive", "Q1"]
    assert data["msgFiles"] == ["standalone.msg"]


def test_browse_defaults_to_home_when_no_path_given(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    response = client.get("/api/browse")

    assert response.status_code == 200
    assert response.get_json()["path"] == str(tmp_path)


def test_browse_reports_no_parent_at_filesystem_root(client) -> None:
    response = client.get("/api/browse?path=/")
    assert response.status_code == 200
    assert response.get_json()["parent"] is None


def test_browse_returns_404_for_a_missing_path(client, tmp_path: Path) -> None:
    response = client.get(f"/api/browse?path={tmp_path / 'does-not-exist'}")
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"].lower()


def test_browse_returns_400_for_a_file_path(client, tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-folder.msg"
    _write_msg(file_path)

    response = client.get(f"/api/browse?path={file_path}")

    assert response.status_code == 400
    assert "not a folder" in response.get_json()["error"].lower()


def test_scan_finds_nested_msg_files_grouped_by_folder(client, tmp_path: Path) -> None:
    _write_msg(tmp_path / "direct.msg")
    (tmp_path / "sub").mkdir()
    _write_msg(tmp_path / "sub" / "a.msg")
    (tmp_path / "sub" / "deep").mkdir()
    _write_msg(tmp_path / "sub" / "deep" / "b.msg")
    (tmp_path / "sub" / "notes.txt").write_text("ignored")

    response = client.post("/api/scan", json={"path": str(tmp_path)})

    assert response.status_code == 200
    data = response.get_json()
    assert data["root"] == str(tmp_path)
    by_name = {f["name"]: f["relativeFolder"] for f in data["files"]}
    assert by_name == {
        "direct.msg": "",
        "a.msg": "sub",
        "b.msg": "sub/deep",
    }


def test_scan_returns_empty_list_when_nothing_found(client, tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()

    response = client.post("/api/scan", json={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.get_json()["files"] == []


def test_scan_returns_404_for_a_missing_path(client, tmp_path: Path) -> None:
    response = client.post("/api/scan", json={"path": str(tmp_path / "nope")})
    assert response.status_code == 404


def test_scan_finds_msg_files_at_arbitrary_depth(client, tmp_path: Path) -> None:
    """Not just one level of subfolders: the scan must keep recursing into
    subfolders of subfolders of subfolders, however deep the tree goes."""
    deep_dir = tmp_path / "a" / "b" / "c" / "d" / "e"
    deep_dir.mkdir(parents=True)
    _write_msg(deep_dir / "deep.msg")

    response = client.post("/api/scan", json={"path": str(tmp_path)})

    assert response.status_code == 200
    files = response.get_json()["files"]
    assert [f["name"] for f in files] == ["deep.msg"]
    assert files[0]["relativeFolder"] == "a/b/c/d/e"


def test_convert_writes_output_next_to_source(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(subject="Hello from the web UI"))
    msg_path = tmp_path / "message.msg"
    _write_msg(msg_path)

    response = client.post("/api/convert", json={"paths": [str(msg_path)]})

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "converted"
    assert result["outputFormat"] == "eml"
    output_path = tmp_path / "message.eml"
    assert result["outputPath"] == str(output_path)
    assert output_path.exists()
    assert b"Subject: Hello from the web UI" in output_path.read_bytes()


def test_convert_dispatches_calendar_and_contact_kinds(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invite_path = tmp_path / "invite.msg"
    _write_msg(invite_path)
    _stub_open_msg(monkeypatch, FakeCalendarItem(subject="Team sync"))
    response = client.post("/api/convert", json={"paths": [str(invite_path)]})
    (result,) = response.get_json()["results"]
    assert result["outputFormat"] == "ics"
    assert (tmp_path / "invite.ics").exists()
    assert b"BEGIN:VCALENDAR" in (tmp_path / "invite.ics").read_bytes()

    contact_path = tmp_path / "contact.msg"
    _write_msg(contact_path)
    _stub_open_msg(monkeypatch, FakeContact(displayName="Alice Dupont"))
    response = client.post("/api/convert", json={"paths": [str(contact_path)]})
    (result,) = response.get_json()["results"]
    assert result["outputFormat"] == "vcf"
    assert (tmp_path / "contact.vcf").exists()
    assert b"BEGIN:VCARD" in (tmp_path / "contact.vcf").read_bytes()


def test_convert_refuses_overwrite_unless_forced(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg())
    msg_path = tmp_path / "message.msg"
    _write_msg(msg_path)
    (tmp_path / "message.eml").write_bytes(b"pre-existing")

    response = client.post("/api/convert", json={"paths": [str(msg_path)]})
    (result,) = response.get_json()["results"]
    assert result["status"] == "failed"
    assert (tmp_path / "message.eml").read_bytes() == b"pre-existing"

    response = client.post("/api/convert", json={"paths": [str(msg_path)], "force": True})
    (result,) = response.get_json()["results"]
    assert result["status"] == "converted"
    assert (tmp_path / "message.eml").read_bytes() != b"pre-existing"


def test_convert_reports_skipped_for_unsupported_class(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(classType="IPM.StickyNote"))
    msg_path = tmp_path / "note.msg"
    _write_msg(msg_path)

    response = client.post("/api/convert", json={"paths": [str(msg_path)]})

    (result,) = response.get_json()["results"]
    assert result["status"] == "skipped"
    assert result["outputPath"] is None
    assert any("StickyNote" in w for w in result["warnings"])


def test_convert_reports_failed_for_garbage_input_without_crashing(client, tmp_path: Path) -> None:
    msg_path = tmp_path / "garbage.msg"
    msg_path.write_bytes(b"not an ole2 file at all")

    response = client.post("/api/convert", json={"paths": [str(msg_path)]})

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "failed"
    assert "OLE2" in result["error"]


def test_convert_handles_multiple_paths_in_one_request(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(subject="Batch message"))
    a_path = tmp_path / "a.msg"
    b_path = tmp_path / "b.msg"
    _write_msg(a_path)
    _write_msg(b_path)

    response = client.post("/api/convert", json={"paths": [str(a_path), str(b_path)]})

    results = response.get_json()["results"]
    assert [r["path"] for r in results] == [str(a_path), str(b_path)]
    assert all(r["status"] == "converted" for r in results)


def test_convert_rejects_missing_paths_payload(client) -> None:
    response = client.post("/api/convert", json={})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_convert_rejects_non_list_paths_payload(client) -> None:
    response = client.post("/api/convert", json={"paths": "not-a-list"})
    assert response.status_code == 400


def test_convert_with_empty_string_output_path_writes_next_to_source(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test: the frontend always sends an outputPath field, using
    "" for "no destination folder chosen" (never omitting the key). That
    must behave exactly like a request with no outputPath at all -- writing
    next to the source -- and must NOT resolve "" to the server process's
    current working directory."""
    monkeypatch.chdir(tmp_path)  # a decoy cwd distinct from the source's folder
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    msg_path = source_dir / "message.msg"
    _write_msg(msg_path)
    _stub_open_msg(monkeypatch, FakeMsg())

    response = client.post(
        "/api/convert",
        json={"paths": [str(msg_path)], "outputPath": "", "scanRoot": str(source_dir)},
    )

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "converted"
    assert result["outputPath"] == str(source_dir / "message.eml")
    assert (source_dir / "message.eml").exists()
    assert not (tmp_path / "message.eml").exists()


def test_convert_rejects_output_path_pointing_at_an_existing_file(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg())
    msg_path = tmp_path / "message.msg"
    _write_msg(msg_path)
    not_a_dir = tmp_path / "not-a-dir.txt"
    not_a_dir.write_text("i am a file, not a folder")

    response = client.post(
        "/api/convert", json={"paths": [str(msg_path)], "outputPath": str(not_a_dir)}
    )

    assert response.status_code == 400
    assert "not a folder" in response.get_json()["error"].lower()


def test_convert_with_output_path_and_preserve_structure_mirrors_scan_root(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg())
    source_dir = tmp_path / "source"
    nested_msg = source_dir / "sub" / "deep" / "nested.msg"
    _write_msg(nested_msg)
    dest_dir = tmp_path / "dest"

    response = client.post(
        "/api/convert",
        json={
            "paths": [str(nested_msg)],
            "outputPath": str(dest_dir),
            "preserveStructure": True,
            "scanRoot": str(source_dir),
        },
    )

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "converted"
    expected = dest_dir / "sub" / "deep" / "nested.eml"
    assert result["outputPath"] == str(expected)
    assert expected.exists()


def test_convert_with_output_path_and_flat_structure_ignores_source_subfolders(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg())
    source_dir = tmp_path / "source"
    nested_msg = source_dir / "sub" / "deep" / "nested.msg"
    _write_msg(nested_msg)
    dest_dir = tmp_path / "dest"

    response = client.post(
        "/api/convert",
        json={
            "paths": [str(nested_msg)],
            "outputPath": str(dest_dir),
            "preserveStructure": False,
            "scanRoot": str(source_dir),
        },
    )

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "converted"
    assert result["outputPath"] == str(dest_dir / "nested.eml")
    assert not (dest_dir / "sub").exists()


def test_convert_with_output_path_but_no_scan_root_falls_back_to_flat(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg())
    msg_path = tmp_path / "source" / "message.msg"
    _write_msg(msg_path)
    dest_dir = tmp_path / "dest"

    response = client.post(
        "/api/convert", json={"paths": [str(msg_path)], "outputPath": str(dest_dir)}
    )

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "converted"
    assert result["outputPath"] == str(dest_dir / "message.eml")


def test_browse_output_lists_only_subfolders(client, tmp_path: Path) -> None:
    (tmp_path / "Archive").mkdir()
    (tmp_path / ".hidden").mkdir()
    _write_msg(tmp_path / "standalone.msg")

    response = client.get(f"/api/browse-output?path={tmp_path}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["path"] == str(tmp_path)
    assert data["folders"] == ["Archive"]
    assert "msgFiles" not in data


def test_browse_output_returns_404_for_a_missing_path(client, tmp_path: Path) -> None:
    response = client.get(f"/api/browse-output?path={tmp_path / 'does-not-exist'}")
    assert response.status_code == 404


def test_convert_handles_a_very_large_batch_of_paths_in_one_request(tmp_path: Path) -> None:
    """Regression test for a real report: converting a folder of ~6000 .msg
    files in one click used to send a single /api/convert request whose JSON
    body of absolute paths alone could exceed an artificial request-size cap
    -- before any file content was ever involved. This app has no such cap at
    all now (it's local-only and single-user; there's no real resource
    boundary to protect, so the web UI can handle a folder of any size the
    same way the CLI always could), so this sends everything in one request
    -- deliberately bypassing the frontend's own batching -- to prove the
    backend itself imposes no limit. The paths don't need to exist on disk:
    convert_file fails fast (and cheaply) on a nonexistent path, so this
    stays fast despite the large request body."""
    app = create_app()
    app.config["TESTING"] = True
    paths = [str(tmp_path / f"message_{i:05d}.msg") for i in range(6000)]

    with app.test_client() as test_client:
        response = test_client.post("/api/convert", json={"paths": paths})

    assert response.status_code == 200
    results = response.get_json()["results"]
    assert len(results) == 6000
    assert all(r["status"] == "failed" for r in results)  # none of these paths exist on disk
