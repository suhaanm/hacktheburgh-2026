#!/usr/bin/env bash
# Start the Showtime demo: the guided tour on the built-in practice desktop. One command, no flags needed.
#
#   bash scripts/start-demo.sh [--full] [--live] [--mute] [--debug] [--dry-run] [--real]     (also: npm run showtime)
#   --full     the extended tour (about 4.5 minutes)       --live   live-model chapters (scam check, file search)
#   --mute     captions only, no narration audio            --debug  open the local debug HTTP port 7777 (off by default)
#   --dry-run  seed the profile and print what would run, but do not launch
#   --interactive  no autopilot tour: the practice desktop opens fullscreen in front and you talk to the live assistant
#              (script: docs/DEMO_SCRIPT_INTERACTIVE.md; also: npm run demo:interactive). Re-running re-seeds the profile.
#   --real     no practice desktop and no tour: the assistant runs over your real Mac screen (demo profile seeded)
#
# Stop it with:  bash scripts/stop-demo.sh   (or Esc, or the Stop button in the panel).
# Env overrides (tests): ALONGSIDE_USERDATA (default ~/.alongside-demo), DEMO_PID_FILE (default /tmp/alongside-demo.pid),
# ALONGSIDE_USE_LOCK=1 (agents only: run Electron through scripts/electron-lock.sh).
set -u
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"

USERDATA="${ALONGSIDE_USERDATA:-$HOME/.alongside-demo}"
PIDFILE="${DEMO_PID_FILE:-/tmp/alongside-demo.pid}"
FULL=0 LIVE=0 MUTE=0 DEBUG=0 DRY=0 INTERACTIVE=0 REAL=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --live) LIVE=1 ;;
    --mute) MUTE=1 ;;
    --debug) DEBUG=1 ;;
    --dry-run) DRY=1 ;;
    --interactive) INTERACTIVE=1 ;;
    --real) REAL=1 ;;
    *) echo "unknown flag: $arg (see the header of scripts/start-demo.sh)" >&2; exit 2 ;;
  esac
done

# 1. Refuse to start a second copy.
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null)"
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "The demo is already running (PID $OLD). Stop it first:  bash scripts/stop-demo.sh" >&2
    exit 1
  fi
  rm -f "$PIDFILE"
fi
OTHER="$(pgrep -fl "Alongside.app|[Ee]lectron .*deepmind-hackathon|Electron\.app/Contents/MacOS/Electron .*deepmind" 2>/dev/null | grep -v "^$$ " | head -3)"
if [ -n "$OTHER" ] && [ "$DRY" != 1 ]; then
  echo "Another Alongside / Electron instance seems to be running:" >&2
  echo "$OTHER" | cut -c1-140 >&2
  echo "Quit it first (menu bar item, Quit; or  bash scripts/stop-demo.sh  if it was started by this script)." >&2
  exit 1
fi
if [ -s /tmp/alongside-electron.lock/owner ]; then
  LPID="$(sed -n 2p /tmp/alongside-electron.lock/owner)"
  if kill -0 "$LPID" 2>/dev/null; then echo "Note: an agent holds /tmp/alongside-electron.lock (role $(sed -n 1p /tmp/alongside-electron.lock/owner)); its Electron window may be on screen."; fi
fi

# 2. Build only if out/ is older than src/ (or missing).
if [ ! -f out/main/index.js ] || [ -n "$(find src assets/showtime apps/demo-stage -type f -newer out/main/index.js 2>/dev/null | head -1)" ]; then
  echo "Building (out/ is older than the sources)..."
  npm run build >/tmp/alongside-demo-build.log 2>&1 || { echo "Build failed; see /tmp/alongside-demo-build.log" >&2; exit 1; }
fi

# 3. Seed the dedicated profile: settings for the tour. Other keys are kept; keys the tour flips are reset so a tour
#    that was killed half way cannot leave the look changed. The demo profile.md is handled by the app itself.
mkdir -p "$USERDATA"
node -e '
  const fs = require("fs"); const path = require("path");
  const f = path.join(process.argv[1], "settings.json");
  let s = {}; try { s = JSON.parse(fs.readFileSync(f, "utf8")); } catch {}
  for (const k of ["glass", "glassOpacity", "dyslexiaFont", "textScale", "theme", "highContrast", "textOnly"]) delete s[k];
  Object.assign(s, { onboardingDone: true, agency: "ask_per_task", doItForMeAllowed: true, persona: "marcus", demoMode: true, captions: true, showDock: process.argv[2] !== "false", confirmStyle: "toast" });
  fs.writeFileSync(f, JSON.stringify(s, null, 2));
