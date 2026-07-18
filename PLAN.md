# msg2eml — implementation plan

## Goal

A CLI tool, `msg2eml`, that converts Outlook `.msg` files (MS-OXMSG / OLE2
compound files) into standards-compliant `.eml` files (RFC 5322 + MIME),
readable by Thunderbird and any other standards-compliant mail client.

## Research summary (grounds the design below)

- **extract-msg** (PyPI `extract-msg`, latest 0.55.0, requires Python
  >= 3.8): `extract_msg.openMsg(path)` opens a `.msg` file and dispatches
  to a subclass based on `PidTagMessageClass` (`Message`, `Appointment`,
  `Contact`, `Task`, ... — all deriving from `MSGFile`; real emails derive
  from `MessageBase`). It exposes no direct "convert to `.eml`" helper, so
  we build the conversion ourselves on top of its parsed properties.
  Relevant properties on `MessageBase`: `subject`, `sender` (a formatted
  `"Name <addr>"` string), `to`/`cc`/`bcc` (formatted strings), `recipients`
  (list of `Recipient`, each with `.email`, `.formatted`, `.type`), `date`,
  `messageId`, `inReplyTo`, `header` (an `email.message.Message` parsed
  from the raw transport header stream, or synthesized if absent — this is
  where we pull `References` from), `body`, `htmlBody`, `rtfBody` (already
  decompressed by extract-msg internally). `MSGFile.classType` exposes the
  raw `PidTagMessageClass` string on any opened file, regardless of
  subclass — this is what we use for message-class gating. Attachments are
  exposed via `.attachments`; each has `.data` (bytes for normal
  attachments, a nested `MSGFile`-like object for embedded `.msg` files),
  `.mimetype`, `.cid`/`.contentId`, and filename via `.longFilename`/
  `.shortFilename`/`getFilename()`. All library exceptions derive from
  `extract_msg.exceptions.ExMsgBaseException`.
- **RTFDE** (PyPI `RTFDE`, latest ~0.1.2.2) + **compressed-rtf** (PyPI
  `compressed-rtf`, latest 1.0.7): `compressed_rtf.decompress(data)`
  reverses the LZFu compression Outlook may use for the raw RTF stream;
  `RTFDE.deencapsulate.DeEncapsulator(raw_rtf_bytes).deencapsulate()` then
  exposes `.content_type` (`"html"` or `"text"`) and `.html`/`.text`.
  RTFDE raises `NotEncapsulatedRtf`, `MalformedEncapsulatedRtf`,
  `MalformedRtf`, `UnsupportedRTFFormat` for content it can't handle —
  all must be caught so a bad RTF stream degrades gracefully instead of
  crashing a batch run. Because `extract-msg` already hands us decompressed
  RTF bytes in the common case, we treat `compressed_rtf.decompress`
  as a defensive first pass: try it, and only keep the result if it still
  looks like RTF (`{\rtf`); otherwise use the original bytes unchanged.
- **stdlib `email`**: build with `email.message.EmailMessage` under
  `email.policy.default` (NOT `utf8=True` — we want real RFC 2047 encoded
  headers for maximum compatibility, not raw UTF-8 headers, per the
  fidelity requirement). Nesting is built bottom-up:
  `set_content(plain)` → `add_alternative(html, subtype="html")` gives
  `multipart/alternative`; inline images are added by calling
  `add_related(img_bytes, "image", subtype, cid=...)` on the *html payload
  part itself* (`msg.get_payload()[1]` after the two calls above, or on
  the message directly if there is no plain-text alternative), which
  promotes just that part to `multipart/related`; finally regular
  attachments and nested messages are added via `add_attachment(...)` at
  the top level, which promotes the whole message to `multipart/mixed`.
  `Content-ID` values from `email.utils.make_msgid()` keep their angle
  brackets when passed as `cid=`, but the brackets are stripped for the
  `cid:` URL used inside the HTML `src` attribute. `message/rfc822`
  attachments (nested `.msg` files) are added by passing a built
  `EmailMessage` object to `add_attachment(..., subtype="rfc822")` — the
  content manager encodes nested messages without base64, per RFC 2046
  §5.2.1.

## Message-class gating

