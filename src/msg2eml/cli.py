"""Command-line interface for msg2eml."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from msg2eml.convert import ConversionResult, convert_file
from msg2eml.logging_utils import configure_logging
from msg2eml.report import write_report
from msg2eml.walker import discover_msg_files, resolve_batch_output_path, resolve_single_output_path

logger = logging.getLogger("msg2eml")

EXIT_OK = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_FATAL = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the msg2eml argument parser."""
    parser = argparse.ArgumentParser(
        prog="msg2eml",
        description="Convert Microsoft Outlook .msg files into standard .eml (RFC 5322/MIME) files.",
    )
    parser.add_argument(
        "path",
        help="A .msg file to convert, or a folder to convert (use -r for recursive batch mode)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Output .eml file or directory (default: write next to each source file)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="When PATH is a folder, convert every .msg file found in its subfolders too",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output .eml files instead of skipping them",
    )
    parser.add_argument(
        "--json-report",
        metavar="PATH",
        help="Write a machine-readable JSON report (one entry per file) to PATH",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose", action="store_true", help="Print detailed progress, including all warnings"
    )
    verbosity.add_argument("--quiet", action="store_true", help="Print nothing except errors")
    return parser


def _log_result(result: ConversionResult) -> None:
    if result.status == "converted":
        logger.info("Converted: %s -> %s", result.input_path, result.output_path)
        for warning in result.warnings:
            logger.debug("  warning: %s", warning)
    elif result.status == "skipped":
        reason = "; ".join(result.warnings) or "unsupported message type"
        logger.info("Skipped: %s (%s)", result.input_path, reason)
    else:
        logger.error("Failed: %s (%s)", result.input_path, result.error or "unknown error")
        for warning in result.warnings:
            logger.debug("  warning: %s", warning)


def _run(args: argparse.Namespace) -> list[ConversionResult]:
    input_path = Path(args.path)

    if input_path.is_dir():
        output_dir = Path(args.output) if args.output else None
        msg_files = discover_msg_files(input_path, recursive=args.recursive)
        if not msg_files:
            logger.warning("No .msg files found under %s", input_path)
        results = []
        for msg_file in msg_files:
            output_path = resolve_batch_output_path(
                msg_file, input_root=input_path, output=output_dir
            )
            result = convert_file(msg_file, output_path, force=args.force)
            _log_result(result)
            results.append(result)
        return results

    output_path = resolve_single_output_path(input_path, output=args.output)
    result = convert_file(input_path, output_path, force=args.force)
    _log_result(result)
    return [result]


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code; never raises."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose, quiet=args.quiet)

    input_path = Path(args.path)
    if not input_path.exists():
        logger.error("Input path does not exist: %s", input_path)
        return EXIT_FATAL
    if input_path.is_file() and input_path.suffix.lower() != ".msg":
        logger.error("Not a .msg file: %s", input_path)
        return EXIT_FATAL

    results = _run(args)

    if args.json_report:
        try:
            write_report(results, Path(args.json_report))
        except OSError as exc:
            logger.error("Could not write JSON report to %s: %s", args.json_report, exc)
            return EXIT_FATAL

    converted = sum(1 for r in results if r.status == "converted")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    logger.info("Done: %d converted, %d skipped, %d failed", converted, skipped, failed)

    return EXIT_PARTIAL_FAILURE if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
