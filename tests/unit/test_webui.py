from __future__ import annotations

import base64
import io

import pytest

flask_installed = pytest.importorskip("flask", reason="flask (the 'ui' extra) is not installed")

import msg2eml.convert as convert_module  # noqa: E402
from msg2eml.webui.app import create_app  # noqa: E402
from tests.helpers import OLE2_MAGIC, FakeMsg  # noqa: E402


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _stub_open_msg(monkeypatch: pytest.MonkeyPatch, msg: FakeMsg | Exception) -> None:
    def fake_open_msg(_source: object) -> FakeMsg:
        if isinstance(msg, Exception):
            raise msg
        return msg

    monkeypatch.setattr(convert_module.extract_msg, "openMsg", fake_open_msg)


def _upload(filename: str, data: bytes) -> tuple[io.BytesIO, str]:
    return (io.BytesIO(data), filename)


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
    assert b"/convert" in js.data


def test_convert_with_no_files_returns_empty_results(client) -> None:
    response = client.post("/convert", data={}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert response.get_json() == {"results": []}


def test_convert_returns_eml_base64_for_a_valid_message(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(subject="Hello from the web UI"))

    response = client.post(
        "/convert",
        data={"files": [_upload("message.msg", OLE2_MAGIC + b"rest of fake msg")]},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "converted"
    assert result["filename"] == "message.msg"
    assert result["emlFilename"] == "message.eml"

    eml_bytes = base64.b64decode(result["emlBase64"])
    assert b"Subject: Hello from the web UI" in eml_bytes


def test_convert_reports_skipped_for_non_email_class(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(classType="IPM.Appointment"))

    response = client.post(
        "/convert",
        data={"files": [_upload("invite.msg", OLE2_MAGIC + b"rest")]},
        content_type="multipart/form-data",
    )

    (result,) = response.get_json()["results"]
    assert result["status"] == "skipped"
    assert "emlBase64" not in result
    assert any("Appointment" in w for w in result["warnings"])


def test_convert_reports_failed_for_garbage_upload_without_crashing(client) -> None:
    response = client.post(
        "/convert",
        data={"files": [_upload("garbage.msg", b"not an ole2 file at all")]},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    (result,) = response.get_json()["results"]
    assert result["status"] == "failed"
    assert "OLE2" in result["error"]
    assert "emlBase64" not in result


def test_convert_handles_multiple_files_in_one_request(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_open_msg(monkeypatch, FakeMsg(subject="Batch message"))

    response = client.post(
        "/convert",
        data={
            "files": [
                _upload("a.msg", OLE2_MAGIC + b"one"),
                _upload("b.msg", OLE2_MAGIC + b"two"),
            ]
        },
        content_type="multipart/form-data",
    )

    results = response.get_json()["results"]
    assert [r["filename"] for r in results] == ["a.msg", "b.msg"]
    assert all(r["status"] == "converted" for r in results)


def test_convert_sanitizes_path_traversal_style_upload_filename(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filename with path-traversal-style segments is real, browser-reachable
    input (unlike an embedded raw CR/LF, which multipart/form-data can't
    transport at all -- browsers escape it before the request is ever sent).
    """
    _stub_open_msg(monkeypatch, FakeMsg())

    response = client.post(
        "/convert",
        data={"files": [_upload("../../evil/name.msg", OLE2_MAGIC + b"x")]},
        content_type="multipart/form-data",
    )

    (result,) = response.get_json()["results"]
    assert "/" not in result["filename"]
    assert "/" not in result["emlFilename"]
    assert result["emlFilename"].endswith(".eml")


def test_request_entity_too_large_returns_clean_413(monkeypatch: pytest.MonkeyPatch) -> None:
    from msg2eml.webui import app as app_module

    app = app_module.create_app()
    app.config["TESTING"] = True
    app.config["MAX_CONTENT_LENGTH"] = 10  # tiny, to trigger the handler without a huge upload

    with app.test_client() as test_client:
        response = test_client.post(
            "/convert",
            data={"files": [_upload("message.msg", OLE2_MAGIC + b"more than ten bytes")]},
            content_type="multipart/form-data",
        )

    assert response.status_code == 413
    assert "too large" in response.get_json()["error"].lower()
