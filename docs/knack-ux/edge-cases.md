# Edge cases: Home and the shell (SHELL-WEB)

One table per screen. "Test" is the test name (file in brackets) or the script that proves it. A row says what the worker sees; nothing here is a model answer, every sentence is a fixed template with numbers from the data. Run: `npx vitest run src/screens/Home src/screens/FirstRun src/components/shell src/jobs.test.ts src/lib` from `apps/dashboard`, then `node scripts/check-clicks.mjs <base> --example`, `node scripts/check-copy.mjs <base> --routes=home,first-run` and `node scripts/smoke.mjs <base>`.

Cross-cutting rules, each tested where it is drawn: no "undefined", "NaN" or "null" is ever printed; a number that is not a number makes the sentence fall back to the engine's own words or the row disappears; dates are read as written (no time zone moves the day); every dynamic text carries `dir="auto"` and wraps anywhere (`overflow-wrap: anywhere`), so a long or right-to-left name never breaks the column; a count is whole, with thousands separated.

## Home (`screens/Home`)

| State | What is shown | Test |
|---|---|---|
| Loading, under 600 ms | the hero area holds its height, nothing else | check-copy `home` and the visual audit |
| Loading, over 600 ms | "Reading your week" in muted 12 px; while the engine is starting, "Starting Knack, about 20 seconds." | `Reading` (visual audit) |
| Could not load | "Could not read your week." / "Nothing was changed." / Try again | `the quiet and error states: every state has a title, a body, no blame...`; `only a stale week and a load failure offer Try again` [edge.test.ts] |
| One pointer | the hero; the action; Why this?; the quiet rows (needs you, growth) | `the hero is at most 16 words with one quantity` [model.test.ts] |
| Two or three pointers | the best one is the hero, the second is a row of at most 12 words | `the quiet row for a second pointer` [model.test.ts] |
| No pointers, status ok | "Nothing stands out this week." / "No number moved far enough to matter." | `an unknown status reads as a quiet week` [edge.test.ts] |
| First week or not enough data | "Knack is learning your work." / "Check back in a few days." | `uses the shortest wording of the wireframe for each` [model.test.ts] |
| Not set up | "Choose your role first." and a Choose a role button to first run | `asks for a role first when the worker is not set up` [model.test.ts] |
| Stale | "These numbers are out of date." / "Knack says nothing rather than something old." / Try again | `only a stale week and a load failure offer Try again` [edge.test.ts] |
| Role changed | "Your role changed." / "Pointers start again, so you are not compared with your old role." | model.test.ts |
| An approval blocks a job or a safety pause is waiting | the approval takes the hero; the pointer becomes the first quiet row; buttons are real clicks; the consequence is printed; a safety pause has no primary button | `what takes Home's hero slot` and `recognises a safety pause` [approval.test.ts]; check-clicks J2 |
| Several approvals (up to thousands) | one hero (safety pause first, then irreversible, then outward, oldest first; ties by id); the rest are one count row | `ranks a safety pause...`, `copes with thousands of waiting items`, `copes with a time it cannot read` [approval.test.ts] |
| Approval approved but the step did not finish | an error toast "Approved, but the step did not finish."; never "done" | `reads what an approval did with the step it released` [approval.test.ts] |
| Approval needs a fresh sign-in (identity provider on) | the sign-in notice is printed under the hero; without it nothing is approved | ApprovalHero + smoke (example data: approve is a real click) |
| Needs-you count: 0, 1, 2, 1,203, 2.9, negative, NaN, Infinity | no row; "1 thing needs you"; "2 things need you"; "1,203 things need you"; "2 things need you"; no row | `the quiet rows: needs you ...` [edge.test.ts] |
| The sidebar badge and the Home row disagree | they cannot: both read the count Needs you publishes (`refreshNeedsBadge`); Home subtracts the hero | `leaves the rest for the needs-you row, never below zero` [approval.test.ts] |
| Seconds: 0, 1, 35, 119, 120, 4,200, 3.6 million, negative, not a number | "as long as the expert"; "1 second"; "35 seconds"; "119 seconds"; "2 minutes"; "70 minutes"; "1,000 hours"; the engine's own sentence; the engine's own sentence | `measure: a number and its unit`, `hero: the sentence` [edge.test.ts] |
| Step name of 40 words, one word of 500 letters, accents, emoji, Arabic, Chinese, Cyrillic | the hero stays within 16 words with one quantity (the step is cut to its first words with an ellipsis); a single long word is kept whole and wrapped by the page; other scripts pass through untouched | `hero: the sentence` [edge.test.ts] |
| Pointer with an empty headline, no action, or no id | not a pointer (filtered); no action button; Why this? still works when the engine says details are available | Home filter + `an empty or whitespace headline gives an empty sentence` [edge.test.ts] |
| Action label over five words, or a target that is not a screen | "See more"; the link is always a `#/` route, never `javascript:` | `the action...` [edge.test.ts] |
| What to try: missing, empty, punctuation only, over 12 words | the line is absent (never "Try .") | `what to try ...` [edge.test.ts] |
| Repeats row: no total, 0 actions, 0, negative, NaN, infinite rate; half a minute; 1 hour; 12,345 hours | no row; "About 1 minutes..." (minutes under an hour); "About 1 hour a week..."; "About 12,346 hours a week..." | `repeats: ...` [edge.test.ts] |
| Repeats interval upside down, missing, negative | put the right way round; no hint; clamped at 0 | `repeats: an interval given the wrong way round` [edge.test.ts] |
| Date line: any time zone, month 13, day 45, empty, "2026-1-5", null week | "Week of 9 November" as written; nothing is drawn for a date that is not on the calendar; "This week" when there is no date | `the date line` [edge.test.ts] |
| Week crossing a month or a year | "28 December to 3 January" | `a week that crosses a month or a year names both` [edge.test.ts] |
| Origin badge | one badge in sentence case: "Example data" wins; "Some example data" for mixed; "Synthetic firm" from the engine's own badge text, any case; nothing for real data | `the origin badge` [edge.test.ts] |
| Example line after first run | "This is an example. Knack starts counting now." for a week; not with a first-run time a day ahead (clock fault) or unreadable | `the example line and stale or skewed clocks` [edge.test.ts] |
| Engine unreachable | the one-line banner "Knack cannot reach its engine." with Try again; nothing is changed; the status line says the same | check-copy `--example` and smoke |
| Voice context | `reportInsight(id, kind)` only for a pointer hero; null for an approval, a quiet week or loading; ids outside the grammar are dropped by `lib/wakeContext.ts` | wakeContext tests (Track C); Home effect |

