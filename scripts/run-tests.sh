#!/usr/bin/env bash
# Run every automated test suite. Uses the project venv when present.
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="$ROOT/.venv/Scripts/python"; [ -x "$PY" ] || PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python
FAILED=()

run() {  # name dir cmd...
  local name=$1 dir=$2; shift 2
  echo "=== $name"
  if (cd "$dir" && "$@"); then echo; else FAILED+=("$name"); echo; fi
}

run "Ticket Service"    services/ticket-service       "$PY" -m pytest -q
run "Dev Agent Service" services/dev-agent-service    "$PY" -m pytest -q
run "LLM client"        packages/llm-client           "$PY" -m pytest -q
run "Slack Intake"      services/slack-intake-service npx jest
run "GitHub Status"     services/github-status-service npx jest

if [ ${#FAILED[@]} -eq 0 ]; then
  echo "All test suites passed ✓"
else
  echo "Failed: ${FAILED[*]}"; exit 1
fi
