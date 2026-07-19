"""Machine-readable JSON report for a conversion run."""

from __future__ import annotations

import json
from pathlib import Path

from msg2eml.convert import ConversionResult


def write_report(results: list[ConversionResult], report_path: Path) -> None:
    """Write a JSON array with one entry per converted/skipped/failed input file."""
    entries = [
        {
            "input_path": str(result.input_path),
            "output_path": str(result.output_path) if result.output_path else None,
            "output_format": result.output_format,
            "status": result.status,
            "warnings": result.warnings,
            "error": result.error,
        }
        for result in results
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
