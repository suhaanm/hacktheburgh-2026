# Defaults

Every default the product ships with, one section per feature, each with the reason and how to change it. A default is as automated as the safety rules allow: nothing here is a consent a person has not clicked.

Settings, Your data, Needs you and Routines come first (Track C), then Hey Knack (the voice track). Hey Knack's row in Settings prints `Default: on.` and shows what `wake.state()` answers; its own rules are in the last section.

Owner request of 8 Nov 2026 (00:15 GMT): enable everything that was off "for the demo", and set every default as automated as possible **inside the safety layers**. This page lists each default Track C's screens show (Settings, Your data, Needs you, Routines), what it was, what it is now, why, and the safety note. A test (`SettingsView.test.ts`, "defaults.md lists every default") keeps this page and the rows in step: each Settings row prints `Default: ...` from `DEFAULTS` in `apps/dashboard/src/screens/Settings/model.ts`.

**Never a default, whatever the request:** auto-granting a consent card (voice, screen frames, capture, folders), auto-approving an action, unattended runs, irreversible actions in an unattended run, any real click before the supervised R1 spike (D30, D52, D56). Those stay off until the worker, or the owner for R1, says otherwise. The code decides these gates, not a setting.

Where a default lives in another track's file, the exact one-line change is given for the lead. Track C does not edit those files.

## Settings

