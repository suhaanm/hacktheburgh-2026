#!/bin/bash
# Run a heavy command only when a machine-wide slot is free. FIFO per lane so short jobs cannot starve.
# usage: scripts/heavy.sh <command> [args...]
#   lane "long" (default): UNDERSTUDY_HEAVY_SLOTS (default 3) slots, for big suites, evaluations, bake-offs.
#   lane "short": UNDERSTUDY_HEAVY_SHORT=1, UNDERSTUDY_HEAVY_SHORT_SLOTS (default 2) extra slots, for jobs under about 3 minutes of work.
# Works on macOS bash 3.2. Stale slots and tickets (owner process gone) are reclaimed. Polls every 3 s, prints one line per minute.
N="${UNDERSTUDY_HEAVY_SLOTS:-3}"
S="${UNDERSTUDY_HEAVY_SHORT_SLOTS:-2}"
DIR="${TMPDIR:-/tmp}/understudy-heavy-slots"
mkdir -p "$DIR" "$DIR/tickets"
lane=long; prefix=slot; limit="$N"
if [ "${UNDERSTUDY_HEAVY_SHORT:-0}" = "1" ]; then lane=short; prefix=short; limit="$S"; fi
now="$(perl -MTime::HiRes=time -e 'printf "%017.6f", time' 2>/dev/null || date +%s)"
ticket="$DIR/tickets/${lane}-${now}-$$"
echo $$ > "$ticket"
slot=""
cleanup() { rm -f "$ticket"; [ -n "$slot" ] && rm -rf "$slot"; }
trap cleanup EXIT INT TERM HUP
waited=0
while true; do
  # drop stale tickets of this lane
  for t in "$DIR"/tickets/${lane}-*; do
    [ -f "$t" ] || continue
    tp="$(cat "$t" 2>/dev/null)"
    if [ -n "$tp" ] && ! kill -0 "$tp" 2>/dev/null; then rm -f "$t"; fi
  done
  oldest="$(ls "$DIR"/tickets/${lane}-* 2>/dev/null | sort | head -1)"
  if [ "$oldest" = "$ticket" ]; then
    i=1
    while [ "$i" -le "$limit" ]; do
      d="$DIR/${prefix}${i}"
      if [ -d "$d" ] && [ -f "$d/pid" ]; then
        p="$(cat "$d/pid" 2>/dev/null)"
        if [ -n "$p" ] && ! kill -0 "$p" 2>/dev/null; then rm -rf "$d"; fi
      fi
      if mkdir "$d" 2>/dev/null; then
        echo $$ > "$d/pid"
        slot="$d"
        rm -f "$ticket"
        "$@"
        rc=$?
        exit $rc
      fi
      i=$((i + 1))
    done
  fi
  waited=$((waited + 3))
  if [ $((waited % 60)) -eq 0 ]; then echo "heavy.sh[$lane]: waiting (${waited}s; load $(uptime | sed 's/.*averages*: //'))" >&2; fi
  sleep 3
done
