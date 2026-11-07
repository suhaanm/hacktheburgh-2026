#!/usr/bin/env bash
# Starts the Understudy services in the background. Skips services that are not built yet and ports already in use.
# Logs: data/logs/<name>.log   PIDs: data/pids/<name>.pid   Stop with scripts/stop.sh
# Never prints secrets: services load .env themselves.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data/logs data/pids

ENGINE_PORT="${ENGINE_PORT:-7700}"; AGENT_PORT="${AGENT_PORT:-7710}"; DASHBOARD_PORT="${DASHBOARD_PORT:-5173}"
PRE_MOCK="${UNDERSTUDY_MOCK-}"   # a value given on the command line wins over .env
if [[ -f .env ]]; then set -a; source .env; set +a; fi
[[ -n "$PRE_MOCK" ]] && export UNDERSTUDY_MOCK="$PRE_MOCK"
ENGINE_PORT="${ENGINE_PORT:-7700}"; AGENT_PORT="${AGENT_PORT:-7710}"; DASHBOARD_PORT="${DASHBOARD_PORT:-5173}"

busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
start() { # name port cmd...
  local name="$1" port="$2"; shift 2
  if busy "$port"; then echo "  [skip] $name: port $port already in use"; return; fi
  nohup "$@" > "data/logs/$name.log" 2>&1 &
  echo $! > "data/pids/$name.pid"
  echo "  [start] $name on :$port (pid $!, log data/logs/$name.log)"
}

echo "Understudy dev (UNDERSTUDY_MOCK=${UNDERSTUDY_MOCK:-0})"
if [[ ! -d data/synthetic ]]; then
  echo "  [synth] generating synthetic data (about 10 s)"
  uv run --package understudy-engine understudy synth --all > data/logs/synth.log 2>&1 || echo "  [warn] synth failed, see data/logs/synth.log"
fi

# Run the engine in the agent environment (a superset) so it can import the agent's queue, audit and kill-flag helpers.
start engine "$ENGINE_PORT" uv run --package understudy-agent understudy serve

if [[ -f services/agent/understudy_agent/sandbox_sites/__main__.py ]]; then
  start sites "${SANDBOX_PORT_BASE:-7801}" uv run --package understudy-agent python -m understudy_agent.sandbox_sites
else echo "  [skip] sandbox sites: not built yet"; fi

if [[ -f services/agent/understudy_agent/server.py ]]; then
  start agent "$AGENT_PORT" uv run --package understudy-agent python -m understudy_agent.server
else echo "  [skip] agent service: server.py not built yet"; fi

if [[ -f apps/dashboard/package.json ]]; then
  start dashboard "$DASHBOARD_PORT" bash -c "cd apps/dashboard && exec npm run dev -- --host 127.0.0.1 --port $DASHBOARD_PORT"
else echo "  [skip] dashboard: not built yet"; fi

sleep 3
echo
echo "Dashboard: http://127.0.0.1:$DASHBOARD_PORT   Engine: http://127.0.0.1:$ENGINE_PORT/health   Agent: http://127.0.0.1:$AGENT_PORT/health"
[[ "${1:-}" == "--open" ]] && open "http://127.0.0.1:$DASHBOARD_PORT" 2>/dev/null || true
