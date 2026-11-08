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

## Insight screens, admin

The Admin screens (Firm, Roles, People, Onboarding, Automation, Risk, Forecasts, Brief) open insight first: one headline sentence built by code, at most one simple chart or short list, and the numbers behind one closed "See the numbers". They only read. Nothing on them sends, books, approves or changes anything, so no default here is a consent.

| Setting | Default | Why | Change it |
|---|---|---|---|
| Where an admin lands | Firm (the overview), when the address names nothing | the shell's rule for the Admin view | the Admin sidebar |
| Forecasts: which card shows its evidence | the first card (the surest one) is open, with its interval and its one chart; the other two are closed | one chart above the fold keeps the screen within its word budget, and the surest insight is the one to read first | the chevron on a card opens or closes its evidence; the choice is not remembered, because the cards change with the data |
| Forecasts: which insights, and in what order | up to three, chosen by code: onboarding speed, the junior and expert gap, repeated work, the trend mix; the surest first (Likely, then Possible, then Too early to say), ties in that order | the model proposes, code decides: every sentence is a fixed template filled from the answers the other Admin screens read | not a setting |
| The confidence word | Likely: n of at least 10 and an interval that clears zero and is not wide. Possible: n of 5 to 9, or a wide interval. Too early to say: n under 5, no interval, or an interval that includes no change | one word for how far the data supports a sentence; an interval across zero is never read as a direction | printed once in "How reliable are these forecasts?" |
| Automation: the window | 7 days; the last window the admin chose is remembered on this device (key `understudy-last-firm-automation-window`) | a week is the rhythm of repeated work | the 7 days and 30 days buttons |
| People: order and filter | by name, A to Z, everyone shown; never a score, never a rank | for coaching and onboarding, not for evaluating individuals | "Sort and filter" inside "See the numbers" (name or time in role; one trend class) |
| People: the role groups | closed; the first two people of a group show when it opens, "Show all N" shows the rest | an opened group stays a few scannable rows | the group's summary line |
| The smallest group a figure may describe | 5 people | the privacy threshold; a smaller group is merged or left out and the page says so | not a setting (the engine merges small groups too) |
| Old or future numbers | numbers more than 14 days old, or dated after today, say so in one line under the headline; example data never shows that line, it carries its own note | an old number must not pass for a fresh one; an example's date is not a claim | not a setting |
| The month in a forecast | the month 28 days ahead of the clock; no month when the clock cannot be read | "expect 3 new starters to need coaching through December" needs a date to mean anything | not a setting |
| Firm brief | headline first on screen; the A4 page is in the page but only the printer sees it, so "Print the brief" is one click and prints the same page whatever is open | a printable page must not depend on what is expanded | the browser's print dialog saves it as a PDF |
| Firm: which insight is open | none; the palette opens one with `?insight=` | an opened insight adds a table and a chart above the fold | the row opens in place |
| Origin, use limit, n and the interval | always printed: the origin pill and the use limit in the head, n on every card and row, the interval in the chart's line, the headline's line or the table | never behind a hint | not a setting |

