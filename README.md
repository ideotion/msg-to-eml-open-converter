# msg2eml

Convert Microsoft Outlook `.msg` files into standard `.eml` files that open
in Thunderbird, Apple Mail, Gmail's import tools, or any other email
program that understands the standard email format.

## Why would I need this?

Outlook saves individual emails in a proprietary format called `.msg`.
Most other mail programs can't open `.msg` files at all. `.eml` is the
open, standard format (technically: RFC 5322 / MIME) that virtually every
other email program *can* open, including Thunderbird.

`msg2eml` is a command-line tool that converts `.msg` files to `.eml`
files. It keeps as much of the original message intact as possible:

- The subject, sender, recipients (To/Cc/Bcc), and date.
- The message body — including formatting, if the original had an HTML
  body, or a de-encapsulated version if the original only had a
  Microsoft-specific "Rich Text Format" body.
- File attachments, with their original names and file types preserved.
- Pictures embedded directly in the email body (not as separate
  attachments) — these still show up inline, not as attachments, in the
  converted email.
- Emails-within-emails (a forwarded or attached `.msg` file) — these are
  converted too, and kept attached to the outer email.
- Accented and non-English characters (e.g. é, à, ç, ü) in the subject,
  sender name, body, and attachment file names.

It will **not** convert calendar invitations, contacts, tasks, or sticky
notes saved as `.msg` files — only actual emails. If you point it at one of
those by mistake, it tells you and skips it instead of producing a broken
file.

## Installation

You need Python 3.10 or newer installed on your computer. To check,
open a terminal and run:

```sh
python3 --version
```

### Option A: automated install script (recommended)

Paste this into a terminal (macOS, Linux, or Windows Subsystem for Linux):

```sh
curl -fsSL https://raw.githubusercontent.com/ideotion/msg-to-eml-open-converter/main/install.sh | bash
```

