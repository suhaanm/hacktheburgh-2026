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

## Insight screens, worker (Growth)

Growth is the one worker page for personal insight: My progress, then Where my time goes, My steps against an experienced worker's, How my routines connect and, for programmers, My commits, one under the other with no extra navigation. Each section is a quiet title, ONE headline sentence built by code from the worker's own data, and the numbers behind one closed disclosure. A worker sees only their own work and ONE unnamed experienced worker's way of doing the task (`docs/knack-ux/views.md`). Nothing here consents, approves or sends anything.

| Setting | Default | Why | Change it |
|---|---|---|---|
| Which section is open | none; the address opens one (`#/growth?section=time`, `steps`, `map`, `commits`) and scrolls to it. The old routes (week, presence, genome, graph, git) redirect there | a page of five closed disclosures is a page of five sentences; one click opens the numbers | the section's "See the numbers" |
| My commits | shown for the programmer role, and for anyone who follows a link to it; hidden for other roles | commit habits mean nothing to a benefits processor | the role in Settings, "Set up again" |
| Whose data each section reads | the worker's own (the engine's id for them once set up); before that, the built-in example, with the one origin pill saying so | a worker's screen never lists other people, so there is no person picker | not a setting |
| The baseline | one experienced worker, never named, never an average of colleagues, never a count of them. The "Compare with" choice (nearest expert or consensus) is gone from the worker view | the owner's rule (4.1): no cohort, no other learners | not a setting |
| The origin pill | one for the whole page: the engine's origin for My progress, or "Example data" when any section is showing example data; each section's footer says where its numbers came from | one pill per screen (budget); the sentence per section is never behind a hint | not a setting |
| Steps: ribbon and the "Where the time went" rows | the ribbon (the worker and the experienced worker, labelled "You" and "Experienced worker", no ids); the rows list up to four steps that lost the most seconds | the group waterfall is a cohort figure; the worker's own case is what they can act on | the scrubber, "Explain this case" and "Key and more" (closed) |
| Steps: Explain | closed; it auto-runs only on example or mock data, where it costs nothing; with a live engine it is a remembered switch that is off until the worker turns it on (key `understudy-last-explain-auto`) | a live model call is not free and is the worker's choice | "Explain when this opens" inside Explain |
| Time: the week and the hours | your week against an experienced worker's, then the working-hours map; ideas for a calmer week, free hours, whether a background run's window will last, and quiet hours sit in closed rows inside | the headline says the one thing (meeting load against the experienced worker, or the hours you are usually at the machine) | the closed rows |
| Time: the week | the latest week; no week picker | a picker needs the list of people and weeks | not a setting |
| Quiet hours | unchanged from what the worker set; saving one is the worker's own click | a setting the worker owns | "Quiet hours" row inside Time, More |
| Map | closed; the graph draws names only on hover, focus or click | the owner's request 4.13 | "See the map" |
| My progress: the example learner | the first story (improves) when the screen shows example data | any example has to be one of them | "Example learner" inside "About this data" |
| Counts of people | never drawn: the engine's n of a group is replaced by what the screen draws (one case, one week, N commits), and a note that describes how a group was made is dropped | views.md | not a setting |
| Last choices remembered on this device | the opened state is not remembered (the address is the memory); the Explain switch is; the example learner is not | an open section from yesterday is not a preference | |

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

The spec said three clicks and at most 50 words and 4 controls per first-run screen. The owner then asked for the role choice, three consents and a check that the voice and the pointer work. The budgets that follow are the smallest that keep every consent printed whole:

| Where | Clicks to Home with nothing skipped | Note |
|---|---|---|
| Browser tab | 3 | role, capture, Show my week |
| Knack app | 5 | role, capture, screen glances, voice, Show my week |
| With connection chips | one more | Continue, owner choice (D55) |

The consent screen carries one card per consent (title, the consent sentence printed whole, three buttons): about 30 words and 4 controls a card, so about 110 words and 10 controls with three cards. The budget for that one screen is therefore 120 words and 12 controls; the role screen (24 words, 6 controls with Skip) and the check screen stay within 50 and 8. `budgets.json` is the lead's file: the numbers above are the proposal.

## Not changed

Pinned views stay off by default (the sidebar's six rows are a measured budget); turning them on is one switch in Settings. The word "synthetic" is untouched until the owner's scope is confirmed.
