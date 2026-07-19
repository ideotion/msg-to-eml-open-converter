#!/usr/bin/env bash
# msg2eml installer: downloads the project source and installs the
# `msg2eml` (and `msg2eml-ui`) commands with pipx.
#
# Usage (paste this whole line into a terminal):
#
#   curl -fsSL https://raw.githubusercontent.com/ideotion/msg-to-eml-open-converter/main/install.sh | bash
#
# Options (set as environment variables before running):
#   MSG2EML_WITH_UI=0   Skip installing the optional web interface (Flask).
#   MSG2EML_BRANCH=main Install from a different branch/tag.
#   MSG2EML_SRC_DIR=... Where to download the source (default: ~/.local/share/msg2eml-src).
#
# Safe to re-run: it always reinstalls cleanly rather than leaving stale state.

set -euo pipefail

REPO="ideotion/msg-to-eml-open-converter"
BRANCH="${MSG2EML_BRANCH:-main}"
WITH_UI="${MSG2EML_WITH_UI:-1}"
SRC_DIR="${MSG2EML_SRC_DIR:-$HOME/.local/share/msg2eml-src}"

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

echo
info "Done! Try one of:"
echo "    msg2eml --help"
echo "    msg2eml-ui        # opens the web interface in your browser"

if [ "$NEEDS_NEW_SHELL" = "1" ]; then
  echo
  info "Note: pipx was just installed for the first time. If the 'msg2eml' command"
  echo "      isn't found above, close and reopen your terminal and try again."
fi
