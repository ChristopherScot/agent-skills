#!/bin/sh
set -u

usage() {
  cat <<'EOF'
Usage: check-deps.sh [build|check|all]

Reports whether the tools drilldown-diagrams needs are installed, and prints
the install command for this machine for any that are missing. Installs
nothing.

  build  building a diagram: Node 18+ and Graphviz (dot)
  check  also running check.mjs: npm, to set up Playwright and Chromium
  all    both (default)

Exit codes: 0 everything required is present, 1 something required is missing,
2 bad arguments.
EOF
}

purpose=${1:-all}
case "$purpose" in
  -h|--help) usage; exit 0 ;;
  build|check|all) ;;
  *)
    echo "Error: purpose must be one of: build, check, all." >&2
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

report_missing() {
  echo "MISSING   $1    install: $2"
  missing_required=1
}

if has node; then
  node_major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
  if [ "$node_major" -ge 18 ]; then
    echo "ok        node $(node --version)"
  else
    report_missing "node 18+ (found $(node --version))" "$(install_command node nodejs)"
  fi
else
  report_missing node "$(install_command node nodejs)"
fi

if has dot; then
  echo "ok        dot ($(dot -V 2>&1 | head -1))"
else
  report_missing dot "$(install_command graphviz graphviz)"
fi

if [ "$purpose" = check ] || [ "$purpose" = all ]; then
  if has npm; then
    echo "ok        npm"
  else
    report_missing npm "$(install_command node npm)"
  fi
  echo "note      check.mjs also needs @playwright/test and Chromium in the directory it runs from;"
  echo "          set up once with: npm init -y && npm i -D @playwright/test && npx playwright install chromium"
fi

if [ "$missing_required" -ne 0 ]; then
  echo
  echo "Required tools are missing. Show the user the install command and ask before running it."
  exit 1
fi