## First run (`screens/FirstRun`)

| State | What is shown | Test |
|---|---|---|
| Roles not loaded / failed | nothing but "Could not read the roles. Nothing was changed." with Try again | FirstRun screen (visual audit) |
| No packs / more than five | no cards / five cards | `more than five packs show five cards; none shows none` [edge.test.ts] |
| Pack summary empty, one word, 500 letters, no full stop | a card line of at most four words, never ending in a comma | `a pack with no summary...`, `cuts a pack summary` [edge.test.ts, firstRun.model.test.ts] |
| Role chosen | the consent screen: one card per consent, each a title, one plain sentence and Yes, Not now and Never of one size, none pre-selected; 89 of 90 words and 10 of 10 controls in the app | `Yes, Not now and Never each reach the same screen` [firstRun.model.test.ts], `scripts/shot-firstrun.mjs` (budget line) |
| Role cards | all packs the engine lists (three now), each with how far it is built: Fully built and validated (deep), Full pack (standard), Starter (thin); Not sure yet picks nothing | `offers all three roles, and says how far each pack is built` |
| Back on the consent screen | shown when the screen has fewer than three cards; with three cards it is left out to keep ten controls (Skip stays) | FirstRun screen |
| The write fails | the consent screen stays, with the engine's message and "Nothing was changed."; no answer is recorded | `a failed write stays on the consent screen` |
| Not now | asked again once after exactly a week; never for Never or Yes; a stored value that is not ours is ignored | `Not now asks again after exactly a week`, `asks again once` |
| Last screen, desktop app | four plain lines from what was written, and the Hey Knack switch with what listening is and is not, plus the shell's own line when permission is refused | `the Hey Knack row` [firstRun.model.test.ts] |
| Last screen, browser tab | no Hey Knack row | `is absent in a browser tab` |
| Pack with no tools, no risky actions, no hours days | still four lines, never "undefined" | `the ready lines cope with a pack...` [edge.test.ts] |
| Opening by itself | only when the engine answered, knows nobody, set-up was never finished here, and the address names Home or nothing and carries no query | `when first run opens by itself`, `never opens...` |
| Connection chips slot | filled by `components/connections/ConnectionChips.tsx` when it exists (one prop, `role`); then a role click opens the chips and a Continue button (4 clicks) | check-clicks "first run" |
| Mac window | the first 40 px drag the window and the column starts below the traffic lights | CSS (`html[data-knack-shell="mac-inset"]`) and the visual audit |

