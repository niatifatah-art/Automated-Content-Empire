#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
WORKSPACE="${1:-$(mktemp -d -t ace2-smoke-XXXXXX)}"

echo "ACE source: $ROOT"
echo "Workspace: $WORKSPACE"
python3 -m compileall -q "$ROOT/src"
python3 -m pytest -q "$ROOT/tests"
python3 -m ace.main --home "$WORKSPACE" test full --report

echo "Smoke test passed."
