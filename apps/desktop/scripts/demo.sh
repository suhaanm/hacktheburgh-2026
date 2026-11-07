#!/usr/bin/env bash
# One-command demo launcher: stage server, demo seed (with backup), demo mode, preflight, then the app.
#
# Usage:  npm run demo [-- <flags>]
#   --keep-profile   do not touch profile.md (keep the learner state as it is)
#   --accurate       grounding preset "accurate" (flash only, slower); default is "accurate" or $ALONGSIDE_GROUNDING_PRESET
#   --force          launch even if preflight has red rows (you have been warned)
#   --no-app         do everything except start the app (used to test this script)
#
# Run it from the SAME terminal you will use on stage: macOS grants Microphone and Screen Recording to the app that
# launched Electron, and the preflight inside this script is only meaningful if it runs under that same launcher.
set -u
cd "$(dirname "$0")/.." || exit 1

USERDATA="${ALONGSIDE_USERDATA:-$HOME/.alongside-demo}"
STAGE_PORT="${STAGE_PORT:-5180}"
SEED="src/main/teaching/fixtures/demo-profile.md"
PRESET="${ALONGSIDE_GROUNDING_PRESET:-accurate}"
KEEP=0 FORCE=0 NOAPP=0
for arg in "$@"; do
  case "$arg" in
    --keep-profile) KEEP=1 ;;
    --accurate) PRESET=accurate ;;
    --fast) PRESET=fast ;;
    --force) FORCE=1 ;;
    --no-app) NOAPP=1 ;;
    *) echo "unknown flag: $arg (see the header of scripts/demo.sh)" >&2; exit 2 ;;
  esac
done

export ALONGSIDE_USERDATA="$USERDATA" ALONGSIDE_GROUNDING_PRESET="$PRESET"

say() { printf '\n== %s\n' "$1"; }
STAGE_PID=""
cleanup() { [ -n "$STAGE_PID" ] && kill "$STAGE_PID" 2>/dev/null; }
trap cleanup EXIT INT TERM

# 1. Practice desktop (stage server)
say "Practice desktop"
if curl -fsS -m 2 "http://127.0.0.1:$STAGE_PORT/" >/dev/null 2>&1; then
  echo "already running on http://127.0.0.1:$STAGE_PORT/"
else
  STAGE_PORT="$STAGE_PORT" nohup node scripts/stage-server.mjs >/tmp/alongside-stage.log 2>&1 &
  STAGE_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    curl -fsS -m 1 "http://127.0.0.1:$STAGE_PORT/" >/dev/null 2>&1 && break
    sleep 0.5
  done
  if curl -fsS -m 2 "http://127.0.0.1:$STAGE_PORT/" >/dev/null 2>&1; then
    echo "started on http://127.0.0.1:$STAGE_PORT/ (stops when this script ends; log: /tmp/alongside-stage.log)"
  else
    echo "could not start the stage server; see /tmp/alongside-stage.log" >&2
    STAGE_PID=""
  fi
fi

# 2. Demo seed profile and demo mode, in an isolated profile directory. Anything replaced is backed up first.
say "Demo profile ($USERDATA)"
mkdir -p "$USERDATA"
STAMP="$(date +%Y%m%d-%H%M%S)"
if [ "$KEEP" = 1 ]; then
  echo "--keep-profile: profile.md left as it is"
elif [ ! -f "$SEED" ]; then
  echo "seed file $SEED is missing; preflight will say so" >&2
else
  if [ -f "$USERDATA/profile.md" ] && ! cmp -s "$SEED" "$USERDATA/profile.md"; then
    cp "$USERDATA/profile.md" "$USERDATA/profile.md.bak-$STAMP"
    echo "existing profile.md differed from the seed; backed up to profile.md.bak-$STAMP"
  fi
  cp "$SEED" "$USERDATA/profile.md"
  echo "seed applied: Start a video call at L2 \"Walk with me\" (returning learner)"
fi
# demoMode is ON by default; make sure an old settings.json has not turned it off. Other settings are left alone.
if [ -f "$USERDATA/settings.json" ]; then
  node -e '
    const fs = require("fs"); const f = process.argv[1]; const stamp = process.argv[2];
    let s; try { s = JSON.parse(fs.readFileSync(f, "utf8")); } catch { process.exit(0); }
    if (s.demoMode === false) { fs.copyFileSync(f, f + ".bak-" + stamp); s.demoMode = true; fs.writeFileSync(f, JSON.stringify(s, null, 2)); console.log("demoMode was off in settings.json; switched on (backup: settings.json.bak-" + stamp + ")"); }
    else console.log("demoMode is on");
  ' "$USERDATA/settings.json" "$STAMP"
else
  echo "no settings.json yet: defaults apply (demoMode on)"
fi
echo "grounding preset: $PRESET"

# 3. Preflight (same terminal, same launcher)
say "Preflight"
node scripts/preflight.mjs
PRE=$?
if [ "$PRE" -ne 0 ] && [ "$FORCE" != 1 ]; then
  echo
  echo "Not launching: fix the FAIL rows above and run  npm run demo  again (or add  -- --force  to go anyway)." >&2
  exit 1
fi
[ "$PRE" -ne 0 ] && echo "--force: launching with red rows." >&2

# 4. What to press and what to say first
say "Cheat sheet"
HK="src/main/hotkey.ts"
pretty() { sed -E 's/CommandOrControl/Cmd/g; s/Escape/Esc/g'; }
START="$(grep -o "START_ACCELERATORS = \[[^]]*\]" "$HK" | grep -o "'[^']*'" | tr -d "'" | pretty | paste -sd ',' - | sed 's/,/, /g')"
STOP="$(grep -o "STOP_ACCELERATORS = \[[^]]*\]" "$HK" | grep -o "'[^']*'" | tr -d "'" | pretty | paste -sd ',' - | sed 's/,/, /g')"
echo "Start a session : $START   (first one that works on this laptop; write it on a sticky note)"
echo "Stop            : $STOP   or the big Stop button, or say \"goodbye\""
WAKE="$(grep -o "wakePhrases: \['[^']*'" src/shared/personas.ts | sed -E "s/.*\['//; s/'$//" | awk '{ printf "%s\"%s\"", (NR > 1 ? " / " : ""), $0 }')"
echo "Wake word       : $WAKE (placeholder names; the hotkey is the stage-safe path)"
echo "Practice desktop: open http://127.0.0.1:$STAGE_PORT/ in a clean window and press F for full screen; S delivers the staged scam text"
echo
echo "First three beats of docs/DEMO_SCRIPT.md:"
grep -E '^\| \*\*0:' docs/DEMO_SCRIPT.md | head -3 | awk -F'|' '{ gsub(/\*\*/, "", $2); gsub(/\*\*/, "", $4); gsub(/\*\*/, "", $5); say = substr($5, 2, 170); if (length($5) > 171) say = say "..."; printf "  %s  %s: %s\n", $2, $4, say }'

if [ "$NOAPP" = 1 ]; then
  echo
  echo "--no-app: stopping before the app starts."
  exit 0
fi

# 5. The app, in the foreground (Ctrl+C stops it and the stage server this script started)
say "Starting Alongside (Ctrl+C to quit)"
if [ "${ALONGSIDE_USE_LOCK:-0}" = 1 ]; then
  # Agents and tests only: one Electron at a time, auto-killed after ALONGSIDE_LOCK_MAX_SECONDS (see scripts/electron-lock.sh).
  bash scripts/electron-lock.sh DEMO npm run dev
else
  npm run dev
fi
