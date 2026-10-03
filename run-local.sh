#!/usr/bin/env bash
# Run Autonomous PM locally without Docker (SQLite instead of Postgres).
# Usage: bash run-local.sh        — starts backend services, logs in ./logs
#        bash run-local.sh stop   — stops them
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
mkdir -p logs

if [ "$1" = "stop" ]; then
  for pid in $(netstat -ano | grep -E ':300[0-7] .*LISTENING' | awk '{print $5}' | sort -u); do
    taskkill //F //T //PID "$pid" > /dev/null 2>&1 || true
  done
  rm -f logs/*.pid
  echo "stopped"; exit 0
fi

# Load .env (LLM keys etc.); skip the Postgres URL – we use SQLite locally
set -a; source .env; set +a
unset DATABASE_URL MONGODB_URI
export DATABASE_BACKEND=sql
export PYTHONPATH="$(cygpath -w "$ROOT/packages/llm-client");$(cygpath -w "$ROOT/packages/slack-client")"
# 127.0.0.1 rather than localhost: on Windows, localhost tries IPv6 first and each
# refused attempt costs ~2s, while uvicorn listens on IPv4 only.
export TICKET_SERVICE_URL=http://127.0.0.1:3001
export PRIORITY_SERVICE_URL=http://127.0.0.1:3003
export STANDUP_SERVICE_URL=http://127.0.0.1:3004
export DEV_AGENT_SERVICE_URL=http://127.0.0.1:3007
PY="$ROOT/.venv/Scripts/python"

start() {  # name dir port cmd...
  local name=$1 dir=$2; shift 2
  (cd "$dir" && "$@" > "$ROOT/logs/$name.log" 2>&1 & echo $! > "$ROOT/logs/$name.pid")
  echo "started $name"
}

start ticket       services/ticket-service       env PORT=3001 DATABASE_URL="sqlite+aiosqlite:///./dev.db" "$PY" -m uvicorn src.main:app --port 3001
sleep 4
start priority     services/priority-service     "$PY" -m uvicorn src.main:app --port 3003
start standup      services/standup-service      "$PY" -m uvicorn src.main:app --port 3004
start github       services/github-status-service env PORT=3002 node src/index.js
start dev-agent    services/dev-agent-service    "$PY" -m uvicorn src.main:app --port 3007
sleep 4
start orchestrator services/orchestrator-service "$PY" -m uvicorn src.main:app --port 3005
start dashboard    apps/web-dashboard            env PORT=3000 npx next dev -p 3000

echo "Dashboard: http://localhost:3000   Ticket API docs: http://localhost:3001/docs"
