# 09 Hey Knack: wake, voice and click when I say so

Owner's request (7 Nov, about 23:00): "Knack should be activated by the words hey knack, and then it speaks to you while guiding you with annotations and computer use." Owner's answers: listening is on by default (no opt-in step; macOS still asks for the microphone and speech recognition itself); the detector is macOS on-device speech; Knack may click when the owner says so. Decision D52 (listening on by default); the old cloud wake word stays deleted and `UNDERSTUDY_FLAG_WAKE` stays off.

Code: `apps/desktop/src/main/wake/**`, the listener `apps/desktop/native/knack-wake/**` (built by `apps/desktop/scripts/build-wake-helper.sh` into `resources/knack-wake`, not committed), and a few hooks listed at the end.

## What happens, in order

```
 Mac microphone ──▶ knack-wake (child process, on-device speech only) ──▶ {"event":"heard"} ──▶ Knack main process
                                                                                                  │
   guards say dormant? (lock, call, meeting, share, Live open, agent acting, switch off, kill) ◀───┤ no: next step
   first-wake cards (voice, then screen): only a real mouse click answers ◀────────────────────────┤
   helper stopped (microphone released) ─▶ soft chime ─▶ the SAME Live conversation as the talk key, hands-free
   pill: Listening ─▶ Thinking ─▶ Speaking          tools: point_at, clear, show_step, ask_choice, end_session, do_it_for_me
```

The helper prints three kinds of line and nothing else: `ready`, `heard`, and `error` with a code from a closed list. It never prints, stores or logs what it heard, and writes no file. The words live in one variable for one utterance and are matched inside the helper (`Matcher.swift`), so no text crosses to Electron. Electron reads each line with a strict parser: any extra field (a transcript, a path) stops the helper (`protocol`). The helper's audio goes to no model; the egress guard and the ledger are untouched. Live audio after the words is a separate path (the renderer's microphone, the existing gates and ledger), and the listener is stopped before it opens.

## States

| State | When | Menu bar status row (one line) | Corner pill |
|---|---|---|---|
| Listening | the helper is ready and no guard says dormant | Listening for Hey Knack. Stays on this Mac, nothing stored. | none |
| Off | the worker's switch is off, or flag `UNDERSTUDY_X_WAKE=0` | Hey Knack is off | none |
| Dormant, locked | the screen is locked | Not listening while the screen is locked | none |
| Dormant, call or meeting | a call, meeting, screen share, or quiet for an hour | Not listening during a call or meeting | none |
| Dormant, paused or stopped | Pause for 1 hour, or Stop everything | Not listening while Knack is paused / while everything is stopped | none (Stopped card as today) |
| Dormant, working | an agent is acting for the worker | Not listening while Knack works | the working pill |
| Talking | a Live conversation is open | Talking with you now | Listening, Thinking, Speaking, End |
| Starting | the helper is starting or restarting after a transient failure | Starting Hey Knack. | none |
| Blocked | a permission is refused, no on-device speech, no binary | see "When macOS has not granted" | none |

Dormant means the helper process is stopped and the microphone is released, not paused. Guards are code (`guards.ts`) and re-read every 3 seconds and on every change (lock, sleep, kill, settings, Live phase). The menu-bar dot: macOS itself draws its orange microphone indicator in the menu bar whenever any process, including the listener, uses the microphone, so "Knack is listening" is visible to the whole system and cannot be hidden by Knack; Knack adds the status row above and a "Listen for Hey Knack" check item (a tray hook, `TrayModel.wake`). If Track A adds a listening icon variant, `wake.status().listening` is the signal.

## Copy (all fixed, in `texts.ts`; words within the budgets of docs/KNACK_UX.md section 5)

| Where | Title (8 words) | Body (22 words) | Buttons (3 words) |
|---|---|---|---|
| First wake, voice | Talk with Knack? | Your voice goes to a cloud voice model while we talk. Nothing is saved on this Mac. | Yes, Not now, Never |
| First wake, screen | Knack may look at your screen while we talk | A small picture goes to a cloud model about every 5 seconds. Never from private apps. Nothing is saved. | Yes, Not now, Never |
| Click for you | Click for you? | One click on the ringed spot, then it stops. You can press Stop at any time. | Allow once, Cancel |
| Settings row | Listen for Hey Knack | Stays on this Mac. Nothing is stored. | a switch |

The three buttons have equal weight and the same style. "Not now" asks again after a day (voice) or a week (screen); "Never" is never asked again, and "Never" on the voice card also turns the listener off. Only a real mouse click answers a card: the page checks that the browser produced the event from a mouse (`isTrusted`, a pointer of type mouse, a click count), main checks the sender and the card, and the first 600 ms after a card appears ignore clicks. A key, a script, a timer or a spoken word is never an answer. A card that is closed or times out answers nothing: nothing is remembered and nothing opens.

The consent split is deliberate: the owner's answer covers the on-device listener, which stores and sends nothing. Sending the worker's voice to a cloud voice model and sending a picture of the screen are the Live consent (D30) and stay asked once, in a card. If the owner would rather treat saying the words as consent for the voice, change `consentStep` in `settings.ts` (one function).

