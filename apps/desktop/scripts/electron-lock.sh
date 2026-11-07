#!/usr/bin/env bash
# Usage: scripts/electron-lock.sh <role> <cmd...>
# One Electron instance at a time across all agents. Refuses if the lock is held by a live PID
# (queues first-come-first-served; ALONGSIDE_LOCK_WAIT=<seconds>, default 600, bounds the wait). Kills the command (whole process group)
# after ALONGSIDE_LOCK_MAX_SECONDS (default 300) and exits 124.
set -u
# Agent/test runs only: the (unauthenticated) debug HTTP server is opt-in via ALONGSIDE_DEBUG=1 (see src/main/index.ts).
export ALONGSIDE_DEBUG=1
LOCK=/tmp/alongside-electron.lock
MAX=${ALONGSIDE_LOCK_MAX_SECONDS:-300}
WAIT=${ALONGSIDE_LOCK_WAIT:-600}

if [ $# -lt 2 ]; then
  echo "usage: $0 <role> <cmd...>" >&2
  exit 2
fi
ROLE=$1
shift

owner_alive() {
  local pid
  pid=$(sed -n 2p "$LOCK/owner" 2>/dev/null || true)
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# FIFO queue: every caller takes a numbered ticket and only the oldest live ticket may take the lock, so concurrent
# agents (and the orchestrators) run one after another instead of racing or giving up. Waiting is the default.
QUEUE=/tmp/alongside-electron-queue
mkdir -p "$QUEUE"
TICKET="$QUEUE/$(python3 -I -c 'import time;print(int(time.time()*1e9))')-$$-$ROLE"
: > "$TICKET"
trap 'rm -f "$TICKET"' EXIT

my_turn() {
  local t pid first=""
  for t in $(ls "$QUEUE" 2>/dev/null | sort); do
    pid=$(echo "$t" | cut -d- -f2)
    if kill -0 "$pid" 2>/dev/null; then first=$t; break; else rm -f "$QUEUE/$t"; fi
  done
  [ "$first" = "$(basename "$TICKET")" ]
}

queue_position() {
  local n=0 t
  for t in $(ls "$QUEUE" 2>/dev/null | sort); do
    n=$((n + 1))
    [ "$t" = "$(basename "$TICKET")" ] && { echo "$n"; return; }
  done
  echo "?"
}

acquire() {
  local waited=0
  while true; do
    if my_turn && mkdir "$LOCK" 2>/dev/null; then
      printf '%s\n%s\n' "$ROLE" "$$" > "$LOCK/owner"
      rm -f "$TICKET"
      return 0
    fi
    # The owner file is written right after mkdir; give a racing holder a moment before judging.
    if [ -d "$LOCK" ] && [ ! -s "$LOCK/owner" ]; then sleep 0.3; fi
    if [ -s "$LOCK/owner" ] && ! owner_alive; then
      echo "[electron-lock] removing stale lock (role $(sed -n 1p "$LOCK/owner"), dead pid $(sed -n 2p "$LOCK/owner"))" >&2
      rm -rf "$LOCK"
      continue
    fi
    if [ "$waited" -ge "$WAIT" ]; then
      echo "[electron-lock] gave up after ${WAIT}s in the queue (held by role $(sed -n 1p "$LOCK/owner" 2>/dev/null))" >&2
      rm -f "$TICKET"
      return 1
    fi
    if [ $((waited % 20)) -eq 0 ]; then
      echo "[electron-lock] $ROLE queued, position $(queue_position), current holder: $(sed -n 1p "$LOCK/owner" 2>/dev/null || echo none)" >&2
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

acquire || exit 75

CHILD=""
KILLER=""
cleanup() {
  trap - EXIT INT TERM
  if [ -n "$KILLER" ]; then
    local kids
    kids=$(pgrep -P "$KILLER" 2>/dev/null || true)
    kill "$KILLER" 2>/dev/null || true
    [ -n "$kids" ] && kill $kids 2>/dev/null || true
    wait "$KILLER" 2>/dev/null || true
  fi
  if [ -n "$CHILD" ] && kill -0 "$CHILD" 2>/dev/null; then
    kill -TERM -- "-$CHILD" 2>/dev/null || kill -TERM "$CHILD" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$CHILD" 2>/dev/null || true
  fi
  rm -rf "$LOCK"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Own process group so the whole Electron tree can be killed together (macOS has no `timeout`).
perl -e 'setpgrp(0, 0); exec @ARGV or die "exec failed: $!"' -- "$@" &
CHILD=$!

(
  sleep "$MAX"
  echo "[electron-lock] ${MAX}s limit reached, killing role $ROLE command" >&2
  touch "$LOCK/timed-out" 2>/dev/null
  kill -TERM -- "-$CHILD" 2>/dev/null
  sleep 2
  kill -KILL -- "-$CHILD" 2>/dev/null
) &
KILLER=$!

wait "$CHILD"
STATUS=$?
if [ -e "$LOCK/timed-out" ]; then STATUS=124; fi
exit "$STATUS"