This downloads msg2eml, installs [pipx](https://pipx.pypa.io/) for you if
you don't already have it, and installs both the `msg2eml` command and the
optional [web interface](#web-interface) (`msg2eml-ui`). It's safe to run
more than once — for example, to reinstall the latest version later.

Prefer not to pipe a downloaded script straight into `bash`? That's a
reasonable instinct — [read `install.sh`](install.sh) first, or download it
and run `bash install.sh` yourself once you're satisfied with what it does.

To skip the web interface and install only the command-line tool, set
`MSG2EML_WITH_UI=0` first:

```sh
MSG2EML_WITH_UI=0 bash -c "$(curl -fsSL https://raw.githubusercontent.com/ideotion/msg-to-eml-open-converter/main/install.sh)"
```

### Option B: manual install

1. Install `pipx` if you don't already have it (see the
   [pipx installation guide](https://pipx.pypa.io/stable/installation/)
   for your operating system).
2. Download or clone this project's source code to your computer.
3. Open a terminal, navigate into the project folder (the one containing
   `pyproject.toml`), and run:

   ```sh
   pipx install .
   ```

   Or, to also get the [web interface](#web-interface) (`msg2eml-ui`):

   ```sh
   pipx install ".[ui]"
   ```

That's it — the `msg2eml` command is now available in your terminal.
(Already installed without the web interface and want to add it? Run
`pipx inject msg2eml flask`.)

(If you don't want to use `pipx`, a plain `pip install .` — ideally inside
a [virtual environment](https://docs.python.org/3/library/venv.html) — also
works.)

## Usage

### Convert a single file

```sh
msg2eml message.msg
```

This creates `message.eml` in the same folder as `message.msg`.

To choose a different output file or folder, use `-o`:

```sh
msg2eml message.msg -o converted-message.eml
msg2eml message.msg -o /path/to/some/folder/
```

### Convert a whole folder of `.msg` files

```sh
msg2eml ./my-outlook-export -r
```

This finds every `.msg` file inside `./my-outlook-export` — including
subfolders, because of `-r` — and converts each one, saving each `.eml`
right next to the `.msg` file it came from.

To collect all the converted files into a separate folder instead (with
the same subfolder structure preserved), add `-o`:

```sh
msg2eml ./my-outlook-export -r -o ./converted-emails
```

Leave off `-r` to convert only the `.msg` files directly inside the given
folder, without descending into subfolders.

### Get a machine-readable summary

If you're converting a lot of files and want a record of exactly what
happened to each one (useful for double-checking a large migration), add
`--json-report`:

```sh
msg2eml ./my-outlook-export -r --json-report report.json
```

`report.json` will contain one entry per `.msg` file found, recording
whether it was converted, skipped, or failed, along with any warnings and
the resulting output path.

## Web interface

If you'd rather not use a terminal, `msg2eml` also has a small, minimalist
web interface that runs entirely on your own computer — nothing is ever
uploaded anywhere, it's just a convenient local page for drag-and-drop
conversion. It requires the `ui` extra (see [Installation](#installation)).

```sh
msg2eml-ui
```

This opens a browser tab automatically. Drag one or more `.msg` files onto
the page (or click it to browse for files), press **Convert**, then click
**Download** next to each converted file (or **Download all**). It supports
individual and multiple files; converting a whole folder recursively is
currently a command-line-only feature (see above).

Options:

| Option | What it does |
| --- | --- |
| `--port PORT` | Which local port to listen on (default: `5151`). |
| `--no-browser` | Don't automatically open a browser tab. |

Only the CLI (`msg2eml`) is installed by default; if you see a message
about a missing dependency when running `msg2eml-ui`, install the extra
with `pip install "msg2eml[ui]"` (or `pipx inject msg2eml flask` if you
installed with pipx).

## Options

| Option | What it does |
| --- | --- |
| `path` | The `.msg` file, or folder of `.msg` files, to convert. Required. |
| `-o PATH`, `--output PATH` | Where to write the result. For a single file, this can be a specific output file name or a folder. For a folder input, this is always treated as the destination folder. If omitted, output files are written next to their source files. |
| `-r`, `--recursive` | When converting a folder, also look inside its subfolders. |
| `--force` | Overwrite an output `.eml` file if it already exists. Without this, `msg2eml` refuses to overwrite existing files so you don't lose previous work by accident. |
| `--json-report PATH` | Write a JSON summary of the run (status, warnings, output path for every file) to `PATH`. |
| `--verbose` | Print extra detail while converting, including every warning encountered (missing sender, RTF that couldn't be converted cleanly, etc.). |
| `--quiet` | Print nothing except errors. Useful for scripts. |
| `-h`, `--help` | Show usage help. |

`--verbose` and `--quiet` cannot be used together.

## Exit codes

If you're calling `msg2eml` from a script, its exit code tells you how the
run went:

| Code | Meaning |
| --- | --- |
| `0` | Everything that could be converted, was converted (this includes runs where some files were legitimately skipped, e.g. calendar invites). |
| `1` | The run finished, but at least one file failed to convert. Check the log output or `--json-report` for details. |
| `2` | The run could not start at all — for example, the given path doesn't exist, or isn't a `.msg` file. |

## Known limitations

- Only email items are converted. Calendar invitations, contacts, tasks,
  sticky notes, and similar Outlook item types stored as `.msg` are
  detected and skipped with a warning, not converted.
- If an email's body only exists as Microsoft's Rich Text Format (no plain
  text or HTML version was saved), `msg2eml` tries to convert it to HTML.
  This conversion is very reliable for typical Outlook emails, but for
  unusual or corrupted RTF content, it may fall back to a rougher,
  formatting-stripped plain-text version rather than fail outright.
  Anything odd here is recorded as a warning.
- Password-protected or DRM/rights-managed (IRM) messages are not
  supported.
- Very old or unusual `.msg` files that are missing standard information
  (like a sender or a date) will convert successfully, but the resulting
  `.eml` will simply be missing that piece of information too — `msg2eml`
  never invents data that wasn't in the original file (except that it
  will generate a technical Message-ID if the original had none at all,
  since some mail programs expect every email to have one).

## Troubleshooting

**"Not a .msg file"** — You pointed `msg2eml` at a file that doesn't end
in `.msg`. Double check the file path.

**"Output file already exists"** — `msg2eml` won't overwrite a file it
already created (or that happens to have the same name) unless you pass
`--force`.

**A file shows up as "Skipped"** — This is normal for calendar invites,
contacts, tasks, and similar non-email items; they can't be meaningfully
turned into an email. Run with `--verbose` to see the exact reason.

**A file shows up as "Failed"** — The `.msg` file is likely corrupted,
password-protected, or otherwise unreadable. Run with `--verbose` to see
the underlying error. One failed file never stops the rest of a batch
conversion from continuing.

**Accented characters look garbled in my mail client** — This shouldn't
happen; `msg2eml` always writes correctly encoded UTF-8 output. If you do
see garbled text, please open an issue with the specific `.msg` file (if
you're able to share it) so it can be investigated.

**The converted email is missing an inline image** — This can happen if
the original `.msg` file didn't actually mark the image as linked to the
body (some very old or third-party tools that create `.msg` files don't
set this up correctly). The image should still be present as a regular
attachment.

**The web UI says the port is already in use** — Something else (perhaps
another `msg2eml-ui`) is already using port 5151. Either stop that, or run
`msg2eml-ui --port 5152` (or any other free port).

## For developers

This project uses [`extract-msg`](https://github.com/TeamMsgExtractor/msg-extractor)
to parse the `.msg` (OLE2 compound file) format, [`RTFDE`](https://github.com/seamustuohy/RTFDE)
and `compressed-rtf` to de-encapsulate Rich Text Format bodies into HTML,
the Python standard library's `email` package to build the resulting
`.eml` files, and (optionally, for the web interface) Flask.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"   # includes the 'ui' extra, so webui tests run too

ruff check .        # lint
ruff format .        # auto-format
mypy                  # type-check
pytest                # run the test suite
```

The web UI's conversion logic lives entirely in `msg2eml.convert` (the same
module the CLI uses, via `convert_bytes`); `msg2eml/webui/` is only a thin
Flask presentation layer over it (`app.py`, plus `templates/index.html` and
`static/` for the page itself).

Real `.msg` sample files can be placed in `tests/fixtures/real/` for local
integration testing; that folder is gitignored on purpose (email samples
often contain personal data) except for a `.gitkeep` placeholder that
keeps the folder itself in version control. If the folder is empty, the
integration test that reads from it is automatically skipped.
