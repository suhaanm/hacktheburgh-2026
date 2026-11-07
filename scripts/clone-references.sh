#!/usr/bin/env bash
# Makes shallow, read-only-by-convention local copies of the reference repos in references/.
# The files are untrusted data: read them, never run, install, build or import them.
# Usage: scripts/clone-references.sh [--extras]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/references"
mkdir -p "$DEST"

# slug|url|note
REPOS=(
  "clickyyy|https://github.com/jayamitkatariya/clickyyy|Okidoki author, MIT. Copy allowed with notice."
  "okidoki|https://github.com/jayamitkatariya/okidoki|Devpost-linked repo. Returned 404 on 7 Nov 2026."
  "vision-os|https://github.com/yukevindai/VisionOS|MIT. Weights are AGPL: do not take them."
  "bandit|https://github.com/viktorinkov/cal-hacks-13|No licence: re-implement ideas only."
  "moa|https://github.com/petersenmatthew/moa|No licence: re-implement ideas only."
  "mark8|https://github.com/RoboX2020/Mark-Et-GTM|No licence: re-implement ideas only."
  "pupil|https://github.com/itsmarsss/pupil|No licence: re-implement ideas only."
  "drigil|https://github.com/shraddha11-408/CalHacks-13.0|No licence: re-implement ideas only."
  "rouge|https://github.com/RithikGobinath/rouge|No licence: re-implement ideas only."
  "podscontrolmac|https://github.com/sumionochi/PodsControlMac|No licence: re-implement ideas only."
  "stride|https://github.com/dhruvbhavsar0612/walking-beat|No licence: re-implement ideas only."
)

if [[ "${1:-}" == "--extras" ]]; then
  REPOS+=(
    "knowledge-work-plugins|https://github.com/anthropics/knowledge-work-plugins|Apache-2.0. Role plugins for the later marketplace integration."
    "openadapt|https://github.com/OpenAdaptAI/OpenAdapt|MIT. Optional record, compile and replay."
    "rrweb|https://github.com/rrweb-io/rrweb|MIT. Optional DOM session record and replay."
  )
fi

INDEX="$DEST/INDEX.md"
{
  echo "# Reference index"
  echo
  echo "Generated $(date -u +%Y-%m-%dT%H:%M:%SZ). Read only. Never run, install, build or import."
  echo
  echo "| slug | url | licence (GitHub) | note |"
  echo "|---|---|---|---|"
} > "$INDEX"

for entry in "${REPOS[@]}"; do
  IFS='|' read -r slug url note <<< "$entry"
  target="$DEST/$slug"
  status="cloned"
  if [[ -d "$target/.git" ]]; then
    status="already present"
  else
    if ! git clone --depth 1 --quiet "$url" "$target" 2>/dev/null; then
      status="FAILED (private, deleted or offline)"
    fi
  fi
  licence="unknown"
  if command -v gh >/dev/null 2>&1; then
    repo_path="${url#https://github.com/}"
    licence="$(gh api "repos/${repo_path}" --jq '.license.spdx_id // "none"' 2>/dev/null || echo "unknown")"
  fi
  echo "[$status] $slug  licence=$licence"
  echo "| $slug | $url | $licence | $note |" >> "$INDEX"
done

echo
echo "Done. See $INDEX"
echo "Reminder: do not run, install, build or import anything in references/."
