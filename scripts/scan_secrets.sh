#!/usr/bin/env bash
# Local secret scan (Spec v17.3.28). CI runs the same via gitleaks-action.
# Install: https://github.com/gitleaks/gitleaks#installing
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed. See https://github.com/gitleaks/gitleaks#installing"
  exit 1
fi
gitleaks detect --source . --config .gitleaks.toml --verbose
