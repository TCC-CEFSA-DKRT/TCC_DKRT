#!/usr/bin/env bash
# Launcher do terminal DKRT (Linux/macOS)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Crie o venv: python3 -m venv .venv && pip install -e ."
  exit 1
fi
exec "$PYTHON" -m context_broker_agent.terminal "$@"
