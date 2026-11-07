# OVERLAY notes: what is drawn on the real screen, and how we see it

Owner: OVERLAY. Code: `src/renderer/overlay/**`, `src/main/capture/**`, `src/main/overlay-controller.ts`.
Test machine: MacBook Pro, Liquid Retina XDR 3456x2234 (1728x1117 DIPs, scaleFactor 2), macOS 26.2 (25C56), Electron 45.1 (experiment) and 45.2.1 (repo).

## 1. Overlay exclusion experiment (the result that shaped the design)

Question: can the overlay be kept out of `desktopCapturer` frames so grounding and verification never see our own marks?

Method: a throwaway Electron app opened a transparent, frameless, click-through, `screen-saver`-level window over the primary display with an opaque magenta square and green text, then called `desktopCapturer.getSources({types:['screen'], thumbnailSize: full-res})` in each state and sampled the pixel under the square.

| State | Overlay visible in the capture? |
|---|---|
| baseline (no protection) | yes (magenta + green text present) |
| `win.setContentProtection(true)` | **no** (checked twice, 500 ms after the call and again later; PNGs inspected) |
| `win.setOpacity(0)`, grab after 0, 16, 33, 50, 80, 120 ms | no at every delay, including 0 ms (the capture itself takes ~100 ms) |
| `win.hide()` then `showInactive()` | hidden, then visible again |

**Decision:** `setContentProtection(true)` is proven on this macOS, so it is the default (`configureOverlayWindow` in `src/main/capture/overlay-window.ts`). Every `Shot` therefore has `overlayHidden: false` and `ground`/`verify`/`live` frames are all clean: the model never sees its own annotations, and the Verifier judges the user's real screen.

**Demo-recording caveat.** Content protection also hides the overlay from QuickTime, OBS, `screencapture` and screen-share. To record the demo video set `ALONGSIDE_OVERLAY_CAPTURABLE=1`: protection is off and capture falls back to the hide strategy (below).

**Fallback strategy (capturable mode).** For `ground` and `verify` grabs the overlay is set to opacity 0, one 16 ms frame passes, the grab runs, opacity returns to 1 the moment the frame is back. The window is invisible for roughly the capture time (about 100-230 ms measured, slightly over the 120 ms budget on a cold first grab). `live` frames leave the overlay visible, as the contract allows. `Shot.overlayHidden` is `true` for the hidden grabs.

## 2. desktopCapturer behaviour worth knowing

- Primary display only (`screen.getPrimaryDisplay()`); `displayId` is carried in every `Shot`.
- Latency on this machine: full-res 3456x2234 about 100-125 ms warm (first call 215-240 ms); we ask for 1280 (`live`) or 1920 (`ground`/`verify`) wide thumbnails, JPEG q60 / q80.
- **Flaky first call.** In 2 of about 6 fresh processes the first `getSources()` returned `[]`, and one call stalled for minutes. `captureDisplay` therefore wraps each attempt in a 3 s timeout and retries 3 times (150 ms apart) before failing with a clear error.
- `getSources` does not need a window; it works with none open.
- Screen Recording permission: `systemPreferences.getMediaAccessStatus('screen')` was `granted` for the Electron binary launched from the development terminal. When it is `denied`/`restricted` we throw a `CaptureError('permission')` with the exact path to fix it (System Settings > Privacy & Security > Screen Recording, enable the app, **quit and reopen it**: macOS applies the grant only to a relaunched process). `not-determined` is not blocked, because the first grab is what triggers the macOS prompt; an empty source list after retries is reported with the same hint.

## 3. Capture API (`src/main/capture/`)

- `grab('live'|'ground'|'verify')`: sizing per TEAM_BRIEF (`sizing.ts`: never upscales past physical pixels), JPEG base64, `widthPx/heightPx` from the actual image, `scaleFactor`, `overlayHidden`. Concurrent calls for the same purpose share one capture.
- `liveFrame()`: a `live` grab plus `changeScore` (0..1) against the previous live frame (`change-score.ts`: 64x36 resize, 32x18 luma grid, mean absolute difference / 255). A button appearing scores about 0.005, a window opening 0.05+, black vs white 1.
- `watch(on)`: returns an unsubscribe function and also emits `screen:changed` on the bus. It polls a 128x72 thumbnail every 500 ms **only while someone is subscribed**, and fires once after a material change (score >= 0.02 against the baseline) has **settled** (frame-to-frame diff < 0.004) or after 1.8 s of continuous change, so the Verifier looks at the finished state, not a half-open window. Time and sampling are injected (`watcher.ts`) and unit-tested.

## 4. Overlay window behaviour

