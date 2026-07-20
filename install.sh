#!/usr/bin/env bash
# msg2eml installer: downloads the project source and installs the
# `msg2eml` (and `msg2eml-ui`) commands with pipx.
#
# Usage (paste this whole line into a terminal):
#
#   curl -fsSL https://raw.githubusercontent.com/ideotion/msg-to-eml-open-converter/main/install.sh | bash
#
# Options (set as environment variables before running):
#   MSG2EML_WITH_UI=0      Skip installing the optional web interface (Flask).
#   MSG2EML_BRANCH=main    Install from a different branch/tag.
#   MSG2EML_SRC_DIR=...    Where to download the source (default: ~/.local/share/msg2eml-src).
#   MSG2EML_AUTO_LAUNCH=0  Don't launch/open the web UI after installing.
#   MSG2EML_UI_PORT=5151   Port to use when auto-launching the web UI.
#   MSG2EML_SHORTCUTS=0    Don't create "Start msg2eml" / "Uninstall msg2eml" desktop shortcuts.
#
# Safe to re-run: it always reinstalls cleanly rather than leaving stale state.

set -euo pipefail

REPO="ideotion/msg-to-eml-open-converter"
BRANCH="${MSG2EML_BRANCH:-main}"
WITH_UI="${MSG2EML_WITH_UI:-1}"
SRC_DIR="${MSG2EML_SRC_DIR:-$HOME/.local/share/msg2eml-src}"
AUTO_LAUNCH="${MSG2EML_AUTO_LAUNCH:-1}"
PORT="${MSG2EML_UI_PORT:-5151}"
SHORTCUTS="${MSG2EML_SHORTCUTS:-1}"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$1" >&2; }

# --- 1. Python 3.10+ -----------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
  error "python3 was not found."
  echo "Install Python 3.10 or newer from https://www.python.org/downloads/ and re-run this script." >&2
  exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_OK="$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')"
if [ "$PY_OK" != "1" ]; then
  error "Python 3.10 or newer is required (found $PY_VERSION)."
  echo "Install a newer Python from https://www.python.org/downloads/ and re-run this script." >&2
  exit 1
fi
info "Found Python $PY_VERSION"

# --- 2. pipx --------------------------------------------------------------
#
# Bootstrapping pipx has to work across very different Python setups: a
# normal python.org/Homebrew install (pip always available), a minimal
# Debian/Ubuntu system (python3's pip module often isn't installed at all),
# and a Debian/Ubuntu system new enough to refuse any pip install outside a
# virtualenv (PEP 668) even once pip exists. Each of those needs a different
# fix, so this tries progressively more invasive options, stopping at the
# first that works.

NEEDS_NEW_SHELL=0

pip_install_pipx() {
  # --break-system-packages only matters (and is only reached) on the
  # PEP-668 "externally managed" Python builds that reject the plain form;
  # it's scoped to this one `pip install --user pipx` call.
  python3 -m pip install --user --quiet --upgrade pipx 2>/dev/null \
    || python3 -m pip install --user --quiet --upgrade --break-system-packages pipx
}

after_pipx_installed_by_pip() {
  python3 -m pipx ensurepath >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
  NEEDS_NEW_SHELL=1
}

install_pipx() {
  command -v pipx >/dev/null 2>&1 && return 0
  info "pipx not found; installing it..."

  if python3 -m pip --version >/dev/null 2>&1; then
    if pip_install_pipx; then
      after_pipx_installed_by_pip
      return 0
    fi
  else
    info "python3's pip module isn't installed; trying to bootstrap it with ensurepip..."
    if python3 -m ensurepip --upgrade >/dev/null 2>&1 && pip_install_pipx; then
      after_pipx_installed_by_pip
      return 0
    fi
  fi

  # Last resort: the OS's own package manager (the officially recommended
  # route on Debian/Ubuntu in particular). Needs sudo if not already root.
  local sudo_cmd=""
  if [ "$(id -u)" != "0" ]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo_cmd="sudo"
    else
      return 1
    fi
  fi

  if command -v apt-get >/dev/null 2>&1; then
    info "Installing pipx via apt (this may ask for your password)..."
    $sudo_cmd apt-get update -qq || true
    $sudo_cmd apt-get install -y pipx || true
  elif command -v dnf >/dev/null 2>&1; then
    info "Installing pipx via dnf (this may ask for your password)..."
    $sudo_cmd dnf install -y pipx || true
  elif command -v brew >/dev/null 2>&1; then
    info "Installing pipx via Homebrew..."
    brew install pipx || true
  fi

  if command -v pipx >/dev/null 2>&1; then
    # The OS package puts pipx itself on PATH, but apps it installs still go
    # to ~/.local/bin, which may not be -- same fix as the pip-install path.
    pipx ensurepath >/dev/null 2>&1 || true
    export PATH="$HOME/.local/bin:$PATH"
    NEEDS_NEW_SHELL=1
    return 0
  fi
  return 1
}

