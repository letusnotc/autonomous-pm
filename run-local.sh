#!/usr/bin/env bash
# Run Autonomous PM locally without Docker (SQLite instead of Postgres).
# Works on macOS, Linux and Windows (Git Bash).
#
# First time:  bash scripts/setup-local.sh
# Start:       bash run-local.sh          – starts every service, logs in ./logs
# Stop:        bash run-local.sh stop
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
PORTS="3000 3001 3002 3003 3004 3005 3007"
mkdir -p logs

is_windows() { case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; *) return 1 ;; esac; }

if [ "$1" = "stop" ]; then
  if is_windows; then
    for pid in $(netstat -ano | grep -E ':300[0-7] .*LISTENING' | awk '{print $5}' | sort -u); do
      taskkill //F //T //PID "$pid" > /dev/null 2>&1 || true
    done
  else
    for port in $PORTS; do
      if command -v lsof > /dev/null; then
        pids=$(lsof -ti "tcp:$port" 2>/dev/null || true)
        [ -n "$pids" ] && kill $pids 2>/dev/null || true
      else
        fuser -k "$port/tcp" > /dev/null 2>&1 || true
      fi
    done
  fi
  rm -f logs/*.pid
  echo "stopped"; exit 0
fi

if is_windows; then
  PY="$ROOT/.venv/Scripts/python"
  export PYTHONPATH="$(cygpath -w "$ROOT/packages/llm-client");$(cygpath -w "$ROOT/packages/slack-client")"
else
  PY="$ROOT/.venv/bin/python"
  export PYTHONPATH="$ROOT/packages/llm-client:$ROOT/packages/slack-client"
fi
[ -x "$PY" ] || { echo "Python environment not found – run: bash scripts/setup-local.sh"; exit 1; }
[ -f .env ] || { echo "No .env file – run: cp .env.example .env  (then add an LLM API key)"; exit 1; }

# Load .env (LLM keys etc.); skip the Postgres/Mongo URLs – we use SQLite locally
set -a; source .env; set +a
unset DATABASE_URL MONGODB_URI
export DATABASE_BACKEND=sql
# 127.0.0.1 rather than localhost: on Windows, localhost tries IPv6 first and each
# refused attempt costs ~2s, while uvicorn listens on IPv4 only.
export TICKET_SERVICE_URL=http://127.0.0.1:3001
export PRIORITY_SERVICE_URL=http://127.0.0.1:3003
export STANDUP_SERVICE_URL=http://127.0.0.1:3004
export DEV_AGENT_SERVICE_URL=http://127.0.0.1:3007

start() {  # name dir cmd...
  local name=$1 dir=$2; shift 2
  (cd "$dir" && "$@" > "$ROOT/logs/$name.log" 2>&1 & echo $! > "$ROOT/logs/$name.pid")
  echo "started $name"
}

start ticket       services/ticket-service        env PORT=3001 DATABASE_URL="sqlite+aiosqlite:///./dev.db" "$PY" -m uvicorn src.main:app --port 3001
sleep 4
start priority     services/priority-service      "$PY" -m uvicorn src.main:app --port 3003
start standup      services/standup-service       "$PY" -m uvicorn src.main:app --port 3004
start github       services/github-status-service env PORT=3002 node src/index.js
start dev-agent    services/dev-agent-service     "$PY" -m uvicorn src.main:app --port 3007
sleep 4
start orchestrator services/orchestrator-service  "$PY" -m uvicorn src.main:app --port 3005
start dashboard    apps/web-dashboard             env PORT=3000 npx next dev -p 3000

echo "Dashboard: http://localhost:3000   Ticket API docs: http://localhost:3001/docs"
echo "Check health: bash scripts/health-check.sh   (the dashboard takes ~20s to compile the first time)"
