"""Discovery of .msg files and output-path resolution for single/batch modes."""

from __future__ import annotations

from pathlib import Path


def discover_msg_files(root: Path, *, recursive: bool) -> list[Path]:
    """Find .msg files under root, sorted for deterministic ordering.

    The extension match is case-insensitive (``.msg``/``.MSG``/...), which
    matters on case-sensitive filesystems (most Linux/macOS setups).
    """
    pattern = "**/*" if recursive else "*"
    return sorted(p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() == ".msg")


def resolve_single_output_path(input_path: Path, *, output: str | None) -> Path:
    """Compute a placeholder output path for single-file mode.

    The ``.eml`` extension here is only a placeholder: the source's actual
    message kind (and thus its real extension -- ``.eml``, ``.ics``, or
    ``.vcf``) isn't known until the .msg file is opened and classified, so
    :func:`msg2eml.convert.convert_file` swaps this path's suffix for the
    real one before writing.

    With no ``-o``, the output sits next to the source file. With ``-o``,
    an existing directory (or a path that looks like one) is treated as a
    destination folder; anything else is treated as the literal output
    file path. ``output`` is taken as the raw CLI string (not a ``Path``)
    because a trailing slash -- the signal that a not-yet-created directory
    was intended -- is normalized away as soon as it is wrapped in a
    ``Path``.
    """
    if output is None:
        return input_path.with_suffix(".eml")
    output_path = Path(output)
    if output_path.is_dir() or output.endswith(("/", "\\")):
        return output_path / input_path.with_suffix(".eml").name
    return output_path


def resolve_batch_output_path(input_path: Path, *, input_root: Path, output: Path | None) -> Path:
    """Compute a placeholder output path for a file discovered while walking input_root.

    Like :func:`resolve_single_output_path`, the ``.eml`` extension here is
    only a placeholder that :func:`msg2eml.convert.convert_file` replaces
    with the real one once the source's message kind is known.

    With no ``-o``, each file's output sits next to its source, so the
    relative folder structure is naturally preserved. With ``-o``, the
    same relative structure is mirrored into that output directory.
    """
    if output is None:
        return input_path.with_suffix(".eml")
    relative = input_path.resolve().relative_to(input_root.resolve())
    return (output / relative).with_suffix(".eml")
