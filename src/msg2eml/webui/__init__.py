"""Local web UI for msg2eml.

Run ``msg2eml-ui`` to launch it in your browser. This subpackage is only
needed if you want the UI -- the core ``msg2eml`` command works without it.
Requires the optional ``ui`` extra (``pip install "msg2eml[ui]"``), which
pulls in Flask; that dependency is checked here, with a friendly message if
it's missing, before anything that imports Flask is loaded.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``msg2eml-ui`` console script."""
    try:
        import flask  # noqa: F401
    except ImportError:
        print(
            "The msg2eml web UI needs an extra dependency that isn't installed.\n"
            "Install it with:\n\n"
            '    pip install "msg2eml[ui]"\n\n'
            "(if you installed msg2eml with pipx: pipx inject msg2eml flask)\n",
            file=sys.stderr,
        )
        return 1

    from msg2eml.webui.app import run

    parser = argparse.ArgumentParser(
        prog="msg2eml-ui",
        description="Launch the msg2eml local web UI in your browser.",
    )
    parser.add_argument("--port", type=int, default=5151, help="Port to listen on (default: 5151)")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open a browser tab",
    )
    args = parser.parse_args(argv)

    run(port=args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
