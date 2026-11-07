# Showtime: the automated walkthrough

Showtime plays a hard-coded, timed tour of Alongside on the built-in practice desktop (`apps/demo-stage`). It drives the real app (real dock, real overlay, real level chip, real confirmation modal), so what you see is the product, not a video. It is meant for the demo and for first-time visitors.

## What Showtime is, and is not

Showtime is scripted and runs on the built-in **practice desktop**, a fake desktop window (`apps/demo-stage`) that Showtime opens fullscreen. It does NOT drive the real macOS desktop, a real Calculator or a real browser window: the rings, clicks and highlights land on the practice desktop's own elements. There is no real-macOS Showtime mode in this build. The real-macOS demo is the normal product, used by voice or chat: say the helper's name (or use Type instead) and ask for help with whatever is really on your screen. The in-app badge reads "Scripted walkthrough on a practice desktop" for this reason.

## Start and stop

- Menu bar item: "Run the demo walkthrough" (it says "Stop the demo walkthrough" while the tour is active). Emits the bus event `showtime:request`.
- Dock: More settings, Other, "Run demo" / "Stop demo".
- IPC (`window.alongside.showtime`): `start({full?, mode?})`, `stop`, `next`, `prev`, `pause` (toggles), `state`, `onState`, `onCue`.
- While the tour runs, a small control bar at the top of the dock offers Back, Pause, Next and Stop demo. The dock's own Stop button also ends the tour at any time.
- `ALONGSIDE_SHOWTIME_AUTOSTART=1` starts the tour about 3 seconds after launch (hands-free demo and smoke runs).

## Modes

| mode | what runs | model calls |
|---|---|---|
| `scripted` (default) | Fixed timings. Highlight and ring boxes come from the stage's own ground truth (`__stage.rects()`), the scam report and the file search result are recorded fixtures, the level change goes through the real level engine. | none |
| `live` (`ALONGSIDE_SHOWTIME_MODE=live` or `start({mode:'live'})`) | The scam check runs the real analyst on the stage message text; the file search runs the real `search_files` tool. Everything else is still scripted. | yes |

A discreet "Scripted walkthrough on a practice desktop" badge shows at the top right of the screen in scripted mode. `ALONGSIDE_SHOWTIME_BADGE=0` hides it. The roadmap strip (chapter dots, current chapter, one-line caption, progress bar) shows at the top left.

After the last chapter the app is back to normal live mode with your real profile and settings, and the practice desktop stays up for questions until you press Stop.

## Chapters

1. Say its name. 2. It shows, you do (rings, numbers, ticks). 3. Less help as you learn (level chip drains, a scripted stall gets a nudge then an arrow, hints chart). 4. Scam Shield (recorded report, never says "safe"). 5. Meet the second helper (persona switch). 6. Teach me anything (one-step custom lesson). 7. I can do it for you (needs the agency setting: real confirm modal, the demo approve step is automated and labelled, audit line shown). 8. Your files (recorded search result). 9. Type instead (chat view). 10. You're in control (look and feel, forget a profile line, Stop). 11. Progress, then hand-over to live Q&A.

`ALONGSIDE_SHOWTIME_FULL=1` (or `start({full:true})`) adds extra narration and interactions. The core cut is checked by a unit test to fit 3:00 with at least 8 seconds of margin.

A chapter whose dependency is missing is marked unavailable and skipped (chapter 7 without the `agency` setting; chapter 8 in live mode without the files service). The skip reason is in `state().chapters[i].reason`.

## What it changes, and puts back

- Settings flipped by the tour (glass, glass opacity, dyslexia font, text scale, theme, high contrast) and the persona are restored when the tour ends or is stopped.
- `profile.md` is replaced by `assets/showtime/demo-profile.md` for the run. A real profile is moved to `profile.md.showtime-backup` first and put back byte for byte at the end; a missing profile is removed again. If the app is killed mid-tour, the real profile is restored on the next launch (before the learner store loads) and before the next tour.
- Three practice attempts (ids `showtime-1..3`) are written to the learner store so the progress chart has history. They are not removed afterwards.

## Narration audio

Pre-rendered clips live in `assets/showtime/clips/<id>.wav` with a `manifest.json` carrying a text hash. A missing or stale clip means captions only, never a wrong voice line. `ALONGSIDE_SHOWTIME_MUTE=1` (or the Text only setting) forces captions only.

## Verified and not verified

Verified by unit tests (`npx vitest run src/main/showtime src/renderer/overlay/annotations src/renderer/dock/showtime-cues.test.ts`): script timing and narration slots, the machine (pause, next, prev, stop, skipping, failing actions), the service lifecycle (start, stop, hand-over, profile backup and restore, stage open failure, cancel while opening, badge and mode switches, bus requests from the tray, dock Stop), the driver actions against fakes, the roadmap view-model and the dock cue mapping. `npm run typecheck` and `npm run build` are green.

Real Electron (MAC-A, `docs/reports/MAC_A.md`, before the 15:04 fixes): the tour started from the tray, ran chapters 1 to 11 of 11 in about 150 s and Stop worked. It also found that the practice desktop stopped showing in captures after about 40 s, that the control bar covered the dock header, and that agency, captions and doItForMe stayed changed after Stop. Fixes for those were made afterwards and have not been re-run on a Mac.

Not verified: a real Electron run after those fixes, audio playback, the Stop box position (an estimate from the dock geometry), and narration audio (no clips have been rendered, so the tour is captions only).