## When macOS has not granted the permissions

The app starts and runs normally. The listener is only started when no guard says dormant, and it asks macOS for the microphone and Speech Recognition at that moment, so the prompts belong to Knack and appear on the owner's first launch. If either is refused the helper exits with a closed code, is not restarted by itself, and the menu bar says one line:

| Code | Line |
|---|---|
| mic_denied | Hey Knack needs the microphone. Turn it on in System Settings. |
| speech_denied | Hey Knack needs speech recognition. Turn it on in System Settings. |
| mic_restricted, speech_restricted | The microphone / Speech recognition is restricted on this Mac, so Hey Knack stays off. |
| on_device_unavailable | This Mac cannot recognise speech on the device, so Hey Knack stays off. |
| locale_unsupported | Hey Knack does not support this language on the device. |
| no_input_device | No microphone was found, so Hey Knack stays off. |
| binary_missing | Hey Knack is not installed in this build. |
| protocol, crash_loop, spawn_failed, internal, audio_engine_failed, recognizer_unavailable | Hey Knack stopped working. Switch it off and on to try again. |

It never falls back to server recognition: `requiresOnDeviceRecognition` is true, and a locale with no on-device recogniser ends the helper. After the worker fixes a permission in System Settings, switching "Listen for Hey Knack" off and on starts it again.

## How the owner revokes it

1. The switch: menu bar, "Listen for Hey Knack" (or the Settings row once Track C adds it), off. The helper stops at once and the microphone is released.
2. "Never" on the voice card.
3. System Settings, Privacy and Security, Microphone and Speech Recognition: switch Knack off. The helper then exits with a permission code and stays off.
4. `UNDERSTUDY_X_WAKE=0` in `.env`: nothing is created.
5. Delete the data: `wake.json` in the app's data folder holds only the switch, the chime flag and the consent answers.

## What the conversation can do

`point_at(description)`: the existing grounder (the page's DOM first, then the Gemini pointing role through the agent's `/cue/ground` with the gates) returns a box; the overlay draws the ring and the ghost cursor glides to it. It never clicks. `clear()`: takes the ring and cursor away. `show_step`, `ask_choice`, `end_session` as before. `do_it_for_me(description)`: described next. The model's speech here is free-form model audio inside an explicit, bounded conversation (the worker started it; five minutes at most; a spending cap; a quiet half minute ends it); every other spoken line in Knack stays fixed vocabulary. Screen frames go through the existing gates and consent: never from a denylisted app or a secure input, never unattended, held in memory for one call, listed in the ledger without the image.

### The context packet

Every conversation (Hey Knack and the talk key) starts with a code-built packet in its system instruction, and gets changed lines every ten seconds (`context-packet.ts`, `context-source.ts`). It is built in TypeScript because every reading lives in the desktop process; the engine's context routes serve the Python planners. It follows the context library's shape and freshness rules: a reading carries the time it was taken, one older than its limit is dropped and its kind is named under `unknown`. Contents: trigger (wake or key), live models or example data, the Knack screen id (only while the Knack window is focused), the top Home insight id and template id, pending approvals, the running routine and step n of m, the task in progress and the coach step id and zone, the Cue state, the worker's consent words, whether a click can ever happen (`first_supervised_test_pending` or `allowed_after_worker_clicks_allow`), and the closed list of tools with their argument names, types, limits and listed ids. Every value passes a closed grammar (ids match a strict pattern; enums are from fixed lists; counts are whole numbers); nothing from a screen, page, file, name or typed text can enter; a test feeds hostile strings into every field and checks none survives. If a packet cannot be built or would be cut, the session starts with a fixed fallback ("context unavailable, ask the worker what they are working on"). Not yet reported by the shell, so listed as unknown until it is: the top Home insight and the running routine (the dashboard can report them through `window.knackShell.wake.context({ insight, routine })`).

## Click when I say so: fail closed

The model can only ask. `do_it_for_me` rings the thing (as `point_at` does), then asks code. The state machine (`click-machine.ts`, tested) decides; it never clicks.

1. No Live conversation: refused (`no_session`). Already a card or a run: refused (`busy`). Stopped: refused (`killed`). Target not found: refused (`target_not_found`), no card.
2. The rung record `<data dir>/rung_cleared.json` is read. While it is absent, unreadable, malformed, for another rung, from a failed check or has a wrong digest, the answer is `first_supervised_test_pending`, the model says the fixed line "I will show you instead" (the tool message tells it to say exactly that) and keeps guiding with the ring and the ghost cursor. No card.
3. With the record: a corner card, "Click for you?", Allow once or Cancel, with a 20 second timer that means Cancel. Only a real mouse click on Allow is consent. Voice, key and timer are ignored (the request then ends as a Cancel).
4. On Allow the main process asks the agent service for one click at the centre of the ringed box (`POST /desktop/click`, below), which issues the owner's one-time token and RunPermit through the existing `owner_present` flow, starts the countdown with the target app in front, and runs the full pipeline and every real-actuator guard. The kill hotkey and the supervisor stop work throughout; kill from any state closes the card, stops a run and refuses everything until Resume. Never unattended, never a purchase, never a real account. The record clears TextEdit and the sandbox only, until the owner widens it.

