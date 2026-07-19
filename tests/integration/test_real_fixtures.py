"""Integration test against real .msg files, if any are present locally.

``tests/fixtures/real/`` is tracked only via a ``.gitkeep`` placeholder;
its contents are gitignored (see the .gitignore entry and the project
README). Contributors can drop real .msg samples there for deeper local
testing. When the directory is empty (as in a fresh checkout or CI), this
test is automatically skipped by pytest rather than failing -- parametrizing
with an empty list is pytest's documented way to report "got empty
parameter set" as a skip.
"""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

from msg2eml.convert import convert_file

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "real"


def _real_msg_files() -> list[Path]:
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(p for p in FIXTURES_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".msg")


@pytest.mark.parametrize("msg_path", _real_msg_files(), ids=lambda p: p.name)
def test_real_fixture_converts_to_valid_eml(msg_path: Path, tmp_path: Path) -> None:
    output_path = tmp_path / (msg_path.stem + ".eml")

    result = convert_file(msg_path, output_path, force=True)

    assert result.status in ("converted", "skipped"), (
        f"expected converted or skipped, got failed: {result.error}"
    )
    if result.status == "converted":
        assert output_path.exists()
        raw = output_path.read_bytes()
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        assert not parsed.defects
        assert parsed["Subject"] is not None or parsed["From"] is not None
        assert parsed.get_content_type().startswith(("text/", "multipart/"))
