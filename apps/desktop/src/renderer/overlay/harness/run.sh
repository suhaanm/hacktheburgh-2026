#!/usr/bin/env bash
# Headless overlay render: builds demo.html and screenshots every fixture over light and dark backdrops.
# Usage: src/renderer/overlay/harness/run.sh [--out dir] [--fixtures a,b] [--backdrops light,dark,stage]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO"
node src/renderer/overlay/harness/build.mjs
ALONGSIDE_LOCK_WAIT="${ALONGSIDE_LOCK_WAIT:-60}" ALONGSIDE_LOCK_MAX_SECONDS=120 \
  scripts/electron-lock.sh OVERLAY node_modules/.bin/electron src/renderer/overlay/harness/electron-main.cjs "$@"
