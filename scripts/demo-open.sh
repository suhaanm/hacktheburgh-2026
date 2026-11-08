#!/usr/bin/env bash
# Opens the live pages the Knack demo needs, in a tidy layout, WITHOUT Accessibility permission: each page is a Chrome window placed by Chrome
# itself (`open -na "Google Chrome" --args --new-window --window-position=X,Y --window-size=W,H <url>`); nothing here moves or clicks another
# app's window, and nothing runs unless you call it.
#
#   scripts/demo-open.sh --only voice,casenote          open just these scenes
#   scripts/demo-open.sh --all                          every scene below (calc and voice share the left of the screen: pick one in a take)
#   scripts/demo-open.sh --list                         the scenes, their pages and their layout, opens nothing
#   scripts/demo-open.sh --only calc --dry-run          print the commands, open nothing
#   options:  --reset            POST /__reset to the three sandbox sites first (clears notes, submissions and counters; pages are unchanged)
#             --shared-profile   use your normal Chrome profile (default: an isolated, empty one in ~/Library/Caches/knack-demo-chrome: no
#                                bookmarks, no tabs, no avatar, and NO capture extension, which is what you want on camera)
#             --browser NAME     the app to open (default "Google Chrome")
#             --screen WxH       the usable screen size in points (default: asked from macOS without any permission; falls back to 1440x875)
#             --no-check         do not check that the sandbox, dashboard and engine answer first
#             --headed           print what the AGENT needs to be seen on screen and exit (opens nothing; see the note below)
#   env:      KNACK_DASHBOARD (default http://127.0.0.1:5173)   KNACK_SITES_PORT (default 7801)   KNACK_ENGINE (default http://127.0.0.1:7700)
#
# Scenes (the shot list in docs/KNACK_DEMO.md says which take uses which):
#   voice      calculator A, first question (http://127.0.0.1:7801/step/1) on the left: the page Hey Knack points at          (take: voice)
#   calc       the three calculators side by side across the screen (7801/step/1, 7802/, 7803/)                              (take: agent run)
#   casenote   the case-note page on the right (7801/casenote?case=CASE-1005)                                                 (take: agent run, coach)
#   home       the dashboard at #/home      needs-you   #/needs-you      routines   #/routines      growth   #/growth
#   your-data  #/your-data    firm  #/firm (admin)    roles  #/roles    onboarding  #/onboarding   genome  #/genome   forecasts  #/forecasts
#   evidence   #/evidence (the honest numbers: large window)       agents  #/agents (background runs)       models  #/models
# THE AGENT IS INVISIBLE UNLESS ITS STACK WAS STARTED HEADED. The agent runs the three calculators in its own Chromium, which is headless by
# default. For the recording the live stack is started by the lead as `UNDERSTUDY_AGENT_HEADED=1 make live` (this script never starts or restarts
# anything); then the agent's own windows appear on screen while it works, on top of whatever this script opened.
# The Knack app shows the dashboard inside its own window; these Chrome windows are for the web-only views (Evidence, Firm, Forecasts), for a
# take without the app, and for the sandbox pages. The case-note page, the calculators and the dashboard all stay read-only here: opening a page
# changes nothing except the sandbox page counters.
set -uo pipefail

DASH="${KNACK_DASHBOARD:-http://127.0.0.1:5173}"; DASH="${DASH%/}"
SP="${KNACK_SITES_PORT:-7801}"
ENGINE="${KNACK_ENGINE:-http://127.0.0.1:7700}"; ENGINE="${ENGINE%/}"
SITE_A="http://127.0.0.1:$SP"; SITE_B="http://127.0.0.1:$((SP + 1))"; SITE_C="http://127.0.0.1:$((SP + 2))"
BROWSER="Google Chrome"
PROFILE="${KNACK_DEMO_CHROME:-$HOME/Library/Caches/knack-demo-chrome}"
ISOLATED=1; DRY=0; RESET=0; CHECK=1; LIST=0; ALL=0; ONLY=""; SCREEN=""

while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY="${ONLY:+$ONLY,}${2:-}"; shift 2 ;;
    --all) ALL=1; shift ;;
    --list) LIST=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --reset) RESET=1; shift ;;
    --shared-profile) ISOLATED=0; shift ;;
    --browser) BROWSER="${2:-}"; shift 2 ;;
    --screen) SCREEN="${2:-}"; shift 2 ;;
    --no-check) CHECK=0; shift ;;
    --headed) echo "To see the agent work on screen, the live stack must be started with its browser headed (the lead does this; nothing here starts a service):"; echo "    UNDERSTUDY_AGENT_HEADED=1 make live"; echo "The agent's own Chromium windows then open by themselves during a run (Routines > Run now); this script does not place them."; exit 0 ;;
    -h|--help) sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

ALL_SCENES="voice calc casenote home needs-you routines growth your-data firm roles onboarding genome forecasts evidence agents models"

# ---- the usable screen (points): macOS answers this without Accessibility; the menu bar is excluded
SW=1440; SH=875; TOP=25; X0=0
if [ -n "$SCREEN" ]; then
  SW="${SCREEN%x*}"; SH="${SCREEN#*x}"; TOP=0
else
  got="$(osascript -l JavaScript -e 'ObjC.import("AppKit"); var s=$.NSScreen.mainScreen; var f=s.frame, v=s.visibleFrame; [Math.round(v.origin.x), Math.round(v.size.width), Math.round(v.size.height), Math.round(f.size.height-(v.origin.y+v.size.height))].join(" ")' 2>/dev/null || true)"
  if [ -n "$got" ]; then set -- $got; X0="$1"; SW="$2"; SH="$3"; TOP="$4"; fi
