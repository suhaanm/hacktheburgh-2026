#!/bin/bash
# Run a heavy command (a large test suite, tsc over the whole app, an evaluation) only when one of N machine-wide slots is free.
# usage: scripts/heavy.sh <command> [args...]      N defaults to 3 (UNDERSTUDY_HEAVY_SLOTS). Works on macOS bash 3.2.
# Stale slots (their owner process is gone) are reclaimed. Waiting is polite: it polls every 5 s and prints one line per minute.
N="${UNDERSTUDY_HEAVY_SLOTS:-3}"
DIR="${TMPDIR:-/tmp}/understudy-heavy-slots"
mkdir -p "$DIR"
waited=0
while true; do
  i=1
  while [ "$i" -le "$N" ]; do
    d="$DIR/slot$i"
    if [ -d "$d" ] && [ -f "$d/pid" ]; then
      p="$(cat "$d/pid" 2>/dev/null)"
      if [ -n "$p" ] && ! kill -0 "$p" 2>/dev/null; then rm -rf "$d"; fi
    fi
    if mkdir "$d" 2>/dev/null; then
      echo $$ > "$d/pid"
      trap 'rm -rf "$d"' EXIT INT TERM HUP
      "$@"
      rc=$?
      exit $rc
    fi
    i=$((i + 1))
  done
  waited=$((waited + 5))
  if [ $((waited % 60)) -eq 0 ]; then echo "heavy.sh: waiting for a free slot (${waited}s, ${N} slots, load $(uptime | sed 's/.*averages*: //'))" >&2; fi
  sleep 5
done
