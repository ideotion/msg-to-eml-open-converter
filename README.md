# msg2eml

Convert Microsoft Outlook `.msg` files into standard, open formats that
open in Thunderbird, Apple Mail, Gmail's import tools, or any other program
that understands them: `.eml` for emails, `.ics` for calendar items and
tasks, and `.vcf` for contacts.

## Why would I need this?

Outlook saves items in a proprietary format called `.msg`. Most other
programs can't open `.msg` files at all. `msg2eml` converts each `.msg`
file to the open, standard format its content actually calls for:

- **Emails** become `.eml` (RFC 5322 / MIME), openable by virtually every
  email program, including Thunderbird.
- **Calendar items and meeting invitations** (`IPM.Appointment`,
  `IPM.Schedule.Meeting.*`) become `.ics` (iCalendar).
- **Tasks** (`IPM.Task`) also become `.ics`, as an iCalendar to-do item.
- **Contacts** (`IPM.Contact`) become `.vcf` (vCard 3.0), importable into
  Thunderbird's Address Book or any other contacts app.

`msg2eml` picks the right format automatically — you don't need to tell it
what kind of `.msg` file you're giving it. It keeps as much of the original
item intact as possible:

- For emails: the subject, sender, recipients (To/Cc/Bcc), date, and body
  (including formatting, if the original had an HTML body, or a
  de-encapsulated version if the original only had a Microsoft-specific
  "Rich Text Format" body).
- File attachments, with their original names and file types preserved.
- Pictures embedded directly in an email body (not as separate
  attachments) — these still show up inline, not as attachments, in the
  converted email.
- Items-within-items (a forwarded or attached `.msg` file, of any of the
  kinds above) — these are converted too, and kept attached to the outer
  item with the correct type.
- Accented and non-English characters (e.g. é, à, ç, ü) throughout.
- For calendar items: subject, location, body, start/end time, organizer,
  attendees, and busy/tentative/free status.
- For tasks: subject, body, start/due dates, completion date and percent,
  status, and priority.
- For contacts: name, company, job title, email addresses, phone numbers,
  postal addresses, birthday, photo, and notes.