' "$USERDATA" "${DEMO_SHOW_DOCK:-true}"
if [ "$INTERACTIVE" = 1 ] || [ "$REAL" = 1 ]; then
  # No tour to swap the demo profile in: seed it here (returning learner, video call at level 2). A different profile is backed up first.
  SEED="$REPO/src/main/teaching/fixtures/demo-profile.md"
  if [ -f "$USERDATA/profile.md" ] && ! cmp -s "$SEED" "$USERDATA/profile.md"; then cp "$USERDATA/profile.md" "$USERDATA/profile.md.bak-$(date +%Y%m%d-%H%M%S)"; fi
  cp "$SEED" "$USERDATA/profile.md"
fi
# A profile left behind by a crashed tour is put back by the app on launch; do the same here so the file is right first.
if [ -f "$USERDATA/profile.md.showtime-backup" ]; then mv "$USERDATA/profile.md.showtime-backup" "$USERDATA/profile.md"; rm -f "$USERDATA/profile.md.showtime-none"; fi
if [ -f "$USERDATA/profile.md.showtime-none" ]; then rm -f "$USERDATA/profile.md" "$USERDATA/profile.md.showtime-none"; fi

# 4. Launch.
export ALONGSIDE_USERDATA="$USERDATA" ALONGSIDE_OVERLAY_CAPTURABLE=1
if [ "$REAL" = 1 ]; then unset ALONGSIDE_STAGE_ONLY ALONGSIDE_DEMO_DIRECTOR ALONGSIDE_SHOWTIME_AUTOSTART; export ALONGSIDE_DEMO_AUTO=1 ALONGSIDE_BROWSER_APP="${ALONGSIDE_BROWSER_APP:-Safari}"
elif [ "$INTERACTIVE" = 1 ]; then export ALONGSIDE_STAGE_ONLY=1 ALONGSIDE_DEMO_DIRECTOR=1; unset ALONGSIDE_SHOWTIME_AUTOSTART; else export ALONGSIDE_SHOWTIME_AUTOSTART=1; unset ALONGSIDE_STAGE_ONLY ALONGSIDE_DEMO_DIRECTOR; fi
[ "$FULL" = 1 ] && export ALONGSIDE_SHOWTIME_FULL=1
[ "$LIVE" = 1 ] && export ALONGSIDE_SHOWTIME_MODE=live
[ "$MUTE" = 1 ] && export ALONGSIDE_SHOWTIME_MUTE=1
if [ "$DEBUG" = 1 ]; then export ALONGSIDE_DEBUG=1; else unset ALONGSIDE_DEBUG; fi
BIN="$REPO/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
[ -x "$BIN" ] || { echo "Electron is not installed (run npm install)." >&2; exit 1; }
MODE="scripted$([ "$FULL" = 1 ] && echo ', full')$([ "$LIVE" = 1 ] && echo ', live')$([ "$MUTE" = 1 ] && echo ', captions only')"
if [ "$DRY" = 1 ]; then
  echo "dry run: would launch $BIN . with profile $USERDATA (tour: $MODE, debug port: $([ "$DEBUG" = 1 ] && echo on || echo off))"
  exit 0
fi
LOG="${DEMO_LOG_FILE:-/tmp/alongside-demo.log}"
if [ "${ALONGSIDE_USE_LOCK:-0}" = 1 ]; then
  nohup bash scripts/electron-lock.sh "${ALONGSIDE_LOCK_ROLE:-DEMO}" "$BIN" "$REPO" >"$LOG" 2>&1 &
else
  nohup "$BIN" "$REPO" >"$LOG" 2>&1 &
fi
PID=$!
echo "$PID" >"$PIDFILE"
sleep 1
if ! kill -0 "$PID" 2>/dev/null; then
  echo "The app exited right away; see $LOG" >&2
  rm -f "$PIDFILE"
  exit 1
fi
if [ "$REAL" = 1 ]; then
  echo "Real-desktop mode starting (PID $PID): no practice desktop, the assistant works over your actual screen. Say \"Hey Marcus\" or press Cmd+Alt+Space; Cmd+Alt+M stops a session. Stop everything: bash scripts/stop-demo.sh"
elif [ "$INTERACTIVE" = 1 ]; then
  echo "Interactive demo starting (PID $PID). The practice desktop opens fullscreen in about 3 seconds. Say \"Hey Marcus\" or press Cmd+Alt+Space; Cmd+Alt+M stops a session."
  echo "Guaranteed beats (Option+Command+N): 1 greet, 2 video call, 3 scam check, 4 Settings, 5 progress, 6 Amelia goodbye. The session opens by itself and reopens if it drops."
  echo "Keys on the practice desktop: S scam text, G genuine text, Shift+R reset, F fullscreen. Stop everything: bash scripts/stop-demo.sh"
else
  echo "Demo starting (PID $PID, tour: $MODE). The practice desktop opens in about 3 seconds and the tour starts by itself. Space pauses, arrows move, Esc stops; or run: bash scripts/stop-demo.sh"
fi
