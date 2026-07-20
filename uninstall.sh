#!/usr/bin/env bash
# msg2eml uninstaller: removes the `msg2eml` / `msg2eml-ui` pipx install,
# the desktop/Application shortcuts created by install.sh, and the
# downloaded source checkout.
#
# Usage:
#   ./uninstall.sh          Prompts for confirmation before removing anything.
#   ./uninstall.sh -y       Skips the confirmation prompt (also --yes).
#
# Options (set as environment variables before running):
#   MSG2EML_SRC_DIR=...  Where the source checkout lives (default: ~/.local/share/msg2eml-src).
#   This must match whatever MSG2EML_SRC_DIR was set to (if anything) when
#   install.sh was run, since that's where install.sh put things.
#
# Safe to re-run: every step tolerates msg2eml already being partially or
# fully removed.

set -euo pipefail

SRC_DIR="${MSG2EML_SRC_DIR:-$HOME/.local/share/msg2eml-src}"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$1" >&2; }

# --- Final cleanup step (see the big comment near the bottom) --------------
#
# When MSG2EML_UNINSTALL_FINAL_STEP=1 we are the re-exec'd tmp copy of this
# script, invoked purely to delete $SRC_DIR safely. Everything else (the
# confirmation prompt, the pipx uninstall, the shortcut removal) has already
# happened in the *original* invocation before it handed off to us -- do not
# repeat any of it here, just do the one thing we were re-launched for and
# exit.
if [ "${MSG2EML_UNINSTALL_FINAL_STEP:-0}" = "1" ]; then
  rm -rf "$SRC_DIR"
  rm -f "${MSG2EML_UNINSTALL_TMP_SELF:-}" 2>/dev/null || true
  info "msg2eml has been removed."
  exit 0
fi

# --- 1. Parse arguments ------------------------------------------------------

ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    *)
      error "Unknown option: $arg"
      echo "Usage: $0 [-y|--yes]" >&2
      exit 1
      ;;
  esac
done

# --- 2. Confirm before doing anything destructive ---------------------------
#
# This matters even when this script is launched from the "Uninstall
# msg2eml" desktop entry / .app bundle, which is exactly why those are set
# up with Terminal=true / an interactive Terminal window -- so this prompt
# actually has somewhere to be shown and answered.

if [ "$ASSUME_YES" != "1" ]; then
  read -r -p "Remove msg2eml and its shortcuts? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) ;;
    *)
      info "Cancelled -- nothing was removed."
      exit 0
      ;;
  esac
fi

# --- 3. pipx uninstall --------------------------------------------------------

info "Uninstalling msg2eml via pipx..."
pipx uninstall msg2eml || true

# --- 4. Desktop / Application shortcuts --------------------------------------

if [ "$(uname -s)" = "Linux" ]; then
  info "Removing desktop shortcuts..."
  rm -f "$HOME/.local/share/applications/msg2eml.desktop" \
        "$HOME/.local/share/applications/msg2eml-uninstall.desktop"
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
elif [ "$(uname -s)" = "Darwin" ]; then
  info "Removing Application shortcuts..."
  rm -rf "$HOME/Applications/msg2eml.app" "$HOME/Applications/msg2eml-uninstall.app"
fi

# --- 5. Remove the downloaded source checkout (must be LAST) ----------------
#
# This script is very often *itself* a file living inside $SRC_DIR -- that's
# exactly what the "Uninstall msg2eml" shortcut created by install.sh runs:
# "$SRC_DIR/uninstall.sh". That makes the final `rm -rf "$SRC_DIR"` a classic
# footgun: we would be deleting the directory that contains the very script
# currently executing.
#
# On most Unix systems this would *often* happen to work anyway -- once a
# shell has opened a script file to execute it, unlinking that file (or its
# parent directory) doesn't invalidate the already-open file descriptor, so
# reads already in flight keep working even after `rm -rf`. But "usually
# works" is not good enough for a destructive, one-shot operation: the exact
# behavior depends on how much of the script bash has already buffered vs.
# will still read from disk, how this script was invoked (`bash file.sh` vs
# being sourced vs re-read after a `cd`), and even the filesystem underneath
# $SRC_DIR (e.g. NFS handles a still-open-but-unlinked file very differently
# than ext4/APFS). Relying on any of that for the last step of an uninstaller
# is fragile in a way that's hard to test for in advance.
#
# The robust fix: copy this whole script to a private tmp file and `exec`
# that copy for the remainder of the run. `exec` replaces this process's
# running program *entirely* -- once it succeeds, nothing is being read from
# $SRC_DIR anymore (the running code now lives in the tmp copy), so deleting
# $SRC_DIR immediately afterwards is unconditionally safe, regardless of how
# we were originally invoked or what filesystem $SRC_DIR is on.

info "Removing the downloaded source checkout ($SRC_DIR)..."
TMP_SELF="$(mktemp "${TMPDIR:-/tmp}/msg2eml-uninstall.XXXXXX.sh")"
cp "$0" "$TMP_SELF"
chmod +x "$TMP_SELF"
MSG2EML_UNINSTALL_FINAL_STEP=1 \
  MSG2EML_SRC_DIR="$SRC_DIR" \
  MSG2EML_UNINSTALL_TMP_SELF="$TMP_SELF" \
  exec "$TMP_SELF"
# Nothing below this line ever runs in this process: `exec` above either
# replaces it (and the tmp copy takes over, per the branch at the top of
# this file) or -- if it somehow fails -- a non-interactive bash exits on a
# failed exec by default, so control never returns here either way.