Sticky notes, distribution lists, journal entries, and other Outlook item
types saved as `.msg` are not converted — if you point `msg2eml` at one of
those, it tells you and skips it instead of producing a broken file. See
[Known limitations](#known-limitations) for calendar/task/contact-specific
caveats (in particular, recurring events and meeting-invite semantics).

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

Once installed, it also (all of this only on Linux and macOS):

- **Launches the web interface automatically** in a browser tab, running
  quietly in the background from then on (or, if one's already running,
  just opens a tab to it instead of starting a second one).
- **Adds "Start msg2eml" and "Uninstall msg2eml" shortcuts** — to your
  applications menu on Linux (also visible in the Windows Start Menu under
  WSLg), or to `~/Applications` on macOS.

Prefer not to pipe a downloaded script straight into `bash`? That's a
reasonable instinct — [read `install.sh`](install.sh) first, or download it
and run `bash install.sh` yourself once you're satisfied with what it does.

All of the above can be tuned with environment variables set before running
the script:

| Variable | Default | Effect when set to `0` |
| --- | --- | --- |
| `MSG2EML_WITH_UI` | `1` | Skip the web interface entirely (CLI only). |
| `MSG2EML_AUTO_LAUNCH` | `1` | Don't launch/open the web UI after installing. |
| `MSG2EML_SHORTCUTS` | `1` | Don't create the desktop/Application shortcuts. |
| `MSG2EML_UI_PORT` | `5151` | *(not a toggle)* Port to auto-launch the web UI on. |

For example, to install just the command-line tool with none of the GUI
extras:

```sh
MSG2EML_WITH_UI=0 bash -c "$(curl -fsSL https://raw.githubusercontent.com/ideotion/msg-to-eml-open-converter/main/install.sh)"
```

### Uninstalling

Click the **"Uninstall msg2eml"** shortcut install.sh created, or run the
uninstaller it downloaded alongside msg2eml directly:

```sh
bash ~/.local/share/msg2eml-src/uninstall.sh
```

It asks for confirmation, then removes the `msg2eml`/`msg2eml-ui` commands,
the shortcuts, and the downloaded source checkout.

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

This creates `message.eml` next to `message.msg` — or `message.ics` /
`message.vcf`, if `message.msg` turns out to be a calendar item, task, or
contact instead of an email; `msg2eml` figures that out automatically once
it opens the file.

To choose a different output file or folder, use `-o`:

```sh
msg2eml message.msg -o converted-message.eml
msg2eml message.msg -o /path/to/some/folder/
```

(If `-o` names a specific file, its extension is still replaced with the
correct one for what the source turns out to be — `-o out.eml` for a
contact becomes `out.vcf`.)

### Convert a whole folder of `.msg` files

```sh
msg2eml ./my-outlook-export -r
```

This finds every `.msg` file inside `./my-outlook-export` — including
subfolders, because of `-r` — and converts each one to whichever format
matches its content, saving it right next to the `.msg` file it came from.

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
web interface that runs entirely on your own computer. It requires the
`ui` extra (see [Installation](#installation)) and is launched
automatically by `install.sh`; to start it yourself later:

```sh
msg2eml-ui
```

This opens a browser tab automatically. Unlike a typical web app, there's
no upload or download step at all: the page shows a simple folder browser
for navigating your own computer's files, and every conversion is written
right next to its source file, exactly like the command line does — a
browser can never tell a web page (or the local server behind it) the real
absolute path of a file you dropped or selected, so that's the only way
"write the result next to the original" can actually work here.

- **Browse** into a folder using the breadcrumbs and the folder list.
- **Convert a single file** directly from the list with its own
  **Convert** button — handy when a folder has just one or two `.msg`
  files sitting in it directly.
- **Convert a whole folder tree at once** with **Scan this folder for
  `.msg` files** — this looks recursively through every subfolder (even
  when the folder you're looking at has no `.msg` files directly inside
  it, only more subfolders), lists everything it finds grouped by which
  folder it's in, and lets you review the list before converting it all
  with one click. Tick **Overwrite already-converted files** first if
  you're intentionally re-converting something.

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
| `-o PATH`, `--output PATH` | Where to write the result. For a single file, this can be a specific output file name or a folder. For a folder input, this is always treated as the destination folder. If omitted, output files are written next to their source files. The extension is always chosen automatically based on the source's content (`.eml`/`.ics`/`.vcf`), even if `PATH` names a specific file with a different extension. |
| `-r`, `--recursive` | When converting a folder, also look inside its subfolders. |
| `--force` | Overwrite an output file if it already exists. Without this, `msg2eml` refuses to overwrite existing files so you don't lose previous work by accident. |
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
| `0` | Everything that could be converted, was converted (this includes runs where some files were legitimately skipped, e.g. sticky notes). |
| `1` | The run finished, but at least one file failed to convert. Check the log output or `--json-report` for details. |
| `2` | The run could not start at all — for example, the given path doesn't exist, or isn't a `.msg` file. |

## Known limitations

- Sticky notes, distribution lists, journal entries, and similar Outlook
  item types stored as `.msg` are detected and skipped with a warning, not
  converted — there's no open, standard format they'd meaningfully map to.
- **Calendar items are exported as standalone `.ics` files, not
  invite-shaped emails.** This is a deliberate choice: Thunderbird's
  plain file-based `.ics` import has no UID/SEQUENCE-aware update logic
  (re-importing an updated `.ics` for the same event causes a duplicate,
  rather than updating it), unlike its mail-integrated meeting-invite
  handling. Converting meeting invites to invite-shaped `.eml` files
  (with an embedded `text/calendar` part) is a possible future addition.
- **Recurring calendar events are exported as a single occurrence**, not
  a recurring series — decoding Outlook's internal recurrence-pattern
  format into an iCalendar `RRULE` is not yet implemented. A warning is
  included when this happens.
- If an email's body only exists as Microsoft's Rich Text Format (no plain
  text or HTML version was saved), `msg2eml` tries to convert it to HTML.
  This conversion is very reliable for typical Outlook emails, but for
  unusual or corrupted RTF content, it may fall back to a rougher,
  formatting-stripped plain-text version rather than fail outright.
  Anything odd here is recorded as a warning.
- Password-protected or DRM/rights-managed (IRM) messages are not
  supported.
- Very old or unusual `.msg` files that are missing standard information
  (like a sender, a date, or an event's start time) will convert
  successfully, but the result will simply be missing that piece of
  information too — `msg2eml` never invents data that wasn't in the
  original file (except that it will generate a technical Message-ID for
  an email that had none at all, since some mail programs expect every
  email to have one).

## Troubleshooting

**"Not a .msg file"** — You pointed `msg2eml` at a file that doesn't end
in `.msg`. Double check the file path.

**"Output file already exists"** — `msg2eml` won't overwrite a file it
already created (or that happens to have the same name) unless you pass
`--force`.

**A file shows up as "Skipped"** — This is normal for sticky notes,
distribution lists, journal entries, and similar Outlook item types that
have no open-format equivalent to convert to. Run with `--verbose` to see
the exact reason. (Calendar items, tasks, and contacts are *not* skipped —
they're converted to `.ics`/`.vcf`.)

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

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the codebase
fits together (the message-kind dispatch pipeline, the four format
builders, the hardening layers, the web UI's local-filesystem design, and
the duck-typed testing approach) and [`CONTRIBUTING.md`](CONTRIBUTING.md)
for setting up a dev environment, running the checks, and a walkthrough of
adding support for another Outlook item type. In short:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"   # includes the 'ui' extra, so webui tests run too

ruff check .           # lint
ruff format .          # auto-format
mypy                   # type-check
pytest                 # run the test suite
```

Real `.msg` sample files can be placed in `tests/fixtures/real/` for local
integration testing; that folder is gitignored on purpose (email samples
often contain personal data) except for a `.gitkeep` placeholder that
keeps the folder itself in version control. If the folder is empty, the
integration test that reads from it is automatically skipped.
