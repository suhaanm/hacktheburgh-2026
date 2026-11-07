#!/usr/bin/env bash
# Real-window verification (click-through, content protection, point_at on the STAGE page, full-screen Space).
# Takes over the primary display for ~1-2 minutes: run it only when nobody is looking at the screen.
# Needs: STAGE server on 127.0.0.1:5180 (npm run stage), GEMINI_API_KEY in .env, Screen Recording + Accessibility granted.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO"
npm run build >/dev/null
ALONGSIDE_LOCK_WAIT="${ALONGSIDE_LOCK_WAIT:-240}" ALONGSIDE_LOCK_MAX_SECONDS=300 \
  scripts/electron-lock.sh OVERLAY node src/renderer/overlay/harness/real-check.mjs
