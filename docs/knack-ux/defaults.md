# Defaults

Every default the product ships with, one section per feature, each with the reason and how to change it. A default is as automated as the safety rules allow: nothing here is a consent a person has not clicked.

Settings, Your data, Needs you and Routines come first (Track C), then Hey Knack (the voice track). Hey Knack's row in Settings shows what `wake.state()` answers (it prints no default); its own rules are in the last section.

Owner request of 8 Nov 2026 (00:15 GMT): enable everything that was off "for the demo", and set every default as automated as possible **inside the safety layers**. This page lists each default Track C's screens show (Settings, Your data, Needs you, Routines), what it was, what it is now, why, and the safety note. A test (`SettingsView.test.ts`, "defaults.md lists every default") keeps this page and the rows in step: the values are `DEFAULTS` in `apps/dashboard/src/screens/Settings/model.ts`. Since 8 Nov 2026 (05:00, owner) no Settings row prints "Default: X"; the values still apply and this page is where they are written down.

**Never a default, whatever the request:** auto-granting a consent card (voice, screen frames, capture, folders), auto-approving an action, unattended runs, irreversible actions in an unattended run, any real click before the supervised R1 spike (D30, D52, D56). Those stay off until the worker, or the owner for R1, says otherwise. The code decides these gates, not a setting.

Where a default lives in another track's file, the exact one-line change is given for the lead. Track C does not edit those files.

## Settings

