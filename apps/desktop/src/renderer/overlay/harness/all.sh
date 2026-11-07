#!/usr/bin/env bash
# One electron-lock hold (<3 min) for: every fixture screenshot, then the real-window checks.
# Usage: src/renderer/overlay/harness/all.sh   (REAL_CHECK_SKIP=ring,click skips parts of the real-window run; HARNESS_ARGS="--fixtures a,b" limits the screenshots)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO"
node src/renderer/overlay/harness/build.mjs
npm run build >/dev/null
ALONGSIDE_LOCK_WAIT="${ALONGSIDE_LOCK_WAIT:-900}" ALONGSIDE_LOCK_MAX_SECONDS=175 \
  scripts/electron-lock.sh OVERLAY bash -c '
    node_modules/.bin/electron src/renderer/overlay/harness/electron-main.cjs --out docs/overlay-shots ${HARNESS_ARGS:-}
    node src/renderer/overlay/harness/real-check.mjs'