fi
case "$SW$SH" in *[!0-9]*) echo "bad --screen value (use WxH, e.g. 1440x875)" >&2; exit 2 ;; esac

# ---- scene -> "url|x|y|w|h" (integers; a scene may open several windows: one per line)
third=$((SW / 3))
scene_windows() {
  case "$1" in
    voice)     echo "$SITE_A/step/1|$X0|$TOP|$((SW * 55 / 100))|$SH" ;;
    calc)      echo "$SITE_A/step/1|$X0|$TOP|$third|$SH"
               echo "$SITE_B/|$((X0 + third))|$TOP|$third|$SH"
               echo "$SITE_C/|$((X0 + 2 * third))|$TOP|$third|$SH" ;;
    casenote)  echo "$SITE_A/casenote?case=CASE-1005|$((X0 + SW * 55 / 100))|$TOP|$((SW * 45 / 100))|$((SH * 55 / 100))" ;;
    home|needs-you|routines|growth|your-data|firm|roles|onboarding|genome|forecasts|agents|models)
               echo "$DASH/#/$1|$((X0 + (SW - 1152) / 2))|$((TOP + (SH - 735) / 3))|1152|735" ;;
    evidence)  echo "$DASH/#/evidence|$((X0 + (SW - 1280) / 2))|$TOP|1280|$SH" ;;
    *) return 1 ;;
  esac
}

if [ "$LIST" = 1 ]; then
  echo "usable screen: ${SW}x${SH} at ($X0,$TOP). Chrome profile: $([ $ISOLATED = 1 ] && echo "isolated ($PROFILE)" || echo 'your own')"
  for s in $ALL_SCENES; do
    scene_windows "$s" | while IFS='|' read -r url x y w h; do printf '  %-10s %-52s at %s,%s  %sx%s\n' "$s" "$url" "$x" "$y" "$w" "$h"; done
  done
  exit 0
fi

SCENES=""
if [ "$ALL" = 1 ]; then SCENES="$ALL_SCENES"; fi
if [ -n "$ONLY" ]; then SCENES="$SCENES $(echo "$ONLY" | tr ',' ' ')"; fi
if [ -z "$SCENES" ]; then
  echo "Nothing to open: this script runs only when asked. Use --only <scene>[,<scene>] or --all (see --list for the scenes)." >&2
  exit 2
fi
for s in $SCENES; do
  scene_windows "$s" >/dev/null 2>&1 || { echo "unknown scene: $s (see --list)" >&2; exit 2; }
done

# ---- are the services up? (warn, never block: a scene may be wanted for a take without the stack)
check() { # label url
  if curl -fsS -m 2 -o /dev/null "$2" 2>/dev/null; then echo "  up    $1  $2"; else echo "  DOWN  $1  $2  (start the stack: make live)"; fi
}
if [ "$CHECK" = 1 ] && [ "$DRY" = 0 ]; then
  echo "Checking what the scenes need:"
  case " $SCENES " in *" voice "*|*" calc "*|*" casenote "*) check "sandbox A" "$SITE_A/healthz"; check "sandbox B" "$SITE_B/healthz"; check "sandbox C" "$SITE_C/healthz" ;; esac
  case " $SCENES " in *" home "*|*" needs-you "*|*" routines "*|*" growth "*|*" your-data "*|*" firm "*|*" roles "*|*" onboarding "*|*" genome "*|*" forecasts "*|*" evidence "*|*" agents "*|*" models "*) check "dashboard" "$DASH/"; check "engine" "$ENGINE/health" ;; esac
fi

if [ "$RESET" = 1 ]; then
  if [ "$DRY" = 1 ]; then echo "would reset the sandbox sites (POST /__reset on $SP, $((SP + 1)), $((SP + 2)))"
  else for p in "$SP" "$((SP + 1))" "$((SP + 2))"; do curl -fsS -m 3 -X POST "http://127.0.0.1:$p/__reset" >/dev/null 2>&1 && echo "reset sandbox site on $p" || echo "could not reset the site on $p"; done; fi
fi

# ---- open
FLAGS=(--new-window --no-first-run --no-default-browser-check)
if [ "$ISOLATED" = 1 ]; then mkdir -p "$PROFILE" 2>/dev/null || true; FLAGS+=("--user-data-dir=$PROFILE"); fi
opened=0
for s in $SCENES; do
  while IFS='|' read -r url x y w h; do
    cmd=(open -na "$BROWSER" --args "${FLAGS[@]}" "--window-position=$x,$y" "--window-size=$w,$h" "$url")
    if [ "$DRY" = 1 ]; then printf 'would run:'; printf ' %q' "${cmd[@]}"; printf '\n'
    else
      if "${cmd[@]}" 2>/dev/null; then printf 'opened  %-10s %s  at %s,%s  %sx%s\n' "$s" "$url" "$x" "$y" "$w" "$h"; opened=$((opened + 1)); sleep 0.7
      else printf 'FAILED  %-10s %s (is "%s" installed?)\n' "$s" "$url" "$BROWSER"; fi
    fi
  done < <(scene_windows "$s")
done
[ "$DRY" = 1 ] && echo "dry run: nothing was opened." || echo "opened $opened window(s). Close them yourself when the take is done (this script never closes or moves a window)."