| Setting | Old default | New default | Why | Safety note |
|---|---|---|---|---|
| Use live models | On when a key was found (`useLiveModels: true`); the line did not say so | **On when a key is set**; the row says "On, because a key is set" (no row prints a default). With no key it is off, disabled, and says why | A live model is what makes Watch first, the briefing and Coaching worth having. No key means nothing can be live | Every call goes through the egress guard and the ledger (Your data > What it looked at or sent). Frames still need the worker's consent card and never leave in an unattended run. The switch is disabled while a job runs. No code change needed: already `useLiveModels: z.boolean().default(true)` |
| Interruptions | Balanced (every kind Normal, 10 interrupting notices a day) | **Balanced** (unchanged): the engine's own default | This is the policy that was evaluated on held-out data (evals/attention, 11 of 12 criteria). Changing the engine default would change the product away from what was measured. "As automated as possible" is about the system doing more on its own, not about fewer interruptions: the worker can pick Rarely or Often in one click | **Stops and blocking approvals are never hidden**: the safety class ignores every mode and the row prints "Stops and blocking approvals always show." A held item that needs you still appears in Needs you and on the badge. Any group, or any single kind, can be set louder or quieter (More) |
| Coaching | Off (`cueEnabled: false`) | **On** (already true on main) | The coach is the product's second layer. A hint costs nothing and fades as the worker improves | Hints are cards the worker can ignore; the screen is never read for them without the glance consent card; "Quiet for an hour" and the menu bar pause still work |
| Help level | Automatic | **Automatic** (unchanged, not locked) | The level rises and falls with how the worker is doing. A lock is only for someone who wants one | The level is chosen by code from the shadow record, never by a model |
| Show the help level for two seconds | On (engine `level_glance` true) | **On** (unchanged) | It is how a worker learns the level changed | Only when nothing else is on screen and the worker is still |
| Hey Knack | On (its switch lives in the wake store; the old desktop flag `wakeEnabled` is a legacy flag and is not used) | **On** (unchanged), with the note "Stays on this Mac. Nothing is stored." | Owner decision D52: listening is on by default | On-device recognition only; it fails closed to off with one plain line if on-device recognition is missing; no transcript and no audio are stored; macOS still asks for Microphone and Speech Recognition; voice alone never approves anything. The row shows `wake.state()` as the shell reports it, including why it is quiet |
| Move aside while Knack works | On | **On** (unchanged) | The window gets out of the way while an agent works; the pill shows what it is doing | The window comes back when something needs the worker, and the pill and the Dock icon always bring it back |
| Open at login | Off (`launchAtLogin: false`) | **On** (already true on main) | Routines only run while Knack is open, so a worker who wants routines wants it open | Applies to the packaged macOS app only. Opening Knack starts no run. Every routine still waits for the worker's approval and irreversible steps still need their own opt-in |
| Use my skills | On, nothing turned off (the tasks service's own default) | **On** (unchanged); the row appears once the tasks service answers, with each skill's name and description behind More and its own switch | The skill files already on this Mac are the worker's own; using them costs nothing and makes a task better | Names and descriptions only: a skill's contents are never shown or sent from this screen. A skill can be turned off one by one. A skill never grants a permission: the consent card and the per-run permit decide that |
| Longest a task runs | 30 minutes (the tasks service's own default; shown once the service says it) | **30 minutes** (unchanged), choices 5 to 120 | A task that has not finished in half an hour is usually stuck; the worker can raise it for one that needs longer | A hard cap the service enforces: a task is stopped by code at that time, whatever the model says |
| Most a task may spend | US$2 (the tasks service's own default; shown once the service says it) | **US$2** (unchanged), choices US$0.50 to US$20 | A task that costs more than a coffee is a task the worker should have chosen to allow | A hard cap the service enforces: a task is stopped by code when it reaches it (it finishes as failed, with its partial work still openable) |
| Appearance | Auto | **Auto** (unchanged) | Follows the system | None |
| View as | Worker | **Worker** (unchanged) | The worker's own view is the default; Admin is a preview | Admin sees numbers only (Your data > What your admin can see) |

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

## Settled by the lead (8 Nov, after the checkpoint)

- **Interruptions stay Balanced.** The engine's default is the evaluated policy (evals/attention), so no engine change is made and the Settings row shows Balanced pressed (no row prints a default). (`DEFAULTS` in `apps/dashboard/src/screens/Settings/model.ts`, kept in step with this page by `SettingsView.test.ts`).
- **No other engine or desktop change is needed.** Coaching (`cueEnabled`) and Open at login (`launchAtLogin`) are already true on main. Hey Knack's switch lives in the wake store and is on by default; the old `wakeEnabled` in `apps/desktop/src/shared/settings.ts` is a legacy flag and is left alone.

Nothing here makes a model decide anything, and nothing here changes a gate: the eight security layers, the consent cards, the per-run permit and the supervised R1 spike are as they were.

## Hey Knack
## Hey Knack (WAKE-VOICE)

| Setting | Default | Why | Change it |
|---|---|---|---|
| Listen for Hey Knack | **On** (owner, D52) | The listener runs on this Mac only (macOS on-device speech): it has no network, no model, stores nothing and writes no file. So it needs no opt-in and no live models; it runs with example data too. | Menu bar, "Listen for Hey Knack"; Settings; `UNDERSTUDY_X_WAKE=0`; or "Never" on the first card |
| Listener runs when | always, except the guards below | Silence is the default; the listener is stopped, not paused, so the microphone is released | |
| Listener stops while | the screen is locked, the Mac sleeps (and 2.5 s after it wakes), a call, a meeting, a screen share, quiet for an hour, Pause for 1 hour, Stop everything, a voice conversation is open, an agent is acting for you | privacy and one voice at a time | not a setting: code |
| Wake phrase | "Hey Knack" (and "hay", and close spellings such as "nack" and "nac", and "knock" only when a request follows) | a closed accept list, measured offline (docs/knack-ux/09-wake-voice.md) | not a setting |
| Conversation starts | hands-free: after the words you just talk, no key held | the owner's request | the talk key (hold Option-Space) still works as before |
| Soft chime | **On** | "I heard you" before the model speaks; the pill also says Listening | the chime is `wakeChime` in wake.json |
| Live voice | **Switched on by default** (`liveEnabled` is true); a conversation still opens only after your click on the card (Yes, allow both, or Voice only) | the switch is not the consent: the consent record (`liveConsentVersion`) is written by the click alone, and nothing opens while it is 0. Sending your voice to a cloud voice model is a consent a real click gives; it is never granted for you | Never, or Pause for 1 hour; or turn Live off in Privacy |
| Knack looks at your screen while you talk | **Off** until you click Yes, allow both on the one card (`liveFrames` stays false until that click; Voice only leaves it off and asks again after a week) | a picture of your screen leaves the Mac; never from a denylisted app or a password field, never unattended | Settings, Your data; the card asks again after a week if you chose Voice only or Not now; never if you chose Never |
| The yes card | **One card, "Talk with Knack?"**, two clear lines (Voice, then Screen) and four buttons of one weight: Yes, allow both / Voice only / Not now / Never. A real mouse click only (the existing real-click check). It shows at the first Hey Knack, at the first talk-key press, once right after first run, and from Check voice (row "Your yes", button "Show the card"). When only one of the two is due (the other was answered earlier) only that one's single card shows | D30: frames and voice leave the Mac only with your consent. Nothing is pre-answered, auto-answered or scripted: the defaults hold no yes, and a key, a timer or a closed card is no answer | Settings, Your data; Check voice shows it again after Never or Not now |
| The conversation ends | on a goodbye, after about 30 s of quiet, after 5 minutes, on Stop or Stop everything, or at a spending limit | bounded by design | the limits are in Live settings |
| Click for you | **Off** until the first supervised test (R1) has passed and written `rung_cleared.json`; then asked every time with Allow once or Cancel | the owner's rung-by-rung rule | not a setting: code; the kill hotkey works throughout |
| Words the model speaks | free-form model audio, only inside the conversation you started | the owner's request | |
| Words Knack speaks otherwise | fixed lines only | one voice, no surprises | |
| When live voice cannot start (models off, no key, the service not answering, the microphone not allowed) | Knack still hears the words and shows a card in plain words. When the Use live models switch is on and only the model service could not be reached the card says so ("Knack could not reach the model service. It keeps trying and will switch on by itself."); the Settings wording is shown only when the switch is really off | never silence, never a wrong reason | |
| Where it keeps things | `wake.json` in the app's data folder: the switch, the chime, your two answers. Nothing else | | delete the file |

## Insight screens, worker (Growth)

Growth is the one worker page for personal insight: My progress, then Where my time goes, My steps against an experienced worker's, How my routines connect and, for programmers, My commits, one under the other with no extra navigation. Each section is a quiet title, ONE headline sentence built by code from the worker's own data, and the numbers behind one closed disclosure. A worker sees only their own work and ONE unnamed experienced worker's way of doing the task (`docs/knack-ux/views.md`). Nothing here consents, approves or sends anything.

| Setting | Default | Why | Change it |
|---|---|---|---|
| Which section is open | none; the address opens one (`#/growth?section=time`, `steps`, `map`, `commits`) and scrolls to it. The old routes (week, presence, genome, graph, git) redirect there | a page of five closed disclosures is a page of five sentences; one click opens the numbers | the section's "See the numbers" |
| My commits | drawn only for the programmer role; for every other role the section is not on the page at all, even when the address (the old #/git) names it. A programmer with no repository yet reads "Commits appear once a repository is connected." | commit habits mean nothing to a benefits processor or an analyst, and nothing recorded yet is a state, never an error phrase | the role in Settings, "Set up again" |
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
| The Ask bar | **On**: Option-Space tapped opens it (hold still talks), the menu bar row opens it, Escape or a click elsewhere closes it. A line goes into a voice conversation that is already open; otherwise Return makes it a task (source typed) through the agent service on this Mac: a card asks first, a real mouse click only, equal buttons, More for Allow everything for this task; a question about the request is a card of options; Started. and Done. appear on small cards (nothing is spoken for a typed task); an answered question appears on a card, Your answer. When it cannot be taken the bar stays open with the text kept and one plain sentence (too many tasks, everything stopped, the service not answering) | one small place to type | `talkHotkey` |
| The old side panel and its eight-step set-up | **Never shown in the app**: its flag is pinned done, nothing raises the panel; the one onboarding is the first run in the Knack window, and Set up again is in the app menu | one onboarding | not a setting |
| First launch with no key | example data, one line, nothing asked | nothing blocks the first look | add a key to `.env` |
| Quit | with nothing running, quits at once; with a run, one sheet ("Knack is working. Stop it and quit?" Stop and quit, Keep working) | never a surprise stop | not a setting |
| Window size and place | 80 percent by 84 percent of the work area (960 to 1440 by 600 to 1000), remembered per display; a window left off every display after one is unplugged is brought back | a window you cannot find is a bug | drag it |
| Hey Knack, the two consent cards, Click for you | see the Hey Knack section: never answered for you | the safety rules | |
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

The spec said three clicks and at most 50 words and 4 controls per first-run screen. The owner then asked for the role choice, three consents and a check that the voice and the pointer work. The lead's decision D64 sets the consent screen at 90 words and 10 controls above the fold (budgets.json and qa/knack/budgets.json). The screen now measures 89 and 10 in the app (and 40 and 5 in a browser tab): one title and one plain sentence per consent, three buttons of one size, no repeated explanation.

| Where | Clicks to Home with nothing skipped | Note |
|---|---|---|
| Browser tab | 3 | role, capture, Show my week |
| Knack app | 5 | role, capture, screen glances, voice, Show my week |
| With connection chips | one more | Continue, owner choice (D55) |

Each card says in its sentence what Yes does and what leaves the Mac (a picture of the screen goes to a model and is never saved; talking sends the voice to a model); the longer consent text of the desktop app is printed under Your data, beside the switch it belongs to. To keep ten controls, Back is left out on the three-card screen (Skip stays). The role cards say how far each pack is built (Fully built and validated, Full pack, Starter).

## Home: the task box is its second job (decision D66)

Home's budget was 50 words and 5 controls for one sentence and one action. The owner then asked for a text box on Home ("What should Knack do?", with Enter to send and a microphone where the desktop can listen) and a short list of background tasks, so the budget is now 70 words and 6 controls (docs/knack-ux/budgets.json and qa/knack/budgets.json together). Measured in example data: 59 words and 6 controls at 1440 by 900, 1152 by 735 and 390 by 844; against the owner's live engine: 42 words and 3 controls. Three things keep it that small:

- The examples under the box appear only while the box has focus and is empty (they fill the box and never send), and Send appears only once there is something to send.
- A pause for safety no longer takes thirty words: the hero says the first sentence of what happened, then a fixed line ("Paused for safety. Nothing more happens until you choose."), and the engine's own account of the rest waits behind Evidence. What was paused and that nothing happens without the worker stay printed.
- The background tasks list is at most three lines and draws nothing when no task is going.

## Not changed

Pinned views are retired: a worker has five rows and nothing else (docs/knack-ux/views.md). The Account menu keeps Appearance out (it is in Settings). A name is kept on this Mac (the engine holds it as one line the worker can read and delete under What Knack remembers); a role change keeps the person, the name and the capture choice.


## Voice and screen help (VOICE-DEFAULTS, 8 Nov 2026)

Owner requests: "it still tells me that voice needs live models", and keep voice and screen features on by default, with the macOS permissions shown as the next step. What each default is, and what stays a click.

| Setting | Old | New | Why | Safety note |
|---|---|---|---|---|
| Models boot check | One check with an 8 s limit, tried twice; the result decided the whole session | Three attempts with limits of 8, 10 and 12 s and a 0.7 s pause (a failure that comes at once delays the start by about 1.4 s) | A busy Mac or a slow first connection must not switch the models off for the session | The key is only tested for being there; the check sends no content |
| Models off only because the service could not be reached | Final for the session | The app keeps checking every 20 s for as long as it runs, and when the service answers and nothing is running it says one calm line and reopens itself once (never twice within 15 minutes) | The worker should not have to do anything | It never reopens over a running job (a task, a run, a voice conversation) or while Stop everything is on; the environment is put back before the reopening |
| Voice switched on (`liveEnabled`) | Off until the card | **On** | Voice features on by default wherever the rules allow | Not the consent: with the consent record at 0 nothing opens. The record is written only by the worker's click on the card |
| Looking at the screen while talking (`liveFrames`) | Off | **Off** (unchanged) | A picture leaves the Mac, so it needs the click. The card's first button, Yes, allow both, turns it on in one click | Never turned on by a default or a script |
| The yes card | Two cards, one after the other | One card (see Hey Knack above), also shown right after first run and from Check voice | Remove friction, never silently missing | A real click answers it; a yes is never pre-answered |
| Listen for Hey Knack | On | **On** (unchanged) | D52 | On-device only |
| Screen Recording | Never asked; Knack was not listed in System Settings | Asked first, like the microphone: the button Allow screen help (the worker's click) makes macOS ask once, then opens Privacy and Security, Screen Recording; macOS applies it after Knack is reopened, and the cards say so | A frame cannot be taken without it | Only the worker can switch it on |
| Permissions in Settings | Rows only in Check voice | A Permissions block: Microphone, Speech recognition, Accessibility and Screen recording, each On or Off with one button (Allow, or Open System Settings) | One place to see and fix them | Read only; a button is a click and macOS is where the grant is made |
| Permissions in first run | Rows per consent | Two steps: Allow voice (Microphone, then Speech Recognition) and Allow clicking and screen help (Accessibility, then Screen Recording, with Open System Settings) | The owner's words | Each ask is the worker's click |
| Frames wanted but not sendable | Skipped without a word | Said once per conversation on a card and by a closed code (Screen Recording missing, a private app, a password field, a locked or shared screen, an unchecked screen, an empty capture twice); the model is told once with one short line so it never pretends to see | Never silent | The line has fixed words and one closed reason; nothing from the screen |
| "Help me with this" by voice | Went to a task | The model guides with the ring and the steps (point_at, show_step); start_task is for "do it for me" | The worker asked how, not for it done | start_task still shows its consent card |
| A screen task that cannot run in the front window | A bare "Done." | A card (and a spoken line when a conversation is open) says which app and what to do, read from the task row | Never a false Done | The app name is cleaned; the words are ours |

What stays the owner's click, whatever the request: the yes on the card, every macOS permission (Microphone, Speech Recognition, Accessibility, Screen Recording), every consent card for a task, the first supervised click test, and any real desktop click.