## Sidebar, status line, Stop (`components/shell`)

| State | What is shown | Test |
|---|---|---|
| Worker | 5 rows and no More, 0 hint words | `the sidebar contract` [shell.test.ts], check-copy `side 5r` |
| Admin | 9 rows (eight destinations and More: Models and cost, Evidence, Background runs); none of the worker's five | same, `gives an admin eight rows and a More of three` [navModel.test.ts] |
| Pinned views | retired: a worker has five rows and nothing else (docs/knack-ux/views.md); the stored switch is ignored | `gives a worker exactly five rows` |
| Needs-you count 0 / 9 / 1,203 | no badge / 9 / the number (the badge is wide enough for four digits) | `the sidebar badge...` |
| Status: starting, live, example, some example, cannot reach, engine up but not saying | "Starting", "Live models", "Running with example data", "Some example data", "Cannot reach the engine", "Connected"; always a dot and words, at most four words | `the status line` [edge.test.ts, statusModel.test.ts] |
| Engine silent for 30 s | the status becomes "Cannot reach the engine" and the banner appears | `starting turns into cannot reach after thirty seconds` |
| Stop pressed, no service answered | "Stopped." and "No service was running." | smoke (kill) |
| Stopped | the Stop button reads Resume, the in-window banner says everything is stopped (a printed fact, not a colour); Shift-Escape and Shift-Command-K do the same | smoke (kill) and `keys.test.ts` |
| Narrow window (under 880 px) | top bar (Stop, More, account) and a bottom bar of five; an admin's other three rows lead the More sheet, so every Admin destination is reachable | `fits the bottom bar at 390 px` [navModel.test.ts], visual audit at 390 and 840 |
| Stop drawn once | exactly one visible Stop button (the word, one red square from the design system's CSS, no icon of its own); the stopped banner carries one alert icon; a time that cannot be read prints no "Invalid Date" | `stop.test.ts`, smoke (kill switch) |

## Address, keys, menus

| State | What is shown | Test |
|---|---|---|
| Old route, with or without a trailing slash, any case | redirects to its new place and rewrites the address | `an old route with a trailing slash still redirects` [edge.test.ts]; `navModel.test.ts` |
| Week, Presence, Genome, Graph, Git | one page, Growth, at `?section=time\|steps\|map\|commits`; the old query (`?person=`) is kept | `folds the work views into the sections of Growth` |
| `/firm/<view>` and `/predictions` | the view's own address (`/roles`, `/people`, `/brief`, `/forecasts`...); `/firm/nonsense` is `/firm` | `sends the old Firm sub-addresses` |
| Agents | a worker lands on Routines (background tasks); an admin keeps Background runs | `sends Agents to Routines for a worker` |
| Today (the live coach) | stays a screen: unlisted, no redirect; Home opens it while a coach step is active | `the live coach page` |
| `?section=` that Growth does not know, or `../etc` | My progress | `has five, in the order the views rule gives` |
| Malformed query, empty route, 100,000-character path | no throw; Home | `the address` [edge.test.ts] |
| Corner card deep link `#/needs-you?item=q_9` | stays; the item is carried | `the Needs you deep link...` |
| Settings deep link `#/home?settings=interruptions` | opens the Settings drawer at that section and tidies the address; never hijacked by first run | smoke (Settings) and `never opens...` |
| Key event with no key string, an empty key, 10,000 characters, a modifier alone | nothing; no throw | `the keys` [edge.test.ts] |
| Cmd-1 to Cmd-5 (a worker), Cmd-1 to Cmd-8 (an admin), Cmd-comma, Cmd-slash, Shift-Cmd-K | the rows in order, Settings, About this screen, Stop; a number with no row does nothing; no key ever approves anything | `keys.test.ts`, `never approves anything` |
| Account menu | name and role, Change profile, Set up again, View as (remembered, two clicks the first time), Settings, Take the tour, sign-in when configured; Escape returns focus to the button; Appearance lives in Settings | keyboard check in the visual audit; `viewAs` tests |
| More sheet | Admin view only, three rows; Search is the first row only on narrow windows; the keyboard skips rows that are not drawn | `More never has more than ten rows` [edge.test.ts] |
| A worker and an admin screen (including `/models`, `/evidence`, `/forecasts`) | one sentence, "Switch to Admin to see this", and Go to Home; no request is made and no data is drawn; no menu, sheet or palette row reaches it | `says one sentence to a worker who types an Admin address`, `a worker can never reach an admin screen` [edge.test.ts] |

## Palette and About this screen

| State | What is shown | Test |
|---|---|---|
| Empty or blank query | the screens in menu order, at most seven, then "Show all N" | `an empty, blank or one-letter query` [edge.test.ts] |
| 20,000 characters, regex characters, HTML, percent escapes | no throw, no match | `a query of thousands of characters...` |
| Unicode or right-to-left query | split into words, no throw | `unicode and right-to-left queries` |
| A screen's old name (queue, briefing, repeats, memory, privacy, genome, presence, graph, git) | finds the new screen or the Growth section (admin: predictions finds Forecasts) | `a screen can be found by the name it had before Knack`, `lists the four sections of Growth` |
| Thousands of pointer rows | seven until "Show all" | `thousands of extra rows (pointers) are capped at seven` |
| Desktop-only commands (Pause for 1 hour, Open System Settings for Accessibility, Ask Knack) | only when the desktop bridge offers them; "Ask Knack: <phrase>" is the one row when nothing matches and the bridge can ask | `offers a desktop-only command only when the desktop app can do it` [palette.test.ts] |
| Delete my data | opens Your data; nothing is deleted from the palette; no shortcut by design | `gives Delete my data no shortcut by design` |
| About this screen | what it is, where the numbers come from, what it cannot tell you, and the live status; one sentence each; no banned phrase | `about.test.ts` |

## Account menu and profile (`components/shell/AccountMenu.tsx`, `ProfileForm.tsx`, `lib/profile.ts`)

| State | What is shown | Test |
|---|---|---|
| No name yet | "Your name" as a dashed link that opens the editor in place; the avatar shows the person icon | `profile.test.ts` |
| Name typed: spaces, tabs, newlines, bidirectional overrides | trimmed and collapsed to single spaces; control characters and overrides become spaces | `drops control characters and bidirectional overrides` |
| Name with a digit, symbol, emoji, leading hyphen, or over 60 characters | refused with the rule ("Letters, spaces, hyphens and apostrophes, starting with a letter. Up to 60 characters."); never silently cut | `refuses digits, symbols, emoji...` |
| Name in another script (Arabic, Chinese, Cyrillic, accents) | kept; shown with `dir="auto"`; the avatar takes its first letter | `takes letters of any script`, `gives the avatar one letter` |
| Name emptied | cleared (sent as an empty name, which the engine reads as clear) | `sends an empty name to clear one` |
| Nothing changed | the form closes; nothing is sent | `sends only what changed, and nothing when nothing did` |
| Role list | the engine's own closed list (GET /profile `roles`); an engine without that route gets the packs; neither loads: "Roles could not be loaded. Your name can still be saved." | `ProfileForm` (visual audit) |
| Role changed, engine answering | POST /profile {role}; the person, name and capture choice stay; Home, Growth and the coach reload for the new role | engine tests (Track R), smoke |
| Role changed, no engine | "Saved on this device. Knack is showing example data, so Home keeps its example week." | `SAVED_EXAMPLE` |
| Refused (unknown role, bad name, not set up) | the engine's own plain message, inline; nothing changes | `ProfileForm` |
| Storage blocked | the name lasts until the page closes | `lasts for the page even when storage is blocked` |
| The engine deletes the name line (What Knack remembers) | the next answer from the engine clears it here | `follows the engine's word, including when the engine has none` |

## Growth, bridged until Track D draws its sections (`screens/GrowthHost.tsx`)

| State | What is shown | Test |
|---|---|---|
| `?section=progress` or none | Growth as Track D draws it | `GrowthHost` |
| `?section=time\|steps\|map\|commits`, Growth not yet drawing sections | the older screen under one switch of five sections | visual audit |
| A bridged section draws a cohort string ("Average over all novices", a count of people, another person's id) in the Worker view | the section is not drawn: "This section is being rebuilt. It will show only your own work." and a link to My progress | `cohortRules.test.ts`, the view audit |
| The Admin view | not guarded: an admin may see the firm | `GrowthHost` |
| Track D's module exports `handlesSections = true` | the host steps aside | `GrowthHost` |

## The coaching row on Home (`screens/Home/Home.tsx`, `model.ts`)

| State | What is shown | Test |
|---|---|---|
| A coach step is active, engine answering | one quiet row first among the rows: "Coaching you on <task>." (name cut at its first comma, five words at most), opens the coaching page | `the coaching row` [model.test.ts] |
| No active step, the step past the last, a name that is not text, a step that is not a whole number | no row | `is absent when no step is active` |
| No engine (example data) | no row: an example is not a step anyone is coaching | `Home.tsx` |
| Right-to-left or accented task name | kept | `copes with unicode and right-to-left task names` |

## The Home task box (`components/home/TaskBox.tsx`, `lib/taskbox.ts`, `lib/taskClient.ts`)

Track T's task API, contract v1: `POST /agent/tasks {text, source}` as the worker; a consent is `POST /agent/tasks/{id}/consent {choice}` as `worker_approval`; a question is `POST .../answer {option_id}` as the worker.

| State | What is shown | Test |
|---|---|---|
| Empty box, only spaces, only punctuation, Enter | nothing is sent and nothing is said | `is not sendable when there is nothing to send` [taskbox.test.ts], smoke 8i |
| Typed task with line breaks, tabs, runs of spaces, bidirectional overrides | one line, single spaces; what could reorder text is dropped | `is trimmed and flattened to one line`, `drops what could reorder or hide text` |
| Over 500 characters (an emoji counts as one) | refused with "Keep it under 500 characters."; never cut, never sent | `is refused, never cut` |
| Another script, markup, regex characters | sent as text exactly as typed; React prints it as text | `keeps any language`, `is sent as text only` |
| Enter while an input method is still composing a word | does not send | `TaskBox` (`isComposing`) |
| Enter twice quickly | the second is ignored while the first is out | `TaskBox` (`busy`) |
| Example chips | fill the box only; never send; shown only while the box is focused and empty; at most three; role-aware | `are at most three short ones`, smoke 8i |
| The service answers 201 | its own one plain line at once, the box empties and keeps focus; "Knack will plan this." when it sent no line | `places a task`, `says Knack will plan this...` |
| 201 with no task id | an error sentence, nothing placed | `is nothing when there is no task id` |
| `needs_consent` | a card: scope, what it can and cannot do, where, cost, time cap, then Allow and Not now of one size, none pre-selected; a small More reveals "Allow everything for this task" only when the service offers it (a browser task does not) | `reads a consent card whole`, `offers Allow and Not now of equal standing`, smoke 8i |
| A consent card with no scope the worker can read | not a consent: nothing is asked | `is not a consent when it carries no scope` |
| Focus after sending | stays in the box, never on a card button, so the Enter that sent the task cannot also answer it; no key ever answers a consent | smoke 8i |
| The choice | closed list (allow, everything, decline) whatever ids the service sends; sent as `worker_approval`, and nothing else is | `only ever offers the closed choices`, `sends the choice as the approval actor` [taskClient.test.ts] |
| Not now | "Not started. Nothing was changed."; the card goes away | smoke 8i |
| `question` | a card with its options, each a button; the answer goes as the worker | `reads a question card`, smoke 8i |
| An inline answer (`route: "answer"`) | after the task is done, the full text (up to 1500 characters) as plain text under the box, with Dismiss | `reads the task as it is`, smoke 8i |
| Three tasks already running (429) | "Three tasks are already running. Wait for one to finish, or stop one."; what was typed stays | `names the limit of three at a time` |
| No task service (no connection, 502, 503, 504, no such route) | "Knack's task service is not running, so nothing was started."; what was typed stays; nothing is faked | `is unavailable when nothing answers`, smoke 8i |
| The start-up token changed under the call | asked once more, not again | `asks once more when the start-up token changed` |
| Refused with a short plain message / anything else | the service's own words / "That did not go through. Nothing was started." | `shows the service's own short plain message` |
| The microphone button | drawn only where the desktop app can open its Ask bar (`window.knackShell.ask`); absent in a browser | `TaskBox` |

## What is not covered here, and why

- Time zones in Needs you, Routines and Your data timestamps belong to Track C's screens; Home shows no clock time.
- Real desktop behaviour (the pill, the window, the menu bar) is Track A's.
- Right-to-left layout of the whole app (mirroring the sidebar) is not done: only the text direction of dynamic strings is. A right-to-left worker would still see a left-to-right sidebar.