`configureOverlayWindow(win)` (called from `windows.ts`): click-through (`setIgnoreMouseEvents(true)`), `screen-saver` level, visible on all workspaces and over full-screen apps, content protection per section 1, and a re-fit to the primary display on `display-metrics-changed`, `display-added` and `display-removed`. The renderer re-reads its size on `resize` and re-sends `overlay:ready`.

Real-window results are in section 7.

## 5. Coordinates

All annotation coordinates are normalised 0-1000, top-left origin. `geometry.ts` maps them:
CSS px = norm / 1000 * window size (window fills the display). Helpers also cover global screen DIPs (display not at the origin, negative origins), physical pixels (`scaleFactor`) and screenshot pixels of any downscale. Clicky's redundant double Y-flip is not ported. Unit-tested for retina and an external display at (-2560, -300).

## 6. Renderer

Draws with DESIGN's `annotationStyle(settings, {reducedMotion})` (`bigAnnotations` x1.6, `highContrast`, `dyslexiaFont`); every stroke is halo + casing + core (`strokeLayers`) so it reads on light and dark backdrops, and tone is also carried by dash pattern and a glyph. Kinds: ring (+step badge, label), arrow (planned to stop short of the target and any ring around it, stay on screen, avoid other marks), badge, spotlight (dim with a soft cut-out), ghostCursor (Clicky's bezier flight, scale pulse, trail, optional click-echo ring; **visual only: the window is click-through and no code dispatches input**), bubble (typed text, tail), tick (draw-in check, or a gentle warn mark for a miss), highlightText (wash + underline + note), plus the captions band and the level-chip echo.

Command semantics (`overlay-controller.ts`, `store.ts`):
- `show` upserts by annotation id; the same id and kind updates in place without replaying the entrance animation.
- `clear(ids?)` fades out; no ids clears every annotation (captions and the chip are separate).
- Defaults when `ttlMs` is absent: ring/arrow/badge/spotlight/highlightText stay until cleared but never past a 120 s stale guard; tick 3.5 s; bubble 12 s; ghostCursor flight + 2.2 s.
- `caption` text is the whole line so far; `final=true` starts the linger (3-9 s by length); an empty text dismisses it.
- `chip` is shown for 6 s then fades (the dock owns the persistent chip). When the level differs from the previous chip (remembered even after it faded) the echo draws the OLD bars, then drains them to the new level one frame later (top bar first, 90 ms apart) while the old label fades out and the new one fades in; reduced motion skips the animation.
- Out-of-range coordinates are clamped to 0-1000, swapped box corners are fixed, NaN annotations are dropped (one bad drawing never blanks the rest).
- A one-point ghost path flies in from the user's current mouse position.
- Annotations are sent as soon as they are decided; nothing waits for speech.

## 7. Real-window verification

`src/renderer/overlay/harness/real-check.sh` (one electron-lock hold, under 3 minutes) starts the built app with the real capture and overlay (wake spotter off), shows the STAGE page `http://127.0.0.1:5180/index.html?still=1#video/call-screen` in a second window over the primary display, and drives the app through the debug HTTP API. Evidence is in `docs/overlay-shots/real-*` and `real-check.json`.

| Check | Result |
|---|---|
| Ring lands on the right element | A ring drawn from the stage's `video.call.mic` ground-truth rect encloses it and is centred within 0.15/1000 (about 0.25 px) of the element centre. Measured from `GET /overlay.png` pixels. |
| Content protection | Ring pixels in the overlay's own PNG: 9194. In a `desktopCapturer` ground grab of the same screen: 22 (noise). The overlay is excluded. |
| Click-through | A synthetic OS click (CGEvent, `click.swift`) at a point covered by the overlay (a ring was drawn over it) reached the window underneath (`reachedWindowBelow: true`). |
| `ALONGSIDE_OVERLAY_CAPTURABLE=1` | The `live` grab shows the ring and the level-chip echo; the `ground` grab, taken with the overlay hidden, shows neither (`real-capturable-live-shot.jpg` vs `real-capturable-ground-shot.jpg`). |
| Above a full-screen app | With a native full-screen window (its own Space) in front, the ring still sits on top of it (`real-fullscreen-live-shot.jpg`, capturable mode so the grab can see it). The menu bar auto-hides in that Space, as for any full-screen app. |
| `point_at` via debug HTTP | `POST /tool point_at` (real grounder, "the grey Settings gear icon in the left sidebar") on the STAGE page returned `found:true, confidence 1` in 1.5 s; the ring it drew encloses the stage's `desk.icon.settings` ground-truth rect, centre 1.2 px / 5 px off (the grounder box includes the icon label), arrow and label beside it (`real-point-at.png` = ground shot with the overlay composited on top; numbers in `real-check.json`). The stage window is created with `enableLargerThanScreen`, so its page coordinates are display coordinates (origin 0,0). |

