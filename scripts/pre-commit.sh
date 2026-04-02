#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
  PYTHON="$ROOT_DIR/.venv/Scripts/python.exe"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="python"
fi

cmd="${1:-run}"

case "$cmd" in
  install)
    "$PYTHON" -m pre_commit install
    ;;
  run)
    shift || true
    if [[ "$#" -eq 0 ]]; then
      "$PYTHON" -m pre_commit run --all-files
    else
      "$PYTHON" -m pre_commit run "$@"
    fi
    ;;
  version)
    "$PYTHON" -m pre_commit --version
    ;;
  *)
    echo "Usage: ./pc [install|run|version] [extra pre-commit args]"
    exit 1
    ;;
esac
