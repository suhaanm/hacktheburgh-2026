#!/usr/bin/env bash
# Builds the Cue storyboard and writes the screenshots (light and dark, 1440x900 and 390x844) to harness/shots.
# Usage: src/renderer/cue/harness/shoot.sh [--states a,b] [--themes light,dark] [--sizes 1440x900] [--out dir]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO"
node src/renderer/cue/harness/build.mjs
node src/renderer/cue/harness/shoot.mjs "$@"
