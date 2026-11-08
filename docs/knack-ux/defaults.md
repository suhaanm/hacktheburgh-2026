# Defaults

Every default the product ships with, one section per feature, each with the reason and how to change it. A default is as automated as the safety rules allow: nothing here is a consent a person has not clicked.

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

## Desktop

The app around the dashboard: the window, the Dock icon, the menu bar item, the corner column, the background pills, the Ask bar, the services it starts. Everything here is as automatic as the safety rules allow. Nothing in it answers a consent card, approves anything, or turns on anything unattended or irreversible: those stay a real click, per card or per routine.

| Setting or state | Default | Why | Change it |
|---|---|---|---|
| Open at login | **On** (owner, 8 Nov). Only a packaged macOS build registers the login item; a login launch shows no window, only the Dock icon and the menu bar item | Knack is there when work starts | Settings; the menu bar item is not needed |
| Show in the Dock | **On** | a normal macOS app: click the icon to bring the window back | Settings |
| Show in the menu bar | **On** | the eight-row menu: status, Open, Ask, Pause, Stop everything, Settings, Quit | Settings |
| Move aside while Knack works | **On** | the window minimises 0.4 s after a run that uses your real screen starts, and does not come back unless something needs you or you click the pill or the Dock icon | Settings (Move aside while Knack works) |
| Keep the Mac awake while Knack works | **On** | a run that is minimised behind your other windows still needs the machine to stay up. A power-save blocker is held only while a run works (the app alone, plus the display while the run uses your real screen), released the moment it ends, when you switch this off, and when the app quits. Nothing is held between runs | Settings; `keepAwakeWhileWorking` |
| Cue (the coach cards) | **On**, balanced, spoken cues off | on by the owner's request; it never draws over a corner card, a password field or a denylisted app, and it asks nothing | Settings, Cue; "Quiet Cue for an hour" |
| Help level | **Automatic** | the level follows how you are doing; lock it if you want | Settings (Help level) |
| Live models | **On when a key exists**: real models when a Gemini key is in the environment or the repository's `.env` and the models boot check passes, else example data with the one line "Running with example data" | the app decides at start, with no question | Settings, Use live models (restarts the app, about 20 s); costs real money per run, so only this switch changes it |
| Finding the services | **Automatic**: the app looks for the engine and the agent on their ports; if both answer it attaches and never stops them; otherwise it starts what is missing as its own children and stops only those on quit | no setup, and a stack someone else started is left alone | `KNACK_REPO`, `KNACK_LIVE`, `KNACK_SITES=0` |
| A service that stops by itself | started again, 2 s then 4 s then 8 s later, three times in ten minutes; after that one plain sentence and Try again | a crash should not need you | Try again |
| A port that something else holds | said at once in plain words before anything starts ("Another program is using a port Knack needs") | the alternative is a service that fails inside | quit the program, or set `ENGINE_PORT` and `AGENT_PORT` |
| The corner pill | shown while a run works (five words at most, "n of m" only when there are two or more steps, Stop), a quiet check for 2.5 s when it ends, held on an error until you open Knack; never over a password field, a denylisted app or a shared screen | one status in one place | not a setting |
| A run that left something to approve | one card above the pill (Review, Later); Review opens Needs you and nothing is approved by it | a real click on the approval itself is the only approval | not a setting |
| A pill that outlives its work | cleared 3 s after the agent service says nothing is acting; a run record older than 15 minutes is a ghost (a dead process left it) and is never shown | the pill must never say working about nothing | not a setting |
| Background agent pills (top right) | **On**: one small pill per task or run working in the background, a moving icon only while it runs, a still dot while it waits for an OK, a quiet check that fades after 5 s, a red dot for a failure that stays until clicked, at most four and then "+n"; a click opens Routines at the task | the owner's request; the bottom-right column stays for Knack's own attention | not a setting |
| Permission prompts | a corner card (bottom-right, above the pill column), the answer is a real click; plus one native notification | nothing else uses a notification | `confirmStyle` (card or inside the panel; no screen for it in the app yet) |
| Notifications | only the one native notification for a permission prompt. No banner for cards, runs or results | the spec: a banner cannot be non-focusable or carry Stop | not a setting |
| The Ask bar | **On**: Option-Space tapped opens it (hold still talks), the menu bar row opens it, Escape or a click elsewhere closes it. A line goes into a voice conversation that is already open; otherwise it says one plain sentence and stays, because typed chat has no model behind it in this build | one small place to type | `talkHotkey` |
| The old side panel and its eight-step set-up | **Never shown in the app**: its flag is pinned done, nothing raises the panel; the one onboarding is the first run in the Knack window, and Set up again is in the app menu | one onboarding | not a setting |
| First launch with no key | example data, one line, nothing asked | nothing blocks the first look | add a key to `.env` |
| Quit | with nothing running, quits at once; with a run, one sheet ("Knack is working. Stop it and quit?" Stop and quit, Keep working) | never a surprise stop | not a setting |
| Window size and place | 80 percent by 84 percent of the work area (960 to 1440 by 600 to 1000), remembered per display; a window left off every display after one is unplugged is brought back | a window you cannot find is a bug | drag it |
| Hey Knack, the two consent cards, Click for you | see the Hey Knack section: never answered for you | the safety rules | |
