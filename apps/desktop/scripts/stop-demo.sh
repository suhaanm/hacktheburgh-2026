#!/usr/bin/env bash
# Stop the demo started by scripts/start-demo.sh. Stops ONLY the PID in the PID file: graceful TERM, then KILL if it
# will not quit. Afterwards the demo profile is put back (what the app does itself on a clean quit, repeated here so
# a forced kill cannot leave the seeded profile.md in place).
set -u
PIDFILE="${DEMO_PID_FILE:-/tmp/alongside-demo.pid}"
USERDATA="${ALONGSIDE_USERDATA:-$HOME/.alongside-demo}"

if [ -s /tmp/alongside-electron.lock/owner ]; then
  LPID="$(sed -n 2p /tmp/alongside-electron.lock/owner)"
  if kill -0 "$LPID" 2>/dev/null; then echo "Note: an agent holds /tmp/alongside-electron.lock (role $(sed -n 1p /tmp/alongside-electron.lock/owner)); this script only stops the PID in $PIDFILE."; fi
fi

if [ ! -f "$PIDFILE" ]; then
  echo "No demo PID file ($PIDFILE): nothing to stop. If an app is still on screen it was not started by start-demo.sh; quit it from its menu bar item."
  exit 0
fi
PID="$(cat "$PIDFILE" 2>/dev/null)"
if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
  echo "The demo (PID ${PID:-?}) is not running any more."
  rm -f "$PIDFILE"
else
  kill -TERM "$PID" 2>/dev/null
  for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
  if kill -0 "$PID" 2>/dev/null; then
    echo "Still running after 10 s: forcing it to quit."
    kill -KILL "$PID" 2>/dev/null
    sleep 0.5
  fi
  rm -f "$PIDFILE"
  echo "Demo stopped (PID $PID)."
fi

# Put the learner's real profile back if a tour was cut off before it could.
if [ -f "$USERDATA/profile.md.showtime-backup" ]; then
  mv "$USERDATA/profile.md.showtime-backup" "$USERDATA/profile.md"
  rm -f "$USERDATA/profile.md.showtime-none"
  echo "Profile restored from the tour backup."
elif [ -f "$USERDATA/profile.md.showtime-none" ]; then
  rm -f "$USERDATA/profile.md" "$USERDATA/profile.md.showtime-none"
  echo "Tour profile removed (there was none before the tour)."
fi
rm -f "$USERDATA"/*.showtime-tmp 2>/dev/null
exit 0
