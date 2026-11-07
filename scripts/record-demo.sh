#!/usr/bin/env bash
# Screen recording for the launch, demo and submission video. OWNER-INITIATED ONLY: the lead runs this when the owner says "begin the demo"
# and stops it when the owner says stop. It records the MAIN DISPLAY to a movie file in ~/Movies/Knack-demo/, never inside the repo; no agent,
# model or Knack component reads, uploads or sends the file (the product's own rule that screen frames are never written to disk or sent
# concerns the product pipeline, not the owner's own video, and is unchanged).
#
#   scripts/record-demo.sh start [--audio]   begin recording (macOS asks for Screen Recording the first time; --audio adds the default input)
#   scripts/record-demo.sh stop              finish the movie and print its path and size
#   scripts/record-demo.sh status            is a recording running, and how big is the file
#
# Before recording: close other apps and windows you do not want in the video, turn Do Not Disturb on, hide the Dock if you like.
set -uo pipefail
DIR="${KNACK_DEMO_DIR:-$HOME/Movies/Knack-demo}"
PIDF="$DIR/.recording.pid"
mkdir -p "$DIR"

running() { [[ -f "$PIDF" ]] && kill -0 "$(cut -d' ' -f1 "$PIDF")" 2>/dev/null; }

case "${1:-}" in
  start)
    if running; then echo "already recording: $(cut -d' ' -f2- "$PIDF")"; exit 1; fi
    OUT="$DIR/knack-demo-$(date +%Y%m%d-%H%M%S).mov"
    ARGS=(-v -x)
    [[ "${2:-}" == "--audio" ]] && ARGS+=(-g)
    nohup screencapture "${ARGS[@]}" "$OUT" > "$DIR/.recording.log" 2>&1 &
    echo "$! $OUT" > "$PIDF"
    sleep 3
    if ! running; then
      echo "recording did not start. Last output:"; tail -3 "$DIR/.recording.log"
      echo "If macOS asked for Screen Recording, allow it for the app that runs this (Terminal or Claude), then run start again."
      rm -f "$PIDF"; exit 2
    fi
    echo "recording to $OUT (pid $(cut -d' ' -f1 "$PIDF")). Stop with: scripts/record-demo.sh stop"
    ;;
  stop)
    if ! running; then echo "no recording is running"; rm -f "$PIDF"; exit 1; fi
    PID="$(cut -d' ' -f1 "$PIDF")"; OUT="$(cut -d' ' -f2- "$PIDF")"
    kill -INT "$PID" 2>/dev/null
    for _ in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    rm -f "$PIDF"
    if [[ -f "$OUT" ]]; then echo "saved: $OUT ($(du -h "$OUT" | cut -f1))"; else echo "no file was written"; exit 2; fi
    ;;
  status)
    if running; then OUT="$(cut -d' ' -f2- "$PIDF")"; echo "recording: $OUT ($(du -h "$OUT" 2>/dev/null | cut -f1))"; else echo "not recording"; fi
    ;;
  *) echo "usage: $0 start [--audio] | stop | status"; exit 64 ;;
esac