The record is written only by the R1 command-line check (`services/agent/understudy_agent/tiers/mac_check.py`, `write_rung_cleared`) after a passing real run with the owner present and the read-back passed; a dry run, a failed or unproven read-back writes nothing. It holds a schema number, the rung, a time, the target, two enums and a digest. The digest catches edits by mistake, not by someone who can run code as the owner. Recommended (gate code, not changed here): add `rung_cleared.json` to `SettingsGuard.check_path`'s protected list so a model-driven run cannot write it.

### What the agent service must provide (contract, not built here)

`POST {agent}/desktop/click`, header `X-Understudy-Token` (data/.token), body `{ "point": {"x": 0..1000, "y": 0..1000}, "grid": 1000, "card_id": "click-n", "consent": "corner_card_click" }`, answer `{ "ok": boolean, "reason"?: string }`. It must: refuse unless `UNDERSTUDY_REAL_ACTUATOR` is armed and the rung record is valid; issue the one-time token and `grant_run_permit` for this request only; require the countdown with the target app in front; convert the 0..1000 point to the target window's pixels after the hit test; run the click through `SafetyPipeline.authorise` and `MacActuator`; read the result back; never accept an unattended or routine caller; and answer 404 until it exists (the desktop then reports `route_missing` and clicks nothing).

## Proposal for the shell machine (Track A owns it; not applied)

Rows to add to `docs/knack-ux/shell-transitions.json` and `shell-machine.ts`, as a proposal only:

| # | Event | Effects |
|---|---|---|
| 19 | `wake_heard` (the helper said heard, the guards allow, consent is in place) | chime; the pill goes to Listening (row 11 with `trigger: wake`); no window moves |
| 20 | `wake_refused` (consent refused or a Live gate said no) | nothing is drawn; the menu bar status row carries one line |
| 21 | `click_card_shown` | a corner card at priority 3 (approval that blocks a request), over the pill; cards are held while it is up |
| 22 | `click_allowed` (real mouse click) | the card closes; the pill says Working with Stop; the window minimises like any real-screen run (row 1) |
| 23 | `click_done` | the check for 2.5 s (row 7) |

Already wired in this branch without a machine change: the pill follows the Live manager (`voice_hold` Listening, Thinking, Speaking; `voice_end` when it closes) through `knack.dispatch`, and the pill's End button ends the conversation (`KnackLateDeps.onVoiceEnd`). The wake cards are an interim window (`renderer/hey-card`, `wake/card-window.ts`) that implements `CardPort` and can be replaced by the corner column by binding `CardPort` to it.

## Hooks outside `wake/`

`main/index.ts` (wake, context hub, pill follow, coach step capture, `onVoiceEnd`), `main/tray.ts` (two rows and `TrayDeps.wake`), `main/default-flags.ts`, `main/feature-flags.ts` (`UNDERSTUDY_X_WAKE`), `main/live/{manager,session,tools,tool-host,ports,ring,prompt,index,electron}.ts` (hands-free entry, wake tools, context, ghost cursor), `main/knack/knack-shell.ts` (`onVoiceEnd`), `preload/knack.ts` and `shared/knack.ts` (`wake` API), `electron.vite.config.ts` (a preload and a renderer entry), `services/agent/.../mac_check.py` (rung record writer). Info.plist usage strings for the packaged app (electron-builder `mac.extendInfo`): `NSMicrophoneUsageDescription` "Knack listens for the words Hey Knack on this Mac. The listening stays on this Mac and nothing is recorded." and `NSSpeechRecognitionUsageDescription` "Knack uses speech recognition on this Mac to hear Hey Knack. It never uses a server for this and keeps no transcript." The helper carries the same two strings embedded in its binary, and needs the `com.apple.security.device.audio-input` entitlement when signed with the hardened runtime.

## Measured (offline strings, not audio)

Matching logic only, on text a recogniser could return. Development set (the matcher was tuned on it): 0 false accepts in 183 ordinary sentences, 0 misses in 31 variants. Held-out set (written after the matcher was frozen; not used for any change): 1 false accept in 159 ordinary sentences (0.63%, 95% Wilson 0.11 to 3.48%), 0 misses in 25 variants (Wilson 0 to 13.3%). Both together: 1 false accept in 342 (0.29%, Wilson 0.05 to 1.64%), 0 misses in 56 variants (Wilson 0 to 6.4%). The held-out false accept is "Hey nack, nack, nack, that is all I hear from this network": a close spelling followed by a comma is accepted at once. Fixing it would spend the held-out set, so it is left and pinned in `corpus.test.ts`. These numbers say nothing about how often a real microphone and recogniser trigger the detector; that needs the owner's first launch and a day of use, and is not measured. The Swift matcher agrees with the TypeScript on the whole corpus in both modes (`parity.test.ts`).
