# Contributing to msg2eml

msg2eml is a small, single-maintainer open-source utility, not an
enterprise project — this guide is deliberately short. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the codebase fits
together before making non-trivial changes.

## Setting up a dev environment

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The `dev` extra (see `pyproject.toml`) pulls in the `ui` extra (Flask, for
the web interface) plus `pytest`, `ruff`, and `mypy` — one install gets you
everything needed to work on any part of the project, including the web UI.

## Running the checks

These are the same commands CI runs (`.github/workflows/ci.yml`), against
Python 3.10, 3.11, and 3.12:

```sh
ruff check .          # lint
ruff format --check . # formatting (drop --check to auto-format locally)
mypy                  # type-check
pytest -v             # test suite
```

Run `ruff format .` (without `--check`) to auto-fix formatting before
committing.

## Writing tests

Prefer the duck-typed fakes in `tests/helpers.py` (`FakeMsg`,
`FakeRecipient`, `FakeAttachment`, `FakeContact`, `FakeTask`,
`FakeCalendarItem`) over real `.msg` files for new unit tests. Every
builder (`build_eml`, `calendar_convert.build_ics`,
`contact_convert.build_vcard`, `task_convert.build_task_ics`) and helper
module is written against duck-typed, `Any`-typed message objects — touched
only via `getattr()`, never `isinstance` checks against `extract_msg`'s own
classes — so a plain dataclass exposing the same attributes is a fully
valid stand-in. This is how the existing unit tests under `tests/unit/`
work; most need no real `.msg` file at all. For example:

```python
item = FakeCalendarItem(
    subject="Meeting",
    appointmentStartWhole=datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc),
    appointmentEndWhole=datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc),
)
raw = build_ics(item, warnings=[])
```

Real `.msg` sample files are only needed for deeper integration testing —
put them in `tests/fixtures/real/`. That folder is gitignored on purpose
(email/calendar/contact samples routinely carry personal data), with only
a `.gitkeep` placeholder tracked to keep the folder itself in version
control. `tests/integration/test_real_fixtures.py` reads from it and
auto-skips when the folder is empty (e.g. a fresh checkout, or CI), so you
never need real samples to get a passing test run — just add them locally
to exercise the real parsing/conversion path more thoroughly.

## Code style

There's no separate style guide beyond what `ruff`/`mypy` already enforce
(configured in `pyproject.toml`). What's observably already true of this
codebase, and worth keeping true:

- No unnecessary abstractions — builders are plain functions
  (`build_*(msg, *, warnings=None) -> bytes`), not classes or plugin
  frameworks.
- Comments explain non-obvious *why*, not *what* — see almost any module
  docstring in `src/msg2eml/` for the pattern (e.g. `rtf.py` explaining
  why decompression is attempted defensively, `headers.py` explaining why
  header values are sanitized at one chokepoint).
- Fully typed: `mypy` runs with `disallow_untyped_defs` and
  `disallow_incomplete_defs` for `src/` (relaxed for `tests/`).
- GPLv3 (`GPL-3.0-or-later`, see `LICENSE`) — new files should be
  compatible with that.

## Adding support for a new `.msg` kind

The four existing builders are a template for adding another Outlook item
type (e.g. sticky notes, distribution lists — currently classified but
skipped, per `msgclass.py` and the README's "Known limitations"). Each is
a small, self-contained module:

1. **Add (or confirm) a `MessageKind` member** in
   `src/msg2eml/msgclass.py`, and a `(prefix, kind)` entry in
   `_PREFIX_KINDS` mapping the relevant `PidTagMessageClass` prefix (e.g.
   `ipm.stickynote`) to it.
2. **Write a builder module**, `src/msg2eml/<kind>_convert.py`, exposing a
   single function `build_<kind>(msg: Any, *, warnings: list[str] | None =
   None) -> bytes`. Follow `calendar_convert.py`/`contact_convert.py`/
   `task_convert.py` as templates: read fields from `msg` only via
   `getattr()` (never assume a real `extract_msg` type), default
   `warnings` to `[]` if `None`, and append a warning string for anything
   the source lacked or that couldn't be mapped losslessly instead of
   silently dropping it.
3. **Wire it into the dispatch table** in `_build_for_msg()`
   (`src/msg2eml/convert.py`): add an `if kind is msgclass.MessageKind.<KIND>:`
   branch returning a `BuildOutput` with the right `extension`/
   `maintype`/`subtype` and `content=<kind>_convert.build_<kind>(msg,
   warnings=warnings)`.
4. **Write unit tests** in `tests/unit/test_<kind>_convert.py` against a
   new `Fake<Kind>` dataclass added to `tests/helpers.py`, following the
   existing fakes' style (defaults for every attribute the builder reads).

That's the whole surface area — no other module needs to know about a new
kind besides `msgclass.py` (classification) and `convert.py` (dispatch).