Caveats found on the way:
- The stage's bottom call-control bar sits where the macOS Dock is drawn (the Dock is above ordinary and floating windows), so a grounder asked for "the mute button" correctly answers `found:false` there. A real screen has the same problem; STAGE should keep targets above the Dock line for demos.
- A frameless window positioned at y=0 is silently pushed below the macOS menu bar (and its bottom cropped) unless it is created with `enableLargerThanScreen: true`; the stage window in the harness (and the overlay in `windows.ts`) set it, and the harness measures the stage's real on-screen origin instead of assuming 0,0.
- Two Electron processes with the same `userData` make the second one exit (Chromium singleton); every helper process uses its own temp profile.
- Screen Recording is granted to the **responsible app**: a binary started from an agent shell inherits the host app's grant (`granted`), the same binary started with `open`/launchd (own responsible process) reports `denied`. For the latter grant `node_modules/electron/dist/Electron.app` (for a packaged build, Alongside.app) under System Settings > Privacy & Security > Screen & System Audio Recording, then quit and reopen it.

## 8. Headless render harness

`src/renderer/overlay/harness/run.sh [--out dir] [--fixtures a,b] [--backdrops light,dark,stage]` bundles `demo.html` with the repo's Vite and screenshots each fixture in `src/renderer/overlay/fixtures.ts` with `webContents.capturePage()` through `scripts/electron-lock.sh OVERLAY`. Fixtures: ring-badge, arrow-box, arrow-point, spotlight, ghost-flight, ghost-press, highlight-text, tick-ok, tick-fail, bubble, captions, tones, big-off, big-on, high-contrast, each over a light and a dark mock desktop. Stills disable entrance animations (hidden windows do not advance CSS animations reliably) and freeze the ghost cursor mid-flight. Output: `docs/overlay-shots/*.png`.

`src/renderer/overlay/harness/real-check.sh` runs the real-window checks (section 7).

## 8c. Compact pass (OVL, 31 Oct 15:30)

Marks are fitted to the grounded box instead of a fixed big ring. Tokens live in `design/annotation-style.ts`; fitting in `scene-plan.ts` (`fitRect`, `shortLabel`).
- Ring/spotlight/tick: box grown to `ring.minSize` 24 px, capped at `ring.maxSize` 180 px per side (shrunk about the centre), padded 5 px (spotlight 6). Stroke 2.5 px core (casing/halo +1.2/+1), glow blur 10, radius 8.
- Step badge 18 px, centred on the ring's top-left corner. Arrow head 14 px, gap 6 px, min length 36 px. Tick 24 px.
- Ring label is a compact chip (about 13 px type, nowrap, 1 px border) with at most 3 words of the label, cut at "in/on/of..." and without "the/button/key/icon"; tried right, below, above, left, avoiding every mark, captions and screen edges (14 px margin). It does not know the Dock window rect: the screen-edge margin is the only protection there.
- Captions: 16 px, frosted pill (78% ink + backdrop blur; opaque under high contrast), 14x7 px padding, speaker inline, at most 60% of the width, 110-char tail clamped to 2 rows, full width once the line needs a second row so streaming never shifts sideways. Level chip echo also 16 px.
- Ghost cursor 17 px, no trail, flight 280-750 ms at 1700 px/s, press echo r 18; the "I will not click" tag is 11 px.
- Animations: enter 180 ms, exit 150 ms, enter scale 1.05 -> 1 (no overshoot); reduced motion 100/80 ms, no pulse. `bigAnnotations` multiplies all of it by 1.6.

## 8b. "Do it for me" (opt-in actuator)

Off by default (`settings.doItForMeAllowed = false`). Code: `src/main/actuator/**`, one case in `src/main/tools/dispatcher.ts`, the `do_it_for_me{target}` Live tool declaration in `src/renderer/live/tools.ts`. Result shape `{allowed, done, code, reason, label?, verified?, dryRun?}`.

