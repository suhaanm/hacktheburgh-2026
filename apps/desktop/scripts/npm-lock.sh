#!/usr/bin/env bash
# Usage: scripts/npm-lock.sh <cmd...>   (e.g. scripts/npm-lock.sh npm install zod)
# Serialises npm installs across agents. Waits up to ALONGSIDE_NPM_WAIT seconds (default 300) for the lock;
# a lock held by a dead PID is taken over.
set -u
LOCK=/tmp/alongside-npm.lock
WAIT=${ALONGSIDE_NPM_WAIT:-300}

if [ $# -lt 1 ]; then
  echo "usage: $0 <cmd...>" >&2
  exit 2
fi

owner_alive() {
  local pid
  pid=$(sed -n 1p "$LOCK/owner" 2>/dev/null || true)
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

waited=0
while true; do
  if mkdir "$LOCK" 2>/dev/null; then
    echo "$$" > "$LOCK/owner"
    break
  fi
  if [ ! -s "$LOCK/owner" ]; then sleep 0.3; fi
  if [ -s "$LOCK/owner" ] && ! owner_alive; then
    echo "[npm-lock] removing stale lock" >&2
    rm -rf "$LOCK"
    continue
  fi
  if [ "$waited" -ge "$WAIT" ]; then
    echo "[npm-lock] still held by pid $(sed -n 1p "$LOCK/owner" 2>/dev/null) after ${WAIT}s" >&2
    exit 75
  fi
  sleep 2
  waited=$((waited + 2))
done

trap 'rm -rf "$LOCK"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$@"