if ! install_pipx; then
  error "Could not install pipx automatically."
  echo "Please install it manually -- see https://pipx.pypa.io/stable/installation/ -- then re-run this script." >&2
  exit 1
fi

if ! command -v pipx >/dev/null 2>&1; then
  error "pipx was installed but isn't on your PATH yet in this terminal session."
  echo "Close and reopen your terminal (so the updated PATH takes effect), then run this script again." >&2
  exit 1
fi
info "Found pipx"

# Make sure pipx-installed apps end up on PATH. NEEDS_NEW_SHELL may already be
# set to 1 above if this script just bootstrapped pipx itself -- but pipx can
# just as easily have been pre-installed (via the OS, a previous manual
# install, etc.) with its bin dir still missing from PATH, which that earlier
# codepath never touches. So this check runs unconditionally, regardless of
# how pipx got here, and is what actually fixes the "command not found" this
# script would otherwise leave behind.
PIPX_BIN_DIR="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
case ":$PATH:" in
  *":$PIPX_BIN_DIR:"*) ;;
  *)
    pipx ensurepath >/dev/null 2>&1 || true
    export PATH="$PIPX_BIN_DIR:$PATH"
    NEEDS_NEW_SHELL=1
    ;;
esac

# --- 3. Download the source -------------------------------------------------

if command -v curl >/dev/null 2>&1; then
  FETCH() { curl -fsSL "$1"; }
elif command -v wget >/dev/null 2>&1; then
  FETCH() { wget -qO- "$1"; }
else
  error "Neither curl nor wget is available to download msg2eml."
  echo "Install one of them and re-run this script." >&2
  exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
  error "tar was not found, but is needed to unpack the download."
  exit 1
fi

info "Downloading msg2eml (branch: $BRANCH)..."
rm -rf "$SRC_DIR"
mkdir -p "$SRC_DIR"
FETCH "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" \
  | tar -xz -C "$SRC_DIR" --strip-components=1

# --- 4. Install with pipx ---------------------------------------------------

# If pipx picked a `uv` backend from something already on PATH that's too old
# for it, retry once with pipx's plain pip backend (always compatible, just
# a little slower) rather than failing outright. Older pipx versions don't
# have --backend at all, but they also won't hit this failure in the first
# place, so the plain retry only ever triggers on pipx versions that support it.
install_with_pipx() {
  local spec="$1"
  if pipx install --force "$spec"; then
    return 0
  fi
  info "Retrying with pipx's plain pip backend..."
  pipx install --force --backend pip "$spec"
}

if [ "$WITH_UI" = "1" ]; then
  info "Installing msg2eml, including the optional web interface..."
  install_with_pipx "${SRC_DIR}[ui]"
else
  info "Installing msg2eml..."
  install_with_pipx "$SRC_DIR"
fi

# --- 5. Desktop / Application shortcuts -------------------------------------
#
# Only makes sense when the web UI was actually installed -- there's no GUI
# to shortcut otherwise. Hardcodes the pipx bin dir's absolute path into
# Exec= / the launcher scripts rather than relying on PATH, because both
# XDG desktop launchers and double-clicked macOS .app bundles run with a
# minimal environment that doesn't include the interactive shell's PATH
# additions.

UI_BIN="${PIPX_BIN_DIR:-$HOME/.local/bin}/msg2eml-ui"
UNINSTALL_SH="$SRC_DIR/uninstall.sh"

