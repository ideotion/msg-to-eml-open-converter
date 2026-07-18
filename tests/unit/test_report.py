from __future__ import annotations

import json
from pathlib import Path

from msg2eml.convert import ConversionResult
from msg2eml.report import write_report


def test_write_report_creates_expected_json_structure(tmp_path: Path) -> None:
    results = [
        ConversionResult(
            input_path=Path("a.msg"),
            status="converted",
            output_path=Path("a.eml"),
            warnings=["some warning"],
        ),
        ConversionResult(input_path=Path("b.msg"), status="skipped", warnings=["not an email"]),
        ConversionResult(input_path=Path("c.msg"), status="failed", error="boom"),
    ]
    report_path = tmp_path / "report.json"
    write_report(results, report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data == [
        {
            "input_path": "a.msg",
            "output_path": "a.eml",
            "status": "converted",
            "warnings": ["some warning"],
            "error": None,
        },
        {
            "input_path": "b.msg",
            "output_path": None,
            "status": "skipped",
            "warnings": ["not an email"],
            "error": None,
        },
        {
            "input_path": "c.msg",
            "output_path": None,
            "status": "failed",
            "warnings": [],
            "error": "boom",
        },
    ]


def test_write_report_preserves_non_ascii_content(tmp_path: Path) -> None:
    results = [
        ConversionResult(
            input_path=Path("café.msg"),
            status="converted",
            output_path=Path("café.eml"),
            warnings=["Réunion à Nîmes"],
        )
    ]
    report_path = tmp_path / "report.json"
    write_report(results, report_path)
    raw = report_path.read_text(encoding="utf-8")
    assert "café.msg" in raw
    assert "Réunion à Nîmes" in raw


def test_write_report_creates_parent_directories(tmp_path: Path) -> None:
    report_path = tmp_path / "nested" / "dir" / "report.json"
    write_report([], report_path)
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == []
