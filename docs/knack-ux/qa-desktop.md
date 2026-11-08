# QA of the desktop app (Track Q3), 8 Nov 2026

What was proved with the hidden harness (no window shown, no real input, no microphone, no capture of the owner's screen: only each page's own pixels), the defects found, and what is open. Pictures are not committed (`/private/tmp/knack-qa-desktop/pics`, light and dark of every surface).

## How to rerun

```
cd apps/desktop
scripts/electron-lock.sh KNACK node scripts/knack-check.mjs --out /tmp/knack-pictures      # the shell check (62 checks)
scripts/electron-lock.sh KNACK node scripts/knack-e2e.mjs                                   # the real main process, stand-in services
scripts/electron-lock.sh KNACK node scripts/knack-e2e.mjs --real-services                   # the app starts the real engine and agent
scripts/electron-lock.sh KNACK node scripts/knack-qa.mjs --out /tmp/knack-qa-pictures       # NEW: pictures and rules of every desktop surface
scripts/electron-lock.sh KNACK node scripts/knack-qa-variants.mjs                           # NEW: wrong surroundings (see below), and the packaged app started hidden
```

`knack-qa.mjs` (src/main/knack/qa-main.ts) covers: first run in the Knack window (role step, connection chips, three consent cards, the permission step with every state faked through the bridge stand-ins: not asked, refused, restricted, all allowed, needs restart, the listener blocked, Show my week, Home, the stopped banner), every wake, info and task card in light and dark (clipping, size, the real-mouse-click rule: a click in the first 600 ms, a script click and Escape answer nothing, a trusted mouse press answers once), the card over the corner pill column (no overlap, follows the column up), the background pills (four and "+2", every state), a faked second display (card, Ask bar, pills, corner column), and window titles. `knack-qa-variants.mjs` starts the real built app hidden with a corrupted settings, window and wake file, a port held by another program, the agent down with no repository to start it from, no key, and the packaged `Knack.app` itself.

## Results (merged tree)

| Run | Result |
|---|---|
| `knack-check.mjs` | 62 of 62 pass |
| `knack-e2e.mjs` | pass (stand-in services, ghost runs ignored, clean quit in 0.1 s) |
| `knack-e2e.mjs --real-services` | pass (real engine and agent started by the app, both stopped by quit in 4.2 s, nothing left listening) |
| `knack-qa.mjs` | 32 of 32 pass |
| `knack-qa-variants.mjs` | corrupt files, port held, agent down and no repo, no key: pass (the app stays up, one plain state, quits with code 0); the packaged app hidden: see the log below |
| desktop unit tests (wake, knack, live, permissions, tray, hud, toast, card, after-pack) | all pass (983 and the new ones) |

## The packaged bundle (`dist-app/mac-arm64/Knack.app`)

Present and checked: `Info.plist` with `NSMicrophoneUsageDescription` ("Knack listens for the words Hey Knack on this Mac. The listening stays on this Mac and nothing is recorded. It also uses the microphone while you talk with it."), `NSSpeechRecognitionUsageDescription` ("Knack uses speech recognition on this Mac to hear Hey Knack. It never uses a server for this and keeps no transcript.") and `NSAppleEventsUsageDescription`; bundle id `app.knack.desktop`, name Knack; `Resources/knack-wake` (Mach-O arm64, `-rwxr-xr-x`, its own embedded plist has the same two strings); `Resources/dashboard` (index.html and 79 assets); `Resources/knack-config.json` (the repository path); `icon.icns`, `icon.png`, ten tray icons; in `app.asar` (1492 entries, every runtime dependency present) the renderer entries ask, cue/card, dock, hey-card, hud, overlay, pills, toast and the preloads ask, cue, hud, index, knack, pills, wakeCard. After the afterPack step `codesign --verify --deep --strict` exits 0 and the identifier is `app.knack.desktop`.

## Defect log

| Id | Surface | What | Status |
|---|---|---|---|
| Q3-01 | Wake and info cards, second display | A card stacked above the corner pill column even when the column was on another display, so it floated in the middle of the pointer's display. The card now goes to the display that holds the column (`cardWorkArea`, `wake/card-ipc.ts`), else the pointer's. Test: `card-ipc.test.ts`; picture run (second display). | Fixed |
| Q3-02 | Knack window, Stop | The dashboard read the kill state once, at page load. Stop everything from the corner pill, the menu bar, the Dock menu or the hotkey (and Resume on the Stopped card) never reached an open window: the sidebar kept saying Stop, or Resume, and the "Everything is stopped" banner stayed or never came. Probably the stuck banner the owner saw. Now read at load, on focus, on visibility, on a retry event and every 3 s while the window is in view. Test: `components/shell/stop-sync.dom.test.ts` (a stop and a resume from outside show within 4 s; a service that does not answer leaves the view). | Fixed |
| Q3-03 | First run, permissions | After the worker switched the microphone or speech recognition on in System Settings the Hey Knack row stayed "On, but not listening yet" for ever (the listener never retries a refusal; only a switch off and on did). The check step now arms the listener once when the window is looked at again and reads its state 1.6 s later. Test: `shouldRearm` in `firstRun.model.test.ts`. | Fixed |
| Q3-04 | First run, Hey Knack row | The "Open System Settings" button under the Hey Knack line stretched across the whole column. CSS only. | Fixed |
| Q3-05 | Menu bar menu | The Knack menu had no one-line reason when Hey Knack could not listen (docs/knack-ux/09-wake-voice.md promises one). A quiet row appears above the switch only when the listener is not simply listening. Test: `knack/tray-knack.test.ts`. | Fixed |
| Q3-06 | Packaging | The stock Electron signature names the app `Electron`, binds no Info.plist and fails `codesign --verify`. afterPack seals the bundle again ad hoc (`codesign --sign -`, no identity) so it is `app.knack.desktop` with its Info.plist bound. Never fatal. Lead decision: keep. | Fixed |
| Q3-07 | Ask bar | "Typing is not on yet. Hold Option-Space and speak." unless a voice conversation is open: typed tasks work only in the web shell's task box. Lead decision: Track V and Track A add the task port to the Ask bar; re-check after it lands. | Open (assigned V, A) |
| Q3-08 | Home | The "Example data" chip and "Some example data" footer show whenever the engine answers with its example fixture or not at all. Honest provenance (D57); only seen on stand-ins. Lead decision: fine. | Closed |
| Q3-09 | Docs | `capabilities-and-permissions.md` describes a "Say Hey Knack" Try it step; first run is three screens with a "Check that it works" step and a Show me ring. Lead decision: assigned V. | Open (assigned V) |
| Q3-10 | Info.plist | Electron's generic camera, Bluetooth and system-audio usage strings. afterPack deletes them with PlistBuddy (never fatal); the microphone, speech recognition and Apple Events strings stay. Test: `tests/after-pack.test.ts`. | Fixed |
| Q3-11 | Packaging notes | A worktree whose `node_modules` is a symlink makes electron-builder drop the transitive dependencies of `@google/genai` and React from the asar (978 entries instead of 1492). Not a product bug; written in `KNACK_BUILD.md`. | Documented |
| Q3-12 | First run, restricted permission | A permission this Mac's policy forbids (state restricted) reads "Turned off in System Settings" with an Open System Settings button that cannot fix it. Cosmetic, rare (a managed Mac). | Open, low |
| Q3-13 | Starting page, first run | The words "example data" are visible in "Running with example data" (starting page), "Knack could not prepare its example data." and, with no key, "No Gemini key found, so Knack runs on example data." The owner's banned words (demo, mock, synthetic, made-up, Alongside) appear nowhere a worker can read: checked in the desktop build, the dashboard bundle, window titles and every card. | Note |

## What was looked at in the pictures

Every picture was read (light and dark): first launch (the role step, the chips, the three consent cards, the permission step in each state), the Starting and error pages, the corner pill in each state (working with a word and n of m, done, stopped with Resume and no Stop, error, voice listening), the approval card above the pill, a wake card above the pill, every wake, info and task card, the top-right pills (running with a moving icon, waiting with a dot, done, failed, stopped, four and "+2"), the Ask bar open and with its answer line. No overlap, no clipped text (a script measured every element of every card against its window), one Stop everywhere (the red square is drawn by CSS and the markup carries the word only; the Stopped card has no Stop at all).

Not renderable (read from code and tests instead): the menu bar menu rows (`buildKnackMenuEntries`: status line, one thing needs you, Open Knack, Ask Knack, Hey Knack line when blocked, Listen for Hey Knack, Pause for 1 hour, Stop everything, Settings, Quit Knack) and the Dock menu (`buildDockMenuTemplate`: Needs you (n), Pause for 1 hour, Stop everything; Resume replaces each when paused or stopped).

## Permission paths (code and tests)

Microphone: `permissions.requestMicrophone()` (askForMediaAccess) through the first-run Allow row; a refused one shows "Turned off in System Settings" with Open System Settings (`permOpen`), and now re-arms the listener on return. Speech recognition: asked by the listener (`arm()`), shown from the listener's own status; refused, it shows the same button. Screen recording: one forced capture probe on the Allow row only (`requestScreen`), `needsRestart` shown as a plain note. Accessibility: never asked at first run (only after the first supervised test). Every missing permission ends on a card or a status line with a button, never silence: `wake/texts.ts` (`blocked_mic_denied`, `blocked_speech_denied`, `blocked_on_device_unavailable`, `mic_permission`, `screen_recording`, `click_accessibility`, `click_screen_recording`), pinned by `controller.test.ts` ("every capability that cannot work answers with a card and a button", "a blocked listener and a click that cannot run say so on a card").

## Hey Knack end to end with offline fakes

`controller.test.ts` and `tasks.test.ts` (all pass): the words heard, the first-wake voice card and screen card (only a real click answers; a key, a closed card and a timeout answer nothing), the `start_task` tool with a fake task service (consent card with Allow for this task, Not now and More; nothing posted without a click; Started. and Done. lines; More shows the wider option; a refused consent and a failed job say so), Stop everything closing a task card and refusing every wake until Resume. The picture run adds the real window path: the card pages, the sizes, the trusted-click rule. Needs the owner's Mac (not testable here): the real microphone, the recogniser, the macOS prompts.