`PidTagMessageClass` prefixes (case-insensitive): `IPM.Note*` → email,
convert. `IPM.Appointment*` / `IPM.Schedule.Meeting*` → calendar,
`IPM.Contact*` → contact, `IPM.Task*` → task, `IPM.StickyNote*` → note,
`IPM.Post*` → post, `IPM.DistList*` → distribution list, `IPM.Activity*`
→ journal, `IPM.Document*` → document. Anything else (including empty/
missing) → unknown. Only `email` is convertible; everything else is
skipped at the top level with an explicit warning naming the detected
kind. This gate applies only to the top-level file being converted —
nested `.msg` attachments are always best-effort converted to
`message/rfc822` regardless of their own class, so user data is never
silently dropped.

## Package layout (`src/` layout, package name `msg2eml`)

```
pyproject.toml
LICENSE (existing GPLv3, kept as-is)
README.md
.gitignore
.github/workflows/ci.yml
src/msg2eml/
    __init__.py       - package version, public re-exports
    cli.py             - argparse CLI, exit codes, logging setup
    convert.py         - core: build an EmailMessage from a parsed msg object
    msgclass.py        - message-class classification (see above)
    rtf.py             - RTF de-encapsulation (compressed-rtf + RTFDE)
    attachments.py     - attachment/inline-image handling helpers
    headers.py         - header construction helpers (addresses, dates, ids)
    report.py           - JSON report data structures + writer
    walker.py           - recursive .msg discovery + output path mirroring
    exceptions.py       - Msg2EmlError and friends
    logging_utils.py    - logging configuration (default/verbose/quiet)
tests/
    fixtures/real/.gitkeep   - real .msg samples (gitignored, optional)
    unit/                    - unit tests against fakes/mocks
    integration/             - round-trip + real-fixture tests
```

`convert.build_eml()` is written against **duck-typed** parsed-message
objects (only relying on `getattr`, never `isinstance` checks against
`extract_msg` classes) so unit tests can pass simple fakes without needing
real `.msg` files or a real OLE2 parse.

## CLI behavior

- `msg2eml message.msg` → `message.eml` next to the source.
- `-o PATH`: file (single mode) or directory (batch mode) override.
- `-r`/`--recursive`: batch-convert every `.msg` under a folder, mirroring
  relative structure into the output directory.
- `--force`: allow overwriting existing output files (default: refuse).
- `--verbose` / `--quiet`: logging verbosity.
- `--json-report PATH`: write a JSON array, one object per input file,
  with `status` (`converted`/`skipped`/`failed`), `warnings`, and
  `output_path`.
- Exit codes: `0` all converted, `1` completed with some failures/skips
  counted as failures, `2` fatal error (e.g. bad arguments, input path
  does not exist).
- A single malformed `.msg` must never abort a batch: every file's
  conversion is wrapped in a broad `try/except`, logged, and recorded as
  `failed` in the report.

## Testing strategy

1. Unit tests for `msgclass.classify`/`is_convertible`.
2. Unit tests for `rtf.rtf_to_content` against monkeypatched
   `compressed_rtf`/`RTFDE` to exercise success and every failure mode.
3. Unit tests for `convert.build_eml` against a lightweight fake
   "parsed message" object covering: plain+html body, html-only, rtf-only
   (success and failure), inline images, nested `.msg` attachment,
   non-ASCII subject/sender/attachment filename, missing date/message-id.
4. Round-trip tests: every `EmailMessage` produced is serialized with
   `as_bytes()` and re-parsed with `email.parser.BytesParser`, asserting
   headers and MIME structure survive.
5. CLI tests (`argparse` wiring, exit codes, `--json-report` output,
   `--force` behavior) using small crafted `.msg` bytes.
6. `tests/fixtures/real/`: kept via `.gitkeep`, contents gitignored; an
   integration test converts any real `.msg` files found there and asserts
   basic validity, otherwise it is skipped.

## Tooling

- `ruff` for lint + format (configured in `pyproject.toml`).
- `mypy` for type checking (`ignore_missing_imports` for the three
  third-party libraries, which ship no stubs).
- GitHub Actions workflow running ruff, mypy, and pytest on push/PR.

## Steps

1. Write this plan, commit.
2. Scaffold packaging files (`pyproject.toml`, `.gitignore`, CI workflow).
3. Implement `msgclass.py`, `exceptions.py`, `rtf.py` with unit tests.
4. Implement `headers.py`, `attachments.py`, `convert.py` with unit tests.
5. Implement `report.py`, `walker.py`, `logging_utils.py`, `cli.py`.
6. Add round-trip + CLI tests, real-fixture integration test scaffold.
7. Write README for a non-developer audience.
8. Run ruff, mypy, pytest; fix every issue.
9. Commit in logical increments throughout; push; open a draft PR.
