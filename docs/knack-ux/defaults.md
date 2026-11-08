# Defaults

Every default the product ships with, one section per feature, each with the reason and how to change it. A default is as automated as the safety rules allow: nothing here is a consent a person has not clicked.

## Hey Knack (WAKE-VOICE)

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

## Shell, Home and first run (SHELL-WEB)

The owner asked (8 Nov, 00:15) for every toggle and state to be as automated as possible inside the safety layers. These are the defaults the shell, Home and first run choose, and the lines they never cross.

## Never automated (a real click is the only way in)

- A consent: capture, screen glances, voice, a connection. First run shows each as a card with Yes, Not now and Never of one size and one weight; none is pre-selected, none is answered by a timer, a key or a default. Unanswered means asked once, later, in context.
- An approval, a "Resume the run", a "Run while I'm away", anything irreversible or outward. No keystroke approves (`keys.test.ts`).
- A macOS permission: the page shows the state and offers Allow or Open System Settings; macOS shows its own prompt; the worker answers there.

## Automated, with the reason

| Default | Where | Reason |
|---|---|---|
| First run opens by itself on the first launch of the Knack app on this Mac, whatever identity the engine already has | `shouldStartFirstRun` (`inApp`) | A seeded example worker must not skip the role choice (owner, 00:45). A browser tab keeps the old rule. A deep link is never hijacked; a session that showed it once does not show it again (Back is not a trap). |
| The role pack's safe defaults are written when the consent screen is done: its tools, risky actions "never without me", short tone, gradual pace, its hours | `defaultAnswers` | Five questions the worker would answer the same way become zero clicks; all of it is editable in Your data. |
| "Not sure yet" and every Skip pick nothing; nothing is written | `NO_ROLE`, `skip` | Skipping must never cost the worker a choice they did not make. |
| The last consent answer advances to the next screen | `advance` | One click fewer; the cards still need real answers. |
| An unfinished first run resumes where it stopped | `parseProgress` | A closed window must not send the worker back to the start. Strict read: anything unexpected starts again from the top. |
| First run tells the shell it is open (`firstRun: true`) so the Hey Knack listener does not prompt at launch; it is told when first run ends | `wakeContext` | The first microphone prompt belongs to the moment the worker said Yes. |
| Admin view is remembered on this device; an admin lands on Firm | `viewAs.ts`, `App.tsx` | The owner's walk-through should not repeat the switch. It is a view, not a permission. |
| The sidebar badge, the Home row and the corner count read one number | `refreshNeedsBadge` | Three numbers that disagree look like a bug. |
| Home chooses its hero by fixed rules: a blocking approval or a safety pause first, then the best pointer | `blockingItem` | Something the worker must decide outranks something they could learn. |

## Click and word budgets for first run (reasons for the change)

The spec said three clicks and at most 50 words and 4 controls per first-run screen. The owner then asked for the role choice, three consents and a check that the voice and the pointer work. The lead's decision D64 sets the consent screen at 90 words and 10 controls above the fold (budgets.json and qa/knack/budgets.json). The screen now measures 89 and 10 in the app (and 40 and 5 in a browser tab): one title and one plain sentence per consent, three buttons of one size, no repeated explanation.

| Where | Clicks to Home with nothing skipped | Note |
|---|---|---|
| Browser tab | 3 | role, capture, Show my week |
| Knack app | 5 | role, capture, screen glances, voice, Show my week |
| With connection chips | one more | Continue, owner choice (D55) |

Each card says in its sentence what Yes does and what leaves the Mac (a picture of the screen goes to a model and is never saved; talking sends the voice to a model); the longer consent text of the desktop app is printed under Your data, beside the switch it belongs to. To keep ten controls, Back is left out on the three-card screen (Skip stays). The role cards say how far each pack is built (Fully built and validated, Full pack, Starter).

## Not changed

Pinned views are retired: a worker has five rows and nothing else (docs/knack-ux/views.md). The Account menu keeps Appearance out (it is in Settings). A name is kept on this Mac (the engine holds it as one line the worker can read and delete under What Knack remembers); a role change keeps the person, the name and the capture choice.
