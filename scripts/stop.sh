#!/usr/bin/env bash
# Stops the services started by scripts/dev.sh (only the PIDs it recorded) and their children.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
shopt -s nullglob
for f in data/pids/*.pid; do
  name="$(basename "$f" .pid)"; pid="$(cat "$f")"
  if kill -0 "$pid" 2>/dev/null; then
    pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null && echo "  [stop] $name (pid $pid)"
  else echo "  [gone] $name"; fi
  rm -f "$f"
done
echo "done"
