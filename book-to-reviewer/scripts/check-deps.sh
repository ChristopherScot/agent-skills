#!/bin/sh
set -u

usage() {
  cat <<'EOF'
Usage: check-deps.sh [epub|pdf|text|web|all]

Reports whether the tools book-to-reviewer needs for that source type are
installed, and prints the install command for this machine for any that are
missing. Installs nothing.

Exit codes: 0 everything required is present, 1 something required is missing,
2 bad arguments.
EOF
}

source_kind=${1:-all}
case "$source_kind" in
  -h|--help) usage; exit 0 ;;
  epub|pdf|text|web|all) ;;
  *)
    echo "Error: source type must be one of: epub, pdf, text, web, all." >&2
    usage >&2
    exit 2
    ;;
esac

has() {
  command -v "$1" >/dev/null 2>&1
}

install_command() {
  brew_package=$1
  linux_package=$2
  if has brew; then
    echo "brew install $brew_package"
  elif has apt-get; then
    echo "sudo apt-get install -y $linux_package"
  elif has dnf; then
    echo "sudo dnf install -y $linux_package"
  elif has pacman; then
    echo "sudo pacman -S --noconfirm $brew_package"
  elif has winget; then
    echo "install '$brew_package' with winget, scoop or choco"
  else
    echo "install '$brew_package' with your system package manager"
  fi
}

missing_required=0

require() {
  tool=$1
  hint=$2
  if has "$tool"; then
    echo "ok        $tool"
  else
    echo "MISSING   $tool    install: $hint"
    missing_required=1
  fi
}

require python3 "$(install_command python python3)"

if [ "$source_kind" = pdf ] || [ "$source_kind" = all ]; then
  poppler_hint=$(install_command poppler poppler-utils)
  require pdftotext "$poppler_hint"
  require pdfimages "$poppler_hint"
fi

if [ "$source_kind" = epub ] || [ "$source_kind" = all ]; then
  if has textutil; then
    echo "ok        textutil"
  else
    echo "optional  textutil    macOS only, nothing to install; EPUB text uses the built-in HTML fallback"
  fi
fi

if [ "$missing_required" -ne 0 ]; then
  echo
  echo "Required tools are missing. Show the user the install command and ask before running it."
  exit 1
fi