create_linux_shortcuts() {
  local apps_dir="$HOME/.local/share/applications"
  mkdir -p "$apps_dir"

  cat >"$apps_dir/msg2eml.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Start msg2eml
Comment=Convert Outlook .msg files to .eml/.ics/.vcf
Exec=$UI_BIN
Terminal=false
Icon=mail-message-new
Categories=Utility;Office;
EOF

  cat >"$apps_dir/msg2eml-uninstall.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Uninstall msg2eml
Comment=Remove msg2eml and the shortcuts it created
Exec=bash -lc "'$UNINSTALL_SH'"
Terminal=true
Icon=edit-delete
Categories=Utility;Office;
EOF

  update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
}

create_macos_shortcuts() {
  local apps_dir="$HOME/Applications"
  mkdir -p "$apps_dir"

  rm -rf "$apps_dir/msg2eml.app"
  mkdir -p "$apps_dir/msg2eml.app/Contents/MacOS"
  cat >"$apps_dir/msg2eml.app/Contents/MacOS/msg2eml" <<EOF
#!/bin/bash
exec "$UI_BIN"
EOF
  chmod +x "$apps_dir/msg2eml.app/Contents/MacOS/msg2eml"
  cat >"$apps_dir/msg2eml.app/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>msg2eml</string>
  <key>CFBundleExecutable</key>
  <string>msg2eml</string>
  <key>CFBundleIdentifier</key>
  <string>com.ideotion.msg2eml</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
</dict>
</plist>
EOF

  rm -rf "$apps_dir/msg2eml-uninstall.app"
  mkdir -p "$apps_dir/msg2eml-uninstall.app/Contents/MacOS"
  cat >"$apps_dir/msg2eml-uninstall.app/Contents/MacOS/msg2eml-uninstall" <<EOF
#!/bin/bash
osascript -e 'tell application "Terminal" to do script "$UNINSTALL_SH"'
EOF
  chmod +x "$apps_dir/msg2eml-uninstall.app/Contents/MacOS/msg2eml-uninstall"
  cat >"$apps_dir/msg2eml-uninstall.app/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>msg2eml-uninstall</string>
  <key>CFBundleExecutable</key>
  <string>msg2eml-uninstall</string>
  <key>CFBundleIdentifier</key>
  <string>com.ideotion.msg2eml.uninstall</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
</dict>
</plist>
EOF
}

if [ "$WITH_UI" = "1" ] && [ "$SHORTCUTS" != "0" ]; then
  if [ "$(uname -s)" = "Linux" ]; then
    info "Creating desktop shortcuts..."
    create_linux_shortcuts || true
  elif [ "$(uname -s)" = "Darwin" ]; then
    info "Creating Application shortcuts in ~/Applications..."
    create_macos_shortcuts || true
  fi
fi

# --- 6. Launch the web UI ----------------------------------------------------

UI_URL="http://127.0.0.1:${PORT}/"
UI_LOG_FILE="$HOME/.local/share/msg2eml-ui.log"

open_browser_tab() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 &
  else
    python3 -c "import webbrowser,sys; webbrowser.open(sys.argv[1])" "$url" >/dev/null 2>&1 &
  fi
}

if [ "$WITH_UI" = "1" ] && [ "$AUTO_LAUNCH" != "0" ]; then
  if command -v curl >/dev/null 2>&1 && curl -fsS -o /dev/null --max-time 1 "$UI_URL" 2>/dev/null; then
    info "msg2eml web UI is already running -- opening $UI_URL in your browser..."
    open_browser_tab "$UI_URL" || true
  else
    info "Launching the msg2eml web UI in the background..."
    mkdir -p "$(dirname "$UI_LOG_FILE")"
    nohup msg2eml-ui --port "$PORT" >"$UI_LOG_FILE" 2>&1 &
    disown
    info "msg2eml web UI running at $UI_URL (log: $UI_LOG_FILE)"
  fi
fi

echo
if [ "$NEEDS_NEW_SHELL" = "1" ]; then
  info "Done! One more step: '$PIPX_BIN_DIR' was just added to your PATH,"
  echo "      but that only takes effect in *new* terminal windows/tabs."
  echo
  echo "      Close and reopen your terminal (or run 'exec \$SHELL -l'), then try:"
  echo "          msg2eml --help"
  echo "          msg2eml-ui        # opens the web interface in your browser"
else
  info "Done! Try one of:"
  echo "    msg2eml --help"
  echo "    msg2eml-ui        # opens the web interface in your browser"
fi
