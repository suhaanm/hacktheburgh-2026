#!/usr/bin/env bash
# Builds the Cue bundle (out/cue-check) and runs the real-Electron check of the panel window, under the shared Electron lock.
# The window is never shown (see real-check.cjs). Usage: src/renderer/cue/harness/real-check.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO"
npx electron-vite build -c src/renderer/cue/harness/electron.vite.check.config.ts >/dev/null
ALONGSIDE_LOCK_WAIT="${ALONGSIDE_LOCK_WAIT:-120}" ALONGSIDE_LOCK_MAX_SECONDS=90 \
  scripts/electron-lock.sh CUE node_modules/.bin/electron src/renderer/cue/harness/real-check.cjs
status=$?
rm -rf out/cue-check
exit $status
