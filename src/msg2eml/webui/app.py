"""Flask app backing the msg2eml local web UI.

This module imports Flask unconditionally, so it must only be imported
after :func:`msg2eml.webui.main` has confirmed Flask is actually installed
(the ``ui`` extra). Conversion is delegated to the same
:func:`msg2eml.convert.convert_file` and :func:`msg2eml.walker.discover_msg_files`
functions the CLI uses -- this UI is a thin presentation layer over the
local filesystem (the Flask server only ever binds to 127.0.0.1), not a
second implementation of anything.

There is deliberately no upload or download step here: a browser never
exposes a dropped/selected file's real absolute path to JavaScript or the
server, so an upload-bytes-then-download-blob design could never have
written a converted file "next to the original" in the first place. Instead
the browser lets the user navigate the real local folder tree (via
``/api/browse``/``/api/scan``) and the server reads/writes files directly by
path (via ``/api/convert``), exactly like a CLI batch run would.

``/api/scan`` and ``/api/convert`` only ever accept a JSON body. That's not
just a style choice: a plain HTML form can't set ``Content-Type:
application/json``, and a cross-origin ``fetch`` that tries to triggers a
CORS preflight this app never approves (it sends no
``Access-Control-Allow-Origin`` header) -- so this is also a cheap, free
CSRF defense for endpoints that read/write the local filesystem.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

from msg2eml.convert import convert_file
from msg2eml.walker import discover_msg_files

logger = logging.getLogger(__name__)


def _resolve_existing_dir(raw_path: str | None) -> tuple[Path | None, tuple[Response, int] | None]:
    """Resolve a user-supplied path to an existing directory, or an error response.

    Centralized here so /api/browse and /api/scan agree on exactly what
    counts as a usable folder and report the same errors for it.
    """
    target = Path(raw_path).expanduser() if raw_path else Path.home()
    try:
        target = target.resolve(strict=True)
    except OSError:
        return None, (jsonify({"error": f"Folder not found: {target}"}), 404)
    if not target.is_dir():
        return None, (jsonify({"error": f"Not a folder: {target}"}), 400)
    return target, None


def _resolve_output_dir(raw_path: str | None) -> tuple[Path | None, tuple[Response, int] | None]:
    """Resolve a user-supplied output path to a directory (can be non-existent).

    Unlike _resolve_existing_dir, this allows non-existent paths since the
    conversion will create them. Returns None for the path if raw_path is None.
    """
    if raw_path is None:
        return None, None
    target = Path(raw_path).expanduser()
    # Try to resolve, but don't require it to exist yet
    with contextlib.suppress(OSError):
        target = target.resolve()
    # Check if it's a directory path (ends with separator or is existing dir)
    raw_str = raw_path
    if target.is_dir() or raw_str.endswith(("/", "\\")):
        return target, None
    # If it doesn't end with separator and isn't a directory, treat as directory anyway
    # (the conversion will create it)
    return target, None


def create_app() -> Flask:
    """Build the Flask application. Kept separate from :func:`run` for testing."""
    app = Flask(__name__)
    # Deliberately no MAX_CONTENT_LENGTH: this is a local, single-user tool with
    # no real resource boundary to defend (the server only ever talks to itself
    # on 127.0.0.1), and /api/convert's body is just a JSON array of path
    # strings -- never file content -- so its size scales with folder size, not
    # with anything meaningful to cap. The CLI has no equivalent limit either;
    # the web UI should be able to handle a folder of any size the same way.

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
        target, error = _resolve_existing_dir(request.args.get("path"))
        if error is not None:
            return error
        assert target is not None

        try:
            entries = list(target.iterdir())
        except OSError as exc:
            return jsonify({"error": f"Could not read folder: {exc}"}), 403

        folders = sorted(
            (entry.name for entry in entries if entry.is_dir() and not entry.name.startswith(".")),
            key=str.lower,
        )
        msg_files = sorted(
            (entry.name for entry in entries if entry.is_file() and entry.suffix.lower() == ".msg"),
            key=str.lower,
        )
        parent = str(target.parent) if target.parent != target else None
        return jsonify(
            {"path": str(target), "parent": parent, "folders": folders, "msgFiles": msg_files}
        )

    @app.post("/api/scan")
    def scan() -> Response | tuple[Response, int]:
        payload = request.get_json(silent=True) or {}
        target, error = _resolve_existing_dir(payload.get("path"))
        if error is not None:
            return error
        assert target is not None

        try:
            found = discover_msg_files(target, recursive=True)
        except OSError as exc:
            return jsonify({"error": f"Could not scan folder: {exc}"}), 403

        files = []
        for msg_path in found:
            relative_folder = msg_path.parent.relative_to(target)
            files.append(
                {
                    "path": str(msg_path),
                    "name": msg_path.name,
                    "relativeFolder": "" if str(relative_folder) == "." else str(relative_folder),
                }
            )
        return jsonify({"root": str(target), "files": files})

    @app.post("/api/convert")
    def convert() -> Response | tuple[Response, int]:
        payload = request.get_json(silent=True) or {}
        paths = payload.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
            return jsonify({"error": "Expected a non-empty list of file paths"}), 400
        force = bool(payload.get("force", False))
        output_path = payload.get("outputPath")
        preserve_structure = payload.get("preserveStructure", True)

        # Resolve output directory if provided
        output_dir, error = _resolve_output_dir(output_path)
        if error is not None:
            return error

        results: list[dict[str, Any]] = []
        for raw_path in paths:
            input_path = Path(raw_path)
            # Determine output path based on whether we have a custom destination
            if output_dir is not None:
                # Use the output directory
                if preserve_structure:
                    # Calculate relative path from scan root to maintain structure
                    # The scan root is the parent of the first file's relative path
                    # For now, we'll use a simple approach: preserve relative to input's parent
                    # But we need the scan root. Let's use the first file's parent as reference
                    # Actually, we need to know the scan root. Let's pass it in the payload.
                    # For backward compatibility, if no scanRoot, just use flat
                    scan_root = payload.get("scanRoot")
                    if scan_root:
                        scan_root_path = Path(scan_root)
                        try:
                            relative = input_path.resolve().relative_to(scan_root_path.resolve())
                            output_file = (output_dir / relative).with_suffix(".eml")
                        except ValueError:
                            # File is outside scan root, use flat
                            output_file = output_dir / input_path.with_suffix(".eml").name
                    else:
                        # No scan root provided, use flat structure
                        output_file = output_dir / input_path.with_suffix(".eml").name
                else:
                    # Flat structure: all files directly in output directory
                    output_file = output_dir / input_path.with_suffix(".eml").name
            else:
                # No output directory specified, write next to source (original behavior)
                output_file = input_path.with_suffix(".eml")

            result = convert_file(input_path, output_file, force=force)
            results.append(
                {
                    "path": str(input_path),
                    "status": result.status,
                    "outputPath": str(result.output_path) if result.output_path else None,
                    "outputFormat": result.output_format,
                    "warnings": result.warnings,
                    "error": result.error,
                }
            )
        return jsonify({"results": results})

    @app.get("/api/browse-output")
    def browse_output() -> Response | tuple[Response, int]:
        """Browse for output directory selection."""
        target, error = _resolve_existing_dir(request.args.get("path"))
        if error is not None:
            return error
        assert target is not None

        try:
            entries = list(target.iterdir())
        except OSError as exc:
            return jsonify({"error": f"Could not read folder: {exc}"}), 403

        folders = sorted(
            (entry.name for entry in entries if entry.is_dir() and not entry.name.startswith(".")),
            key=str.lower,
        )
        parent = str(target.parent) if target.parent != target else None
        return jsonify({"path": str(target), "parent": parent, "folders": folders})

    return app


def _open_browser_quietly(url: str) -> None:
    """Best-effort browser launch: a headless machine with no browser must not
    take down the background thread it runs in (and, by extension, spam the
    log with a traceback that looks scarier than it is)."""
    try:
        webbrowser.open(url)
    except Exception:
        logger.debug("Could not open a browser tab automatically", exc_info=True)


def run(*, port: int, open_browser: bool) -> None:
    """Start the local server (blocking) and optionally open a browser tab."""
    app = create_app()
    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        threading.Timer(1.0, _open_browser_quietly, args=(url,)).start()
    print(f"msg2eml web UI running at {url} (press Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=port)
