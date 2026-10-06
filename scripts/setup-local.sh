#!/usr/bin/env bash
# One-time setup for running Autonomous PM without Docker:
# a Python virtualenv with every service's dependencies, Node packages, and .env.
# Works on macOS, Linux and Windows (Git Bash). Needs Python 3.11/3.12, Node 18+ and git.
set -e
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3.12 python3.11 python3 python; do
    if command -v "$candidate" > /dev/null; then PYTHON="$candidate"; break; fi
  done
fi
[ -n "$PYTHON" ] || { echo "Python 3.11+ not found"; exit 1; }
echo "== Using $($PYTHON --version 2>&1)"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) VPY=.venv/Scripts/python ;;
  *)                    VPY=.venv/bin/python ;;
esac

echo "== Python virtualenv (.venv)"
[ -x "$VPY" ] || "$PYTHON" -m venv .venv
"$VPY" -m pip install -q --upgrade pip
# All Python services share one environment; their pinned requirements are compatible.
cat services/ticket-service/requirements.txt services/priority-service/requirements.txt \
    services/standup-service/requirements.txt services/orchestrator-service/requirements.txt \
    services/dev-agent-service/requirements.txt | grep -vE '^[[:space:]]*(#|$)' | sort -u > .venv/requirements-all.txt
"$VPY" -m pip install -q -r .venv/requirements-all.txt

echo "== Node packages"
for dir in apps/web-dashboard services/github-status-service services/slack-intake-service; do
  echo "   $dir"
  (cd "$dir" && npm install --no-audit --no-fund --loglevel=error)
done

if [ ! -f .env ]; then
  cp .env.example .env
  echo "== Created .env from .env.example – add an LLM API key (GEMINI_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY)"
fi

echo
echo "Setup complete. Start everything with:  bash run-local.sh"