| Setting | Old default | New default | Why | Safety note |
|---|---|---|---|---|
| Use live models | On when a key was found (`useLiveModels: true`); the line did not say so | **On when a key is set**; the row says "On, because a key is set" and prints "Default: on when a key is set." With no key it is off, disabled, and says why | A live model is what makes Watch first, the briefing and Coaching worth having. No key means nothing can be live | Every call goes through the egress guard and the ledger (Your data > What it looked at or sent). Frames still need the worker's consent card and never leave in an unattended run. The switch is disabled while a job runs. No code change needed: already `useLiveModels: z.boolean().default(true)` |
| Interruptions | Balanced (every kind Normal, 10 interrupting notices a day) | **Rarely** (every kind that can change at Quiet, 4 a day): Knack handles what it can and tells you once at a pause | The setting that does the most on its own is the one that interrupts least. Things that need you are counted, held and shown at the next pause instead of popping up | **Stops and blocking approvals are never hidden**: the safety class ignores every mode and the row prints "Stops and blocking approvals always show." A held item that needs you still appears in Needs you and on the badge. The worker can set any group or any single kind louder (More) |
| Coaching | Off (`cueEnabled: false`) | **On** | The coach is the product's second layer. A hint costs nothing and fades as the worker improves | Hints are cards the worker can ignore; the screen is never read for them without the glance consent card; "Quiet for an hour" and the menu bar pause still work |
| Help level | Automatic | **Automatic** (unchanged, not locked) | The level rises and falls with how the worker is doing. A lock is only for someone who wants one | The level is chosen by code from the shadow record, never by a model |
| Show the help level for two seconds | On (engine `level_glance` true) | **On** (unchanged) | It is how a worker learns the level changed | Only when nothing else is on screen and the worker is still |
| Hey Knack | Off in the desktop settings (`wakeEnabled: false`), although D52 says always on | **On**, with the note "Stays on this Mac. Nothing is stored." | Owner decision D52: listening is on by default | On-device recognition only; it fails closed to off with one plain line if on-device recognition is missing; no transcript and no audio are stored; macOS still asks for Microphone and Speech Recognition; voice alone never approves anything. The row shows `wake.state()` as the shell reports it, including why it is quiet |
| Move aside while Knack works | On | **On** (unchanged) | The window gets out of the way while an agent works; the pill shows what it is doing | The window comes back when something needs the worker, and the pill and the Dock icon always bring it back |
| Open at login | Off (`launchAtLogin: false`) | **On** | Routines only run while Knack is open, so a worker who wants routines wants it open | Applies to the packaged macOS app only. Opening Knack starts no run. Every routine still waits for the worker's approval and irreversible steps still need their own opt-in |
| Use my skills | On, nothing turned off (the tasks service's own default) | **On** (unchanged); the row appears once the tasks service answers, with each skill's name and description behind More and its own switch | The skill files already on this Mac are the worker's own; using them costs nothing and makes a task better | Names and descriptions only: a skill's contents are never shown or sent from this screen. A skill can be turned off one by one. A skill never grants a permission: the consent card and the per-run permit decide that |
| Appearance | Auto | **Auto** (unchanged) | Follows the system | None |
| View as | Worker | **Worker** (unchanged) | The worker's own view is the default; Admin is a preview | Admin sees numbers only (Your data > What your admin can see) |
| Pinned views | Off | **Off** (unchanged) | A sidebar choice, not an automation. Three extra items would cost the calm | None |

## Your data

| Setting | Old default | New default | Why | Safety note |
|---|---|---|---|---|
| Learn from when I am active (capture) | Off until the worker turns it on at first run | **Unchanged** | It is a line in the worker's own memory file and is a consent in all but name. The consent text stays printed beside the switch | Times only: no page text, no URLs, no field values |
| Look at my screen when I seem stuck | Off until the consent card is agreed | **Unchanged** | A consent card is never auto-granted (D30) | Frames are held in memory for one call, never stored, only through the egress guard, never from a denylisted app or while secure input is on |
| Also look every 30 seconds | Off | **Unchanged** | Visible only after the first switch is agreed | Each look is listed |
| Skip messaging and mail apps | On | **On** (unchanged) | Safe by default | Nothing is sent while one of them is in front |
| Search my folders | Off, no folders | **Unchanged** | Folders are added only through a native dialog in the main process | Search runs on the worker's own index |

## Needs you and Routines

| State | Old default | New default | Why | Safety note |
|---|---|---|---|---|
| A routine proposal | Waits for the worker, buttons Watch first, Not now, Details | **Unchanged**; Watch first is the first visible action and the one the J3 check measures | The cheapest step that teaches the routine something | Watch first practises on the next cases. Nothing runs, is saved or is sent |
| Autonomy of a new routine | Watch first (shadow) | **Unchanged** | Promotion is earned from the shadow record by code | The model proposes, code decides |
| Run while I'm away | Off per routine | **Unchanged**: one click for a routine with no irreversible step, a typed confirmation for one that has | An unattended run is a per-routine opt-in | Unattended runs never write to a real account, never use frames |
| An approval | Waits for a real click on the card | **Unchanged** | No keystroke and no voice approves | A real click only. After it, the lead's `finalize` call submits the sandbox note and the row says plainly if it did not finish |
| A paused run | Waits | **Unchanged** | A pause is a safety stop | Shown and counted whatever the Interruptions setting is |

## What the lead needs to change (one line each)

1. `services/engine/understudy_engine/attention/state.py` line 29: `budget_per_day: int = 10` to `4`, and line 84: `return self.modes.get(type_id, "normal")` to `"quiet"` (the safety row on line 83 still returns the fixed row, so stops and blocking approvals are unchanged). Engine tests that assert the Balanced default (`tests/attention/test_service.py`, `test_routes.py`) change with it. Until then the row shows whatever the engine answers and prints "Default: Rarely."
2. `apps/desktop/src/shared/settings.ts` line 49: `cueEnabled: z.boolean().default(false)` to `.default(true)` (the env gate `UNDERSTUDY_X_CUE=1` still has to be set).
3. `apps/desktop/src/shared/settings.ts` line 41: `wakeEnabled: z.boolean().default(false)` to `.default(true)`, or have the shell report `switchOn: true` when the worker has never chosen (D52).
4. `apps/desktop/src/shared/settings.ts` line 62: `launchAtLogin: z.boolean().default(false)` to `.default(true)`.

Nothing here makes a model decide anything, and nothing here changes a gate: the eight security layers, the consent cards, the per-run permit and the supervised R1 spike are as they were.

## Hey Knack

| Setting | Default | Why | Change it |
|---|---|---|---|
| Listen for Hey Knack | **On** (owner, D52) | The listener runs on this Mac only (macOS on-device speech): it has no network, no model, stores nothing and writes no file. So it needs no opt-in and no live models; it runs with example data too. | Menu bar, "Listen for Hey Knack"; Settings; `UNDERSTUDY_X_WAKE=0`; or "Never" on the first card |
| Listener runs when | always, except the guards below | Silence is the default; the listener is stopped, not paused, so the microphone is released | |
| Listener stops while | the screen is locked, the Mac sleeps (and 2.5 s after it wakes), a call, a meeting, a screen share, quiet for an hour, Pause for 1 hour, Stop everything, a voice conversation is open, an agent is acting for you | privacy and one voice at a time | not a setting: code |
| Wake phrase | "Hey Knack" (and "hay", and close spellings such as "nack" and "nac", and "knock" only when a request follows) | a closed accept list, measured offline (docs/knack-ux/09-wake-voice.md) | not a setting |
| Conversation starts | hands-free: after the words you just talk, no key held | the owner's request | the talk key (hold Option-Space) still works as before |
| Soft chime | **On** | "I heard you" before the model speaks; the pill also says Listening | the chime is `wakeChime` in wake.json |
| Live voice | **On** once you click Yes on the first card ("Talk with Knack?") | sending your voice to a cloud voice model is a consent a real click gives; it is never granted for you | Never, or Pause for 1 hour; or turn Live off in Privacy |
| Knack looks at your screen while you talk | **Off** until you click Yes on the second card ("Knack may look at your screen while we talk") | a picture of your screen leaves the Mac; never from a denylisted app or a password field, never unattended | the card asks again after a week if you said Not now; never if you said Never |
| The two cards | asked once, on the first wake, in this order; a real mouse click each; equal buttons (Yes, Not now, Never) | D30: frames and voice leave the Mac only with your consent | Settings, Your data |
| The conversation ends | on a goodbye, after about 30 s of quiet, after 5 minutes, on Stop or Stop everything, or at a spending limit | bounded by design | the limits are in Live settings |
| Click for you | **Off** until the first supervised test (R1) has passed and written `rung_cleared.json`; then asked every time with Allow once or Cancel | the owner's rung-by-rung rule | not a setting: code; the kill hotkey works throughout |
| Words the model speaks | free-form model audio, only inside the conversation you started | the owner's request | |
| Words Knack speaks otherwise | fixed lines only | one voice, no surprises | |
| When live voice cannot start (example data, no key, the service not answering, the microphone not allowed) | Knack still hears the words and shows a card in plain words, with a button to Settings where it helps | never silence | |
| Where it keeps things | `wake.json` in the app's data folder: the switch, the chime, your two answers. Nothing else | | delete the file |