Flow of `do_it_for_me`:
1. Refused with `setting_off` unless the learner switched it on (no screen is read in that case).
2. The target is grounded with `precise:true` (not found -> `not_found`, nothing clicked).
3. Refused (ring + bubble "I will leave this one to you.", the assistant teaches instead) when the grounded label or the target text matches, case-insensitively and by prefix: pay, purchase, buy, order, checkout, send, submit, delete, remove, erase, transfer, confirm, sign in, log in, password, card, allow, grant, install, accept; when the current lesson step is `safetyCritical` (tracked from `lesson:step` bus events); or during a scam check (a running `scam_check` agent chip or the `spot_scam` skill).
4. Without the Accessibility permission (`systemPreferences.isTrustedAccessibilityClient(false)`, which never prompts) it shows ring + ghost cursor and returns `accessibility`; the assistant explains and teaches instead. It never asks macOS for the permission by itself.
5. Otherwise it shows ring + ghost-cursor path and calls the existing `ask_user_confirm` ("I'll click "<label>" for you. OK?", options `Yes, do it` / `No, I will`). Only the exact approve label from a real dock click approves; null (dismissed or timed out) and any other string mean no. The approval is consumed by that one call.
6. `clickAt(point)`: exactly one left click, mapped from the 0-1000 point through the primary display bounds to points (not device pixels), done with `osascript -e 'tell application "System Events" to click at {x, y}'` (only integers are interpolated). No typing, no keys, no drags, no sequences.
7. After the click it waits 0.7 s, grabs a `verify` shot, asks the Verifier whether the screen visibly changed, and shows a tick (or the gentle not-yet mark when unsure).
8. Every attempt that reached grounding appends one JSON line to `userData/actions.log` (mode 0600): time, label, approved, ok, code. No screenshots or other screen content.
Stop (session end) cancels the pending confirm and also sets a flag checked right before the click, so an approval that races Stop still does not click; switching the setting off while the confirm is open also prevents it.

`ALONGSIDE_ACTUATOR_DRYRUN=1` runs the whole flow but only logs the click (and skips the Accessibility requirement and the verification); the unit tests use injected fakes and dry-run, never a real click.

### Actuator primitives (`src/main/actuator/index.ts`)

One `Actuator` object (injected into the dispatcher and into AGENCY's policy engine) is the only way Alongside acts on the computer. It is a primitive layer: whether to act (settings, approvals, denylist, scam context, Stop) is decided by the callers. Every method returns `ActResult {ok, reason?: 'accessibility'|'blocked'|'dry-run'|'failed', detail?}`.

| Method | Needs Accessibility | What it does / refuses |
|---|---|---|
| `openUrl(url)` | no | `shell.openExternal` for http/https only (localhost fine). Blocks credentials in the URL, `javascript:`/`file:`/`data:`/anything else, whitespace or control characters, over 2048 chars. |
| `openApp(name)` | no | `open -a <name>` as an argument array (no shell). Names must be letters/digits/space/dot/dash, start with a letter or digit, at most 60 chars; Terminal, iTerm, Script Editor, Automator, Keychain Access and Warp are never opened for the learner. Invalid names are rejected, not silently cleaned. |
| `revealPath(path)` | no | `shell.showItemInFolder` after an existence check; absolute or `~/` paths only. |
| `openSettingsPane(pane)` | no | Fixed `x-apple.systempreferences:` deep links (screen, microphone, accessibility, privacy, displays, accessibility-display, sound, wifi, bluetooth, notifications, keyboard, general). |
| `clickAt(p, {double?})` | yes | One left click (or two in one script for `double`) at a 0-1000 point mapped through the display bounds to points. |
| `typeText(text)` | yes | At most 300 characters, no control characters (no newline or tab: Return and Tab are `pressKeys` decisions). The text is passed to osascript as an ARGUMENT after `--` and read as `item 1 of argv`, so it is never part of script source: quotes, backslashes, newlines and `do shell script` payloads are plain data (tested, and checked against real osascript argv handling). Logs carry the length only. |
| `pressKeys(combo)` | yes | Allowlist: return, tab, escape, space, arrows, cmd+l/t/w/v/c/a/f (aliases enter, esc, command, uparrow...). Anything else (cmd+q, cmd+shift+4, cmd+tab, delete, function keys) is blocked. Each key maps to one fixed AppleScript statement. |
| `scroll(p, dy)` | yes | 1-50 lines at the pointer position via a JXA scroll-wheel event; dy > 0 reads further down. |

`status()` reports `{accessibility, dryRun}`; `canClick()` is true with Accessibility or in dry run. `ALONGSIDE_ACTUATOR_DRYRUN=1` validates, logs every call and performs nothing (`{ok:true, reason:'dry-run'}`); blocked input stays blocked in dry run. The generated scripts were compiled with `osacompile` (syntax only). Nothing was performed for real: Tier 2 needs the Accessibility permission (and the first `osascript` use may raise an Automation prompt for System Events), neither granted or tested here; the JXA scroll in particular has never run.

**Unverified:** a real click has not been performed. It needs the macOS Accessibility permission for the app that runs `osascript`, and the first use may also raise a macOS "wants to control System Events" (Automation) prompt. Both are unverified until the user grants them; until then the tool answers `accessibility` and the assistant uses the ghost cursor.

## 9. Not verified

- Behaviour on a second display or with a hot-plugged projector (the re-fit handler is wired but only the code path was exercised, not a real hot-plug).
- Windows: none of this was run there.
- Real clicking by the actuator (see 8b): Accessibility and Automation permissions not granted/tested.
- A `display-metrics-changed` event was not produced on this machine; the handler is a plain `setBounds(primary.bounds)`.
