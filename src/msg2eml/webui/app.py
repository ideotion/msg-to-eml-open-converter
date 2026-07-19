"""Flask app backing the msg2eml local web UI.

This module imports Flask unconditionally, so it must only be imported
after :func:`msg2eml.webui.main` has confirmed Flask is actually installed
(the ``ui`` extra). All conversion work is delegated to
:func:`msg2eml.convert.convert_bytes`, which is the same code path the
command-line tool uses -- this UI is a thin presentation layer, not a
second implementation of anything.
"""

from __future__ import annotations

import base64
import logging
import threading
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from msg2eml.attachments import sanitize_filename
from msg2eml.convert import convert_bytes

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB per request; generous for typical .msg files


def _output_filename(raw_filename: str, extension: str) -> str:
    """Derive a safe output filename from an uploaded .msg filename."""
    safe = sanitize_filename(raw_filename)
    stem = Path(safe).stem or "message"
    return f"{stem}.{extension}"


def create_app() -> Flask:
    """Build the Flask application. Kept separate from :func:`run` for testing."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.post("/convert")
    def convert() -> Response:
        results = []
        for upload in request.files.getlist("files"):
            raw_filename = upload.filename or "message.msg"
            display_filename = sanitize_filename(raw_filename)
            result = convert_bytes(upload.read(), display_filename)

            entry: dict[str, object] = {
                "filename": result.filename,
                "status": result.status,
                "warnings": result.warnings,
                "error": result.error,
            }
            if result.output_bytes is not None and result.output_format is not None:
                entry["outputFilename"] = _output_filename(raw_filename, result.output_format)
                entry["outputFormat"] = result.output_format
                entry["outputBase64"] = base64.b64encode(result.output_bytes).decode("ascii")
            results.append(entry)

        return jsonify({"results": results})

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(_exc: RequestEntityTooLarge) -> tuple[Response, int]:
        return jsonify({"error": "That upload is too large."}), 413

    return app


def run(*, port: int, open_browser: bool) -> None:
    """Start the local server (blocking) and optionally open a browser tab."""
    app = create_app()
    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"msg2eml web UI running at {url} (press Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=port)
