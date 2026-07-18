"""Logging configuration for the msg2eml CLI."""

from __future__ import annotations

import logging


def configure_logging(*, verbose: bool, quiet: bool) -> None:
    """Configure the root logger for the CLI's three verbosity levels.

    Default: one concise INFO line per file. --verbose: DEBUG detail,
    including every warning collected during conversion. --quiet: only
    ERROR-level output (failed conversions).
    """
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(message)s", force=True)
    if not verbose:
        # extract-msg logs routine "stream not found" / fallback notices at INFO,
        # and RTFDE's Lark parser is chatty at DEBUG; neither belongs in the
        # default one-line-per-file output.
        logging.getLogger("extract_msg").setLevel(logging.WARNING)
        logging.getLogger("RTFDE").setLevel(logging.WARNING)
