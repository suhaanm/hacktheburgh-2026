# Knack UX specification (UX-STRATEGY, 7 Nov 2026, 22:05 to 00:15 UTC)

Status: PROPOSED for the lead to merge and for four implementer agents to build from tonight and tomorrow. Product name from now on: **Knack** in every user-visible place (internal identifiers, env names and file names keep `understudy`). Companion files in `docs/knack-ux/`: wireframes `01` to `08`, a static prototype of the after state using the real tokens (`prototype/knack.html`, open with `#home`, `#needs`, `#routines`, `#growth`, `#firm`, `#roles`, `#first` and `?theme=dark`) and its renders (`after/`, light and dark at 1152 by 735 and 390 by 844), `jobs.json` (the ten jobs, today and target), `clutter-1440x900.json` (every measurement below), `budgets.json` (the section 5 budgets per screen, for `check-copy.mjs`), `shell-transitions.json` (the 18 window and pill transitions, for the reducer's tests), `banned-phrases.json` (for `copy-lint.test.ts`), `scripts/` (the two measurement scripts), `before/` (screenshots), `knack-brand-sheet.svg`, `06-corner-states.svg`.

What was measured and how. The running dashboard (127.0.0.1:5173, live mock engine, Worker view, then Admin view) was driven with headless Chromium at 1440 by 900, light theme, every non-GET request refused, so nothing changed. "Words above the fold" counts words in text nodes inside `#main` that are visible and intersect the first 900 px; the sidebar is counted separately. "Paragraphs over two lines" counts elements with at least 8 words of their own text that render on more than two lines. "Pills and badges" counts visible `.pill`, `*badge*` and `.chip` elements above the fold. "Controls" counts visible buttons, links, inputs, selects, summaries and role button, tab or switch above the fold in `#main`. The final click of a destructive job was counted and not executed. n = one engine in mock mode, one browser, no users: these are measurements of the interface, not of people. The Electron app was not run (no desktop capture or input was allowed), so section 7's "today" column is from reading `apps/desktop/src/main`.

## The five decisions that matter most

1. **One app, one calm window, one pill.** `Knack.app` is the dashboard as its main window (80% by 84% of the work area, centred, remembered), with the Dock icon and the menu-bar item always present. When a run that uses the worker's real screen starts from the window, the window minimises itself and a 32 px pill in the bottom-right corner says what is happening in five words and offers Stop. It never pops back on its own; only an approval that needs the worker raises a card, and only a click on that card brings the window forward.
2. **Five destinations, not twenty-one screens.** Worker: Home, Needs you, Routines, Growth, Your data. Admin adds Firm, Roles, Onboarding. Everything else is under More and the command palette. Queue, Briefing and routine proposals become one list ("Needs you"); Repeats joins Routines; Memory, Privacy and the ledgers become "Your data".
3. **Home is one sentence.** One hero insight (at most 16 words, one quantity), one action, at most two quiet rows. No chart, no statistic, no paragraph. The evidence is behind "Why this?". The home screen goes from 224 words above the fold (content 173, sidebar 51) to about 64 (content 47, sidebar 17, which now includes a status line and a labelled Stop button).
4. **Words are budgeted and measured.** Every element has a word budget (section 5) and a script fails the build above it. Explanation moves to Hint, Details and ⌘/ ("About this screen"). Honesty items (origin badge, consent text, "it will never", consequences, errors, limits) stay printed.
5. **First run is three clicks.** Role card, one capture consent (Yes, Not now, Never), "Show my week". Everything else takes the role pack's safe defaults and is editable in Your data; permissions are asked in context, once.

Also decided: the sidebar footer is a status line ("Live models" or "Running with example data"), the account button and a labelled Stop button; the corner is the **bottom-right**; there is **one interrupting surface at a time**; **no keyboard shortcut ever approves**; the retired dock panel stays only as a hidden audio host until the Live voice code moves.

---

## 1. The jobs

Ten jobs, ranked by how often I expect them (an expectation, not data). "Today" is the click count from the app being open on its landing screen, measured with `docs/knack-ux/scripts/measure-jobs.mjs` (exact clicks listed). "From the menu bar" is the desktop path today: the menu bar opens the dashboard in a browser tab at the Today screen, not Home. Target budget: the five most frequent jobs within 2 clicks of Home, nothing deeper than 3.

| # | Job | Who | Today: clicks and exact path | Target budget and path |
|---|---|---|---|---|
| J1 | See what matters this week | worker | 0 on the dashboard (it lands on Your week: 173 words and 10 controls above the fold). From the menu bar 3: right-click the icon, Open dashboard (opens at Today), sidebar "Your week" | **0.** Open Knack: Home. At most 50 words of content above the fold (about 65 with the sidebar) |
| J2 | Approve or reject a queued item | worker | 2: sidebar Queue, "Approve and submit" (plus a sign-in step-up for an irreversible item when Auth0 is on). From the menu bar 3 | **1** when the item is Home's hero; **2** otherwise: Needs you, then the button |
| J3 | Opt into an automation, or decline it | worker | 2: sidebar Routines, one of four buttons. "Run while I'm away" is 4: Routines, open the box, switch on, "Allow while I'm away" | **2:** Needs you, then Watch first, Not now or Never. "Run while I'm away" 3: Needs you, More ways to say yes, its switch and confirm |
| J4 | See whether I need less help over time | worker | 1: sidebar Growth (152 words and 7 long paragraphs above the fold when empty; 811 on the whole screen with data) | **1:** Growth. One sentence and one chart above the fold, at most 60 words |
| J5 | See what Knack has of me, and delete it | worker | 4 to delete a memory line: More fold, Memory, Forget, "Forget it". 3 to clear the model ledger: Privacy, Clear the ledger, "Yes, clear the list". Five places hold "my data" (Memory, Privacy ledger, Presence, Growth ledger, Graph nodes), each with its own delete wording | **3** to delete anything: Your data, Forget, Forget it (inline confirm). **1** to see. "Delete everything Knack holds about me" is 3 as well |
| J6 | Stop everything, or pause | worker | 1: the fixed "Stop everything" pill (Shift-Esc is 0). From the menu bar 2: right-click, Stop everything or "Pause for 1 hour" | **0:** Option-Shift-Command-K anywhere. **1:** the corner pill's Stop while working. **2:** menu bar when idle |
| J7 | Start work and get the overlay out of my way | worker | 4 for a sandbox job (More fold, Agents, choose a job, "Run in background"; it runs on sample data). From the menu bar 2: "Talk to Understudy". The window never moves aside | **0:** Option-Space (tap to type, hold to talk), Enter. **2:** Routines, Run now: the window minimises and the pill shows |
| J8 | Admin: find where the firm loses time | admin | 2: View as Admin, sidebar Firm (seven cards, 206 words above the fold) | **0** with a real role (Admin lands on Firm); **1** with the role switch (account menu, View as Admin, remembered). Three rows above the fold |
| J9 | Admin: compare a role | admin | 3: View as Admin, Firm, tab Roles (313 words above the fold) | **1:** sidebar Roles (**2** with the role switch) |
| J10 | Admin: see onboarding speed | admin | 3: View as Admin, Firm, tab Onboarding (284 words above the fold) | **1:** sidebar Onboarding (**2** with the role switch) |

First run, for comparison: about 20 clicks over 15 screens today (8 steps in the desktop panel, then 7 questions in the dashboard); **3 clicks** after (section 8).

What the numbers say. The two-click jobs are already two clicks; the real costs are elsewhere: (a) the landing is Home but the desktop opens Today, so the menu-bar path costs one extra click and lands on the wrong screen; (b) J5 and J7 are scattered: five places for data, three for "do something now"; (c) the cost of a click is the words on the screen it lands on, which is 150 to 320 words above the fold on 15 of 20 worker screens. Cutting words matters more than cutting clicks, which is why section 2 and section 5 exist.

Rejected: adding a "Quick actions" strip to Home (a second hero; the sidebar already is the quick actions); keyboard approval of a queued item (the approval must stay a real click, an existing safety rule); a single "Settings" destination for J5 (consents and data are one idea, behaviour preferences another; see section 3).

Machine-readable copy of this table: `docs/knack-ux/jobs.json`. SYSTEM writes the skeleton of `apps/dashboard/scripts/check-clicks.mjs` and SHELL-WEB completes it: it replays the target paths and fails above budget.

---

## 2. Clutter inventory

Measured at 1440 by 900 in the live mock (all 28 screens, `docs/knack-ux/clutter-1440x900.json`). "Above" is words above the fold in the main column, "total" the words on the whole screen, "long" paragraphs over two lines, "pills" pills and badges above the fold, "ctl" controls above the fold in the main column.

The shell, on every screen: **51 words of hints and 18 controls in the sidebar** (24 and 31 when the Details and More folds open themselves, which they do on 13 screens; with both open the list is taller than a 900 px window and "Briefing" is clipped); a permanent Stop button; a header of four elements (eyebrow, title, lede, badge) that repeats the nav label; a content column that re-centres on every screen (its left edge is at x = 474 on Home and Notices, 294 on Routines and Queue, 280 on Growth and Firm); 9 sidebar rows by default (10 for Admin), 22 with the folds open.

| Screen (Worker view) | Above | Total | Long | Pills | Ctl |
|---|---|---|---|---|---|
| Home (Your week) | 173 | 173 | 2 | 1 | 10 |
| Growth (nothing counted) | 152 | 579 | 7 | 1 | 0 |
| Repeats | 119 | 119 | 1 | 3 | 9 |
| Routines | 183 | 347 | 2 | 1 | 9 |
| Queue | 157 | 259 | 0 | 6 | 6 |
| Privacy | 240 | 344 | 2 | 1 | 8 |
| Genome | 318 | 936 | 11 | 2 | 12 |
| Presence | 142 | 363 | 4 | 2 | 2 |
| Graph | 162 | 217 | 2 | 1 | 22 |
| Week | 118 | 1097 | 4 | 1 | 3 |
| Git habits | 176 | 477 | 3 | 2 | 3 |
| Predictions | 205 | 1035 | 6 | 2 | 3 |
| Today | 80 | 80 | 0 | 1 | 8 |
| Memory | 179 | 447 | 2 | 2 | 19 |
| Notices | 172 | 439 | 0 | 1 | 23 |
| Onboarding (role screen) | 159 | 159 | 3 | 0 | 1 |
| Briefing | 256 | 858 | 4 | 1 | 1 |
| Agents | 95 | 95 | 0 | 0 | 4 |
| Models | 184 | 467 | 1 | 0 | 4 |
| Evidence (exempt) | 236 | 25,602 | 417 | 26 | 16 |

| Screen (Admin view) | Above | Total | Long | Pills | Ctl |
|---|---|---|---|---|---|
| Firm overview | 206 | 299 | 0 | 2 | 14 |
| Firm: Roles | 313 | 492 | 4 | 5 | 10 |
| Firm: People | 222 | 614 | 0 | 3 | 20 |
| Firm: Onboarding | 284 | 284 | 2 | 5 | 10 |
| Firm: Automation | 147 | 147 | 0 | 2 | 10 |
| Firm: Risk and coverage | 178 | 193 | 0 | 8 | 9 |
| Firm: Forecasts | 201 | 1044 | 6 | 3 | 10 |
| Firm: Brief | 226 | 790 | 2 | 2 | 9 |

Median above the fold: 173 words (worker, 20 screens), 214 (admin, 8 screens). The design system's own budget for a worker screen is about 400 words in total; nine of the 20 worker screens measured exceed 400 (Growth when empty is 579, Genome, Week, Predictions, Memory, Notices, Models, Briefing, Evidence), and although the one-line helper rule is met, the header still carries four elements.

### The worst ten screens (score = words above + 12 per long paragraph + 4 per pill + 3 per control)

| # | Screen | Score | What is wrong, specifically |
|---|---|---|---|
| 1 | Genome | 494 | 318 words above the fold, 11 long paragraphs, a six-item legend, the instruction "Drag the slider or press Play", four disclosures before the first number is explained |
| 2 | Firm: Roles | 411 | 313 words; "Synthetic firm" badge three times plus a page badge; an "A gap we can see" pill on every row; three charts side by side competing |
| 3 | Firm: Onboarding | 358 | 284 words; five badges; a legend that is itself a sentence (23 words) |
| 4 | Firm: Forecasts | 315 | 1,044 words in total; six long paragraphs |
| 5 | Briefing | 311 | 256 above and 858 in total for "up to three cards"; an example-data sentence of 24 words |
| 6 | Predictions | 294 | 1,035 words; six long paragraphs; reads as a report, not a screen |
| 7 | Firm: People | 294 | 20 controls above the fold |
| 8 | Privacy | 292 | 240 words above the fold to say "1 call to a model" |
| 9 | Firm: Brief | 285 | 790 words in total for "a one-page summary" |
| 10 | Memory | 268 | 19 controls; the default view is raw Markdown with line numbers and a file path |

Graph (22 controls above the fold), Notices (23 controls: 18 kinds each with a four-way choice, to set one preference) and Growth when empty (152 words and 7 long paragraphs to say that nothing is there) follow. Evidence has 25,602 words and is exempt by D45, but it is a first-level sidebar item next to Privacy; that is an IA offender, not a copy one.

### What the after state measures (static prototype, same method, 1152 by 735 window, light)

`docs/knack-ux/prototype/knack.html` builds the five main screens with the real tokens and the spec's copy; `after/after-measurements.json` is the measurement. It carries only the headline content (Hints and disclosures closed, as they are by default), so the real screens will land a little above these numbers; the budgets in section 5 leave that headroom.

| Screen | Words above the fold, before and after | Controls | Pills | Paragraphs over two lines | Sidebar |
|---|---|---|---|---|---|
| Home | 173 to 47 (plus 51 and 17 sidebar words) | 10 to 4 | 1 to 1 | 2 to 0 | 9 rows to 6 |
| Needs you (Queue before) | 157 to 103 (three decisions, one more than Queue had) | 6 to 12 | 6 to 0 | 0 to 0 | |
| Routines | 183 to 45 | 9 to 5 | 1 to 0 | 2 to 0 | |
| Growth (before: empty state) | 152 to 53 (with data) | 0 to 4 | 1 to 1 | 7 to 0 | |
| Firm overview | 206 to 80 | 14 to 5 | 2 to 1 | 0 to 0 | 10 rows to 9 |
| Roles | 313 to 36 | 10 to 3 once the rows are links | 5 to 1 | 4 to 0 | |
| First run (role screen) | 159 to 20 | 1 to 3 | 0 to 0 | 3 to 0 | no sidebar |

Controls on Roles and on the first-run role screen are counted as they will be built (rows and cards are controls); the static prototype draws them as plain elements. Home's hero wraps to three lines at 390 px (24 px type); that is the one allowed exception to "no paragraph over two lines" and is exempt in `check-copy.mjs`.

### Cross-cutting offenders (fix once, every screen improves)

1. **The sidebar**: 51 words of hints, two fold buttons with their own hints, six footer controls (profile, engine mode, View as with a Hint, Search, tour, theme). Replace with five items, a status line, an account button and a Stop button.
2. **The four-element header**: eyebrow, title, lede and a badge on every screen. Replace with a title (or the hero sentence) and, only where it is a real limit, one printed line.
3. **The `framenote` bar** ("These are the detailed numbers. Your week shows the few that matter.") on six Details screens and its twin on Evidence: 16 words that apologise for the screen. Replace with a breadcrumb.
4. **Mono-capital badges** ("SYNTHETIC FIRM", "NAMES ARE MADE UP. THIS FIRM IS SYNTHETIC.", "EXAMPLE DATA") repeated per chart and per card. Replace with one sentence-case "Example data" or "Synthetic firm" per screen; the sentence goes in its Hint.
5. **The permanent Stop button**, drawn on every screen while nothing runs. Replace with the corner pill while working, a small Stop button (a red square and the word) in the sidebar footer otherwise, and the keyboard and menu-bar paths.
6. **The moving content column** (left edge at 280, 294 or 474). Replace with one left-aligned column (section 6).

---

## 3. Information architecture

### Navigation

Sidebar width 208 px. Each item has a 16 px icon and a label; no second line. Rows are 32 px. The current item gets `--panel` and a 2 px `--accent` left edge (as today). Counts appear only on Needs you.

| Destination | For (one sentence) | Absorbs |
|---|---|---|
| **Home** | What matters this week, as one sentence and one action. | Your week, Today (live task strip) |
| **Needs you** | Everything waiting for a decision: approvals, paused runs, routine proposals, prepared actions. | Queue, Briefing, the proposal half of Routines, paused runs |
| **Routines** | What runs for you, how far it is trusted, and what could run next. | Routines, Repeats |
| **Growth** | Whether you need less help over time. | Growth |
| **Your data** | What Knack remembers, measures and has sent, with a delete beside each. | Memory, Privacy, Presence's hours, Growth ledger, What your admin can see, capture and glance switches |
| Admin: **Firm** | Where the firm loses time and what changed. | Firm overview |
| Admin: **Roles** | Experts and juniors side by side, one row per role. | Firm: Roles, People (as a drill-down) |
| Admin: **Onboarding** | How fast people reach independence. | Firm: Onboarding |

Below the items: **More** (opens a sheet of at most ten one-line rows), then the footer, three things: a **status line** (a dot and at most four words: "Live models", "Running with example data", "Some example data" or "Cannot reach the engine"; it opens Settings at "Use live models"), an **account button** (avatar and name; opens View as, Appearance, Settings, Take the tour) and a **Stop button** (a red square and the word "Stop", 32 px high, always visible). Search is Command-K and the first row of the sheet on narrow windows.

The sidebar has 6 rows for a worker (5 plus More) and 9 for an admin (5 worker, then an "Admin" group of 3, then More), against 9 and 10 by default today (22 with folds open). The sidebar carries about 17 words in all (labels, brand, name, Stop and the status line), against 51 words of hints alone today. On a 390 px screen the sidebar becomes a bottom bar of the same five items (56 px high); More and the account sit in the first.

**More sheet** (rows, no hints; hints live in the palette): Understand your work: Where time goes (Genome), Your hours (Presence), How work connects (Graph), Calendar (Week), Git habits, Forecasts (Predictions). Behind the scenes: Background runs (Agents), Models and cost, Live coach (Today). For reviewers: Evidence. Admin adds: Firm: People, Automation, Risk and coverage, Forecasts, Firm brief.

**The signature screens and Pinned views.** The work ribbon (Genome), the work graph and the presence heatmap are the product's three memorable visuals (`docs/UI_DIRECTION.md`), and this IA moves them out of the sidebar (lead decision). They stay one click from Home: the hero's action ("See where the time goes") opens Genome focused on that step; Growth and the command palette reach the others. The owner's own walk-through opens on Genome by deep link (`#/genome`), and `DEFAULT_SCREEN` can still be flipped to it. `navModel.ts` carries `PINNED_VIEWS = [genome, graph, presence]`, off by default and switched on in Settings, Views, "Pinned views" ("Show Genome, Graph and Presence in the sidebar"); the sidebar then shows them as a "Look closer" group of three (9 rows). No visible string anywhere uses the word "demo". Old routes keep working through the redirects (`#/genome`, `#/today`, `#/queue`, `#/privacy` and `#/evidence` all appear in `docs/drafts/DEMO_SCRIPT.md`), and that script needs one pass to match the new labels.

**Settings** (Command-comma, a sheet; one line per setting, in this order): **Use live models** (the master switch, below), Interruptions (Rarely, Balanced, Often; a "Per kind" disclosure holds today's 18 rows; "Stops and blocking approvals always show." printed), Coaching (on or off; help level lock), Move aside while Knack works (on), Open at login (off), Appearance (Auto, Light, Dark), Models and cost (link), Views (View as Worker or Admin; Example week, shown only with example data; Pinned views), About (version, the engine and agent addresses). The rule that sorts a setting: **anything that lets Knack see or send a specific thing (capture, screen glances, the microphone, folders) lives in Your data; the one master switch for live models and everything about how Knack behaves live in Settings.**

### Live models and example data

The app starts its stack in **live** mode when a Gemini key is present and in **mock** mode when it is not (provider Gemini, D49), so the first thing the worker needs is an honest, quiet answer to "is this real?".

| State (from `/health` and the screens' own sources) | Status line (sidebar footer, 12 px) | Dot | Also |
|---|---|---|---|
| Reachable, `mock` false | Live models | solid `--good` | nothing else |
| Reachable, `mock` true (by design, or no key) | Running with example data | dashed hollow ring, `--muted` | a screen that shows example rows keeps its own "Example data" badge |
| Reachable, some sources answering with example rows | Some example data | dashed hollow ring | the badge on those screens |
| Not reachable | Cannot reach the engine | solid `--bad` | one line at the top of the content: "Knack cannot reach its engine." with a Try again button; nothing is changed |
| Starting | Starting | dashed hollow ring | "Starting Knack, about 20 seconds." on Home only |

The dot and the words always travel together (colour never alone); the line is one line at 208 px ("Running with example data" is 25 characters). It is not repeated as a banner on every screen: the origin badge already marks the data on a screen, and one printed line per screen is the budget. The two are different facts and both stay: the status line says which models Knack is using; the badge says where the numbers on this screen came from (a live model can still be reading the synthetic firm).

**Use live models** (Settings, first row): a switch. On: "Knack can call Gemini for steps you allow. Each call is listed in Your data." (15 words). Off: "Everything runs on example data." (5). No key found: the switch is disabled and one line is printed, "No Gemini key found. Add it to .env and reopen Knack." (11). Changing it restarts the engine, so the line "Switching restarts the engine. About 20 seconds." appears under the switch while it is changing, and the switch is disabled while anything is running ("A job is running. Stop it first."). Frames from the screen still need their own consent in Your data; this switch is the master gate above it and does not replace it. Honesty check for the first sentence: "Each call is listed" is true only while the old desktop remote paths are gated through the ledger (D38, `UNDERSTUDY_LEGACY_REMOTE`) and the catalogue's known gap stays closed; if the privacy summary reports a path the ledger does not cover, the sentence is replaced by the engine's own scope note, printed.

### Where each current screen goes

| Current screen | Verdict | Becomes |
|---|---|---|
| Your week (Home) | keep, rebuild | Home |
| Queue | merge | Needs you |
| Briefing | merge | Needs you (a prepared action is a row) |
| Routines | keep, split | Needs you for the decision; Routines for management |
| Repeats | merge | Routines, tab "Could automate" |
| Growth | keep, cut | Growth |
| Privacy | merge | Your data, "What it looked at or sent" |
| Memory | merge | Your data, "What Knack remembers" |
| Presence | demote | More, "Your hours"; its hours also appear in Your data |
| Genome | demote | More, "Where time goes"; a Home insight links straight to it |
| Graph | demote | More, "How work connects"; node delete uses the Your data wording |
| Week | demote | More, "Calendar" |
| Git habits | demote | More |
| Predictions | demote | More, "Forecasts" (Admin: Firm: Forecasts) |
| Today | retire as a screen | a live strip on Home while a task is on; "Stop coaching" moves to Settings |
| Notices | merge | Settings, Interruptions |
| Onboarding | retire | first run (section 8); "Set up again" in Settings |
| Agents | demote | More, "Background runs"; the pill's "Open" lands on the run |
| Models | demote | More and Settings, "Models and cost" |
| Evidence | demote, keep whole | More, For reviewers (still exempt from the word budget) |
| Firm overview, Roles, Onboarding | keep | the three Admin items |
| Firm: People | merge | a drill-down inside Roles |
| Firm: Automation, Risk and coverage, Forecasts, Brief | demote | More (Admin rows) and the palette; the eight-tab strip is retired |

Old routes redirect (`#/queue` to Needs you and so on), so the tour, the palette, the desktop's deep links and every existing bookmark keep working.

**Default landing:** Home. A returning worker sees, in three seconds, the date, one sentence of insight with its action, and, if anything is waiting, one row that says "1 thing needs you". An admin lands on Firm: the three most important rows.

Rejected: a top tab bar (eight tabs do not fit with a window at 960 px); keeping the Details and More folds (it is hide and seek: they opened themselves on 13 of 28 screens); palette-only navigation (not discoverable; the sidebar is the map); a second sidebar level for Firm (the tab strip's cousin).

---

## 4. Home

### What it shows (see `docs/knack-ux/01-home.md` for the wireframe and the states)

1. A date line ("Week of 9 November") and the origin badge in sentence case ("Example data" or "Synthetic firm") when the data is not real.
2. **The hero**: the top pointer as a sentence of at most 16 words, in the display face at 28 px, at most two lines. Template: `On {step} you usually take about {n} {unit} {longer|less} than {the expert|your peers}.` **Exception that makes J2 one click:** if an approval that blocks a running job, or a safety item, is waiting, it takes the hero slot (its title, one line, its own buttons, the consequence printed, "Evidence" opening in place) and the pointer becomes the first quiet row. Something the worker must decide outranks something they could learn.
3. One line of what to try, at most 12 words, imperative. Absent when the engine has none.
4. **One primary action**, at most four words, a verb phrase ("See where the time goes"), and a "Why this?" disclosure. It holds the method (fixed rules, not a model), the interval, n and the origin sentence.
5. At most two quiet rows, in this order of claim: the live task when one is on ("Working on the entitlement check. Help level 2.", the old Today screen in one line), the needs-you count when above 0, the second pointer, then the best of Repeats and Growth. Each is a hairline row with an icon, one sentence of at most 12 words and a chevron.

### What it never shows

A chart, a table, an interval or an n (they are behind "Why this?"), a lede about method, the Monday note (palette: "Copy my Monday note"), "What your admin can see" (Your data), the example-week selector (Settings, Views), the data-mode line (it lives in the sidebar's status line), a card per pointer, a second primary action, an eyebrow, a large Stop button when nothing runs (the sidebar's small Stop button is the only one while idle).

### The one-quantity rule

A worker-facing sentence carries at most one quantity: one count ("1 thing needs you") or one measure ("about 35 seconds"), never both. A range with its interval counts as one quantity, and so does a rate ("58 times in 3 weeks", "about 1 hour a week") or a fraction ("3 of 8"). "2 repeats could run for you, about 1 hour a week" breaks it; "About 1 hour a week could run for you." does not. Statistics (n, intervals, p-values, baselines) are not on the worker home at all; they live one tap away (a Hint or "Why this?"), as D45 already requires for worker screens. A lint (`oneQuantity.ts`) counts digit groups and number words outside dates, times, ids, ranges, rates and fractions, and fails a sentence with two separate quantities ("2 repeats, about 1 hour a week").

### Empty and first-run states

| State | Title | Body | Action |
|---|---|---|---|
| First run | the example insight, badged "Example data" | "This is an example. Knack starts counting now." | none |
| First week, capture off or later | Knack is learning your work. | Check back in a few days. | none |
| Nothing stands out | Nothing stands out this week. | No number moved far enough to matter. | none |
| Stale | These numbers are out of date. | Knack says nothing rather than something old. | Try again |
| Role changed | Your role changed. | Pointers start again, so you are not compared with your old role. | none |
| Could not load | Could not read your week. | Nothing was changed. | Try again |

No illustration, no mark above the title. The title is the only large text.

### Push versus pull (full rules: `docs/ATTENTION_DESIGN.md`, kept as the source of truth)

| Item | Interrupts? | Where it appears | Rule |
|---|---|---|---|
| Stopped (kill), a run paused for safety, an irreversible decision | yes, once | corner card (priority 1 or 2), then a menu-bar and Dock marker until resolved | safety is never held or batched |
| An approval that blocks a running job, a blocked run, a deadline | yes, once, at a natural break, one reminder | corner card (priority 3 or 4), badge always | attention table, rules 4 to 6 |
| Routine proposal, briefing card, run finished, morning report | **no** | Needs you, the badge, one digest card on return | wait class: digest only |
| The week's pointer | **no** | Home when the worker opens Knack | pull |
| Growth, Genome and the rest | **no** | on request | pull |
| Help-level change | glance only when nothing else is up | the existing 2 s level glance | unchanged |

Rule for new items: an item may interrupt only if a row in the attention table says so; a new interrupting type needs an entry there first. The pill is a status, not an interruption.

---

## 5. Copy rules

### Word budgets (these replace the table in `packages/design/README.md` for Knack; SYSTEM updates it)

| Element | Budget |
|---|---|
| Screen title (not a hero sentence) | 6 words, one line |
| Hero insight sentence | 16 words, two lines at 28 px |
| Lede or helper line | none by default; if used, 10 words, one line, and only for a real limit or a use rule |
| List row (title) | 12 words, one line; optional muted line 6 words |
| Card (proposal, queue, notice): title, body, button | 8 words, 20 words, 3 words |
| Corner pill label | 5 words |
| Corner card: title, body | 8 words, 22 words (the attention layer's existing limits) |
| Empty state: title, body, action | 5 words, 10 words, 1 action |
| Hint | 20 words, one sentence, never the only copy of a fact |
| Disclosure body | 60 words or 7 list items |
| Button | 3 words (4 for a hero action); a pill 2 words |
| Above the fold, content only | Home 50; Needs you 120; Routines 100; Growth 60 (empty 25); Your data 90; other worker screens 120; Admin screens 150; Details (More) screens 120; Evidence exempt |
| Whole default view, content only | worker 250, admin 400 (the old budget was 400 and 700) |
| Paragraphs over two lines | 0 in any default view |
| Pills and badges above the fold | 1 (the origin badge) |
| Controls above the fold | Home 5 (content), Needs you 12 (each row carries its own buttons), other worker screens 8, Admin 10 |
| Sidebar | 6 rows (worker), 9 (admin), 0 words of hints |

A screen over its budget moves the excess into a Details, a Hint or the palette, or it is cut.

### Banned patterns

- **"This screen shows..."**, "Here is what...", "You do not have to...", "Please", "Note:", "Remember", "Simply", "Just". Say the thing, not what the screen is for.
- **Explanatory paragraphs** in a default view. If it explains, it is a Hint (a unit, a definition), a Details (a method, a reason) or "About this screen" (⌘/).
- **Repeated disclaimers.** One origin badge per screen. "Nothing runs until you say so" appears once, on the consent surface, not on the lede, the card and the toast. The method sentence ("fixed rules, not a model") appears in "Why this?" only.
- **Eyebrows** that repeat the sidebar label, and a title that repeats the eyebrow.
- **Counts as titles** that say nothing ("Two things from your week"). Say the thing.
- **Mono capitals** outside chart axes and the work ribbon (already the rule; the badges now obey it).
- **Jargon in the default view**: rung and A0 to A2 (say Watching, Asks first, Runs on its own), ledger (say "record of what was sent"), shadow (say "watch first"), genome (say "where time goes"), occurrence (say "step"), n and interval on a worker screen.
- **Apology and blame**: "oops", "invalid", "you missed". Errors say what happened, then what the person can do, then what was not touched.

### Where explanation lives instead

| Kind | Home for it |
|---|---|
| A unit, a definition, an interval, an n beside a figure | Hint (20 words) |
| A reason, a method, a list | the screen's own Details disclosure |
| "What is this screen and where do the numbers come from?" | "About this screen" side panel, opened with ⌘/ or the palette's "Explain this screen" |
| A fact the worker must see (origin, consent, "it will never", a consequence, an error, a limit, the kill state) | **printed, always**; this is D45 and does not change |

### Voice

Calm, plain, second person, present tense, sentence case. Specific verbs. No hype, no exclamation marks, no emoji, no guilt, no countdowns. Knack speaks in the first person only inside the corner card ("Knack noticed a repeat") and never claims feelings. Numbers as digits with units. A consent says what will happen and gives "Not now" and "Never" the weight of "Yes".

### Before and after: twelve real strings

| # | Where | Before | Words | After | Words |
|---|---|---|---|---|---|
| 1 | Home lede | "9 to 15 November. Chosen by fixed rules, not by a model." | 12 | "Week of 9 November" (the method moves into "Why this?") | 4 |
| 2 | Home pointer body and button | "Open Growth to see where the time goes." and a button "Open Growth" (twice on one screen) | 10 | button "See where the time goes" | 5 |
| 3 | Home note under the cards | "An example week from the synthetic firm stands in for this profile." | 12 | badge "Example data" (the sentence is its Hint) | 2 |
| 4 | Growth, nothing counted | "An occurrence is counted each time a step from your role's pack comes up in your real work. You do not have to do anything extra. Here is what will appear, and when." plus a ghost chart and a three-item list | 33 | "Your curve starts after 10 steps." | 6 |
| 5 | Growth lede | "This shows how much less help you need, not how expert you are." | 13 | "Measures help needed, not expertise." (printed: it is a limit) | 5 |
| 6 | Routines lede | "Suggested between tasks. Nothing runs until you say so." | 9 | none (the consent captions carry it) | 0 |
| 7 | Routine choice caption | "It works in the background and asks before anything outward." | 10 | "Asks before it submits or sends." | 6 |
| 8 | Queue lede | "Anything that cannot be undone, or reaches outside, waits here for one click." | 13 | none | 0 |
| 9 | Queue empty | "All clear. When a routine reaches a step it may not take alone, it stops and a card appears here with the evidence." | 23 | "Nothing needs you. Knack asks when a step cannot be undone." | 11 |
| 10 | Notices lede | "Choose how loudly each kind of notice speaks. Safety stops and blocking approvals always show." | 15 | "Stops and blocking approvals always show." under a three-way control | 6 |
| 11 | Memory lede | "One Markdown file on this device, owned by you. Only your own actions and approvals can change it." | 18 | "What Knack remembers. Only you can change it." | 8 |
| 12 | Firm badge | "NAMES ARE MADE UP. THIS FIRM IS SYNTHETIC." (mono capitals) | 8 | "Synthetic firm" (the sentence is its Hint; on Evidence it stays printed) | 2 |

Also: the Details-screen frame note (16 words and a link) becomes a breadcrumb; the stop toast "Stopped. No service was reachable, so nothing was running. With no service running, this only changes the screen." (18) becomes "Stopped. No service was running." (5) when no service answered and "Stopped." (1) otherwise; the sidebar's two fold hints (14 words) become "More" (1). Total on these fifteen strings: 224 words before, 61 after.

---

## 6. Visual system

Keeps `packages/design/tokens.css` and the ten rules of `packages/design/README.md` (one hero per screen, no gradients or glows, no accent bars, hairlines for structure, Hints never the only copy). What changes is restraint and consistency.

### Type scale and weights (existing tokens; five sizes in use)

| Role | Token | Size and line height | Face and weight |
|---|---|---|---|
| Hero insight, first-run question | `--text-2xl` (first-run: `--text-3xl`) | 28 and 1.2 (first-run 40) | display 600 |
| Screen title, card title | `--text-xl` | 22 and 1.25 (card title: `--text-md` 16 at 600) | display 600 |
| Reading text (memory file, a sentence in a card) | `--text-md` | 16 and 1.5 | body 400 |
| Row, control, label, muted line | `--text-sm` | 14 and 1.4 | body 400, 600 for the row title and labels |
| Data, axis, time, interval | `--text-xs` | 12 and 1.4 | mono 400 |
| Key number (one per chart) | `--text-3xl` | clamp 28 to 40 | display 600, tabular |

Weights: 400 and 600 only (no 500, no 700). Labels are sentence case in the body face at 600; the mono capitals stay for chart axes and the work ribbon. Tabular figures wherever numbers align.

### Space, rhythm, density, width

Base unit 4 px. Steps in use: 8 (inside a row, label to value), 12 (row padding), 16 (between rows, title to content), 24 (between sections), 32 (page top), 40 (page sides). **One left-aligned column** starting 40 px from the sidebar on every screen, two widths: reading (720 px: Home, Needs you, Routines, Your data, Settings) and wide (1080 px: Growth, Genome, Firm views). Never centred; the left edge does not move between screens. Row height 44 px, control height 32 px, sidebar item 32 px, table row 36 px. The window minimum is 800 by 560, so the 390 px layout belongs to the web build (bottom bar) only.

### Surfaces, borders, shadows

At most three surface levels on any screen: the canvas (`--bg`), a raised `--panel` for a separate object (a proposal, an approval, a notice: never for a section), and `--sunk` for code and evidence. The sidebar is canvas with a hairline. Lists are hairlines, not stacks of cards: at most one card stack per screen. Hairline (1 px `--line`) for all structure; shadow only on layers that float above other apps or content (`--elev-2`: the corner pill, the corner card, the palette, a popover). No shadow inside the page.

### Motion

State changes only, with the existing durations: hover and press 140 ms, a disclosure 240 ms, a card arriving 360 ms, the ring landing 560 ms, fade 900 ms. The pill arrives by opacity (no slide), collapses to a check in 240 ms, fades in 240 ms. Reduced motion zeroes every duration (existing). Nothing loops. Progress is a count ("3 of 8"), not a spinner; when the length is unknown, the pill shows the label alone.

### Icons

One inline SVG set, 16 px grid, 1.5 px stroke, `currentColor`, no dependency. Fourteen icons: home, needs-you (bell-less: a circle with a dot), routines (two arrows), growth (rising line), your-data (stacked lines), more (three dots), stop (square), check, alert (triangle), chevron, info, search, plus, close. Icons sit beside nav items, the pill's glyph and rows; never inside primary buttons (a verb needs no picture), never as decoration, never emoji.

### Empty-state policy

No illustration, no mark, no icon box. A title (5 words), one line (10 words), at most one action. The current `.state__mark` is retired.

### Dark mode

Both themes designed together (existing tokens, AA contrast tested by `design-tokens.test.ts`). The corner column uses `--panel` and `--line`, so it reads on any app behind it; the pill's red square uses `--bad` (a lighter tone in dark); the check uses `--good`. `docs/knack-ux/06-corner-states.svg` shows both. The macOS window background follows the OS appearance; `backgroundColor` is set from the token to avoid a white flash.

### The brand lockup (glyph plus the word Knack; `docs/knack-ux/knack-brand-sheet.svg`)

The mark already in `packages/design/brand/` is kept: a solid disc with a ring offset behind it (the worker, and the understudy shadowing them). The product name changes; the geometry does not.

- **Lockup:** the glyph, then the word "Knack" in the display face at 600. **The disc is as tall as the capital K** (so the word is about 0.87 of the glyph's height). Gap between glyph and word: one disc radius.
- **Clear space:** one K on every side.
- **Colour in the UI:** disc in `--fg`, ring in `--accent`, both full strength (the existing `understudy-glyph.svg` draws the ring at 62% in `currentColor`; use that file only on single-colour surfaces: the menu bar, a monochrome favicon, print).
- **Sizes and where the mark appears:** sidebar top: glyph 20 px with the word at 17.5 px (replaces the orange and blue bars the dashboard draws today). First run: glyph 56 px alone above the question. Corner pill: glyph 14 to 15 px alone. Favicon and the browser tab: the currentColor glyph at 16 px. Window title bar: native title text "Knack" only, no drawn mark (the traffic lights are the chrome). Dock: the existing ink tile with the teal ring, on the macOS 1024 canvas with an 824 px tile (icns from `apps/desktop/scripts/make-icons.mjs`). Menu bar: the template glyph, 18 and 36 px, with six states (idle, working dot, needs-you count, glance ring, stopped square, and paused, which keeps today's disc with two bars), in the priority stopped, needs you, glance, working, paused, idle.
- **Never:** recolour the ring for status (status is the pill text and the menu-bar badge), add a gradient or glow, set the word in capitals, or put the mark inside a rounded tile in the UI (the tile is for the Dock only).
- **Tagline:** none inside the app.

### Tokens and components to add

Tokens (add, never rename): `--sidebar-w: 208px`, `--content-read: 720px`, `--content-wide: 1080px`, `--row-h: 44px`, `--control-h: 32px`, `--pill-h: 32px`, `--corner-w: 340px`, `--corner-inset: 16px`, `--text-corner: 0.8125rem` (the corner column only: it sits beside other apps' interfaces and 13 px keeps the pill at 32 px; everything else uses the scale).

Components to add: `navitem` (icon, label, count; restyle of `nav__link`), `row` (44 px, hairline, trailing chevron or action on hover and focus, always visible on touch), `hero-insight`, `inline-banner` (the needs-you or stopped line inside the window), `account-menu`, `more-sheet`, `settings-sheet`, `confirm-row` (the inline "Forget it / Keep" row), `corner-pill`, `corner-card`, `lockup`, `kbd`. Restyle `pill--origin` (today uppercase, tracked, 11 px): sentence case in the body face at 12 px and 600, dashed border kept (dashed means synthetic). Drop the 500 and 700 font imports in `apps/dashboard/src/main.tsx` (weights are 400 and 600 only). Components to retire: `framenote`, `datanote` (replaced by `status-line`), the eyebrow slot of `PageHead`, `state__mark`, `killbar` as a permanent bar (it remains as the in-window stopped banner), the fixed `kill--fixed` button (it becomes the sidebar Stop button). New: `status-line` (replaces `datanote`) and `stop-button`.

---

## 7. The window and the overlay

The full state machine, with a table of 18 transitions, the corner priority list and the surface map, is in `docs/knack-ux/08-window-states.md`; the pill and card in every state, light and dark, are in `docs/knack-ux/06-corner-states.svg`. The numbers and the code changes are here.

### Today (from `apps/desktop/src/main`)

The "dock" is a floating always-on-top panel (320 by 64 compact, 360 by 580 expanded, bottom-right); closing it only hides it; there is no `activate` handler, so clicking the Dock icon does nothing; the dashboard is a separate browser tab opened from the menu bar at the Today screen; the HUD (Stop pill, proposal card, notice card) is bottom-left and the Stop pill shows only while an agent acts; permission prompts are a separate 400 px toast at the top-right; the Cue panel and the ring overlay are separate windows; the menu-bar menu has up to 17 rows and a click toggles the dock panel; services (engine 7700, agent 7710, sandbox sites 7801 to 7803) are started by `make dev`, not by the app; `window-all-closed` quits only if there is no menu-bar item; `launchAtLogin` exists and is off.

### The default window

| Property | Value |
|---|---|
| Size (first launch) | **80% of the work area's width by 84% of its height**, width clamped to 960..1440, height to 600..1000. On 1440 by 900 (work area 1440 by 875): 1152 by 735. On 1920 by 1080: 1440 by 886 |
| Minimum, maximum | minimum 800 by 560 (the sidebar becomes an icon rail under 880 px); maximum is the display; full screen allowed, never restored on launch |
| Position | centred horizontally, a little above centre vertically (40% of the free height) |
| Remember | size and position per display id, saved 400 ms after a move or resize; used only if at least 60% of the window is inside a current display's work area, else the default is recomputed; the first launch ignores it |
| Chrome | `titleBarStyle: hiddenInset`, traffic lights at 16 px from the corner, native title "Knack" (Mission Control, Window menu), solid `--bg` (no vibrancy), sidebar top 40 px is the drag strip |
| App name | `app.setName('Knack')` first thing (menu bar app name, Dock label, notifications) |

### What each close and quit does

| Action | Does | Never |
|---|---|---|
| Minimise (yellow, Command-M) | window to the Dock | stops a run |
| Close (red, Command-W) | hides the window (the page stays alive for a fast reopen); app, menu bar and Dock icon stay | quits, hides the Dock icon, stops a run |
| Dock icon click or Activate | from closed: opens on Home at the last size and place; from minimised: restores where it was; behind other windows: brings to front | opens a second window |
| Command-H | hides the app | |
| Quit (Command-Q, Dock menu, menu bar) | quits at once if nothing runs; otherwise a sheet: "Knack is working. Stop it and quit?" [Stop and quit] [Keep working]; if a routine set to run while away is due in 24 hours, one more line says it will not run while Knack is closed | quits silently over a running job |
| Command-Shift-K | stops everything (when Knack is frontmost). The global key stays Option-Shift-Command-K: it exists, is tested, and does not take a common shortcut from other apps | |
| Shift-Esc | stops everything in the window (exists) | |
| Dock menu | Needs you (n), Pause for 1 hour, Stop everything | bounces the Dock icon, ever |
| Open at login | off by default; asked once, in context, after the first "Watch first" ("Open Knack when you log in? Routines only run while Knack is open."); a login launch shows no window, only the menu bar and Dock icon | opens a window at login |

### State machine in brief (rows 1 to 18 in `08-window-states.md`)

- **First launch:** the window opens centred at the default size on first run (section 8); the menu bar and Dock icon appear; the engine and agent start as child processes, and the window waits for them only after click 3.
- **Idle:** the window may be open, minimised or closed; the Dock icon and menu-bar item are present; no corner window exists (the HUD hides itself when it has nothing to show, as it does today); the menu bar shows the idle glyph, and a count when something needs the worker.
- **Working:** when a run that clicks or types on the worker's own screen or browser starts, and the main window is focused, the window **minimises itself** after 400 ms (to the Dock, so a Dock click restores it); the pill appears. A sandbox job, or a run started while the window is not focused, does not move the window. The setting "Move aside while Knack works" (on) turns it off; the pill shows either way.
- **Needs you:** one card above the pill; never a modal; it does not take focus; it never restores the window; the button "Review" opens the window on that item.
- **Done:** the pill becomes a check for 2.5 s, fades in 240 ms and the corner window hides. **The window does not pop back.** A result that needs a look raises the badge and appears in Needs you; the digest card tells the worker once, on return.
- **Error:** the pill turns to an outlined error state and stays until acknowledged, then becomes a menu-bar marker. **Kill:** the "Stopped" card replaces the pill and stays until Resume; the window, if open, shows an in-window banner. Both are always visible.

### The corner pill

| Property | Value |
|---|---|
| Place | **bottom-right** of the work area (excludes the menu bar and the Dock), **16 px** inset from the right and bottom edges; the card sits above the pill with an 8 px gap and grows upward. Draggable to any corner (snaps, 16 px inset), remembered per display id as `cornerPosition` |
| Pill size | 32 px high, 176 to 320 px wide, radius pill, 12 px side padding, 8 px gap; glyph 15 px; label at most 5 words (`--text-corner` 13 px); "n of m" in mono 11 px only when known; a divider; Stop (a 8 px red square and the word "Stop", hit area 60 by 32 px) |
| Card size | 340 px wide (300 to 360), padding 16, radius 6, at most about 160 px tall, at most two buttons ("Review" primary, "Later") |
| Opacity | 100% for 8 s after any change, then 85%; 100% on hover or focus; a card is always 100% |
| Click-through | the window is sized to its content (the existing `fit()` trick in `hud.ts`) and never takes focus (`focusable: false`, a non-activating panel), so there is no transparent surround to block clicks; the first 600 ms after a card appears ignore clicks (a mis-click guard) |
| Pointer rule | a non-safety card is held while the pointer is within 160 px of its place (up to 10 s, then drawn at the corner farthest from the pointer); safety cards are drawn at once at the corner farthest from the pointer |
| Never over a password or payment field | while macOS secure input is on, or the frontmost app is on the denylist, or the awareness probe reports a password or payment field: non-safety cards are held (the menu-bar count carries them). Safety cards still show, with the content-free wording the attention layer already uses, at the corner farthest from the pointer |
| Expiry | a safety card 30 s then a marker; an approval, blocked run or deadline card 20 s then a marker (one reminder 20 min later, as the attention layer already says); the digest card 15 s; hover pauses the timer; the close button means "Later" |
| Multi-display | the pill goes to the display holding the pointer when it first appears (the display of the target window when the run names one) and stays there until done; the card follows the pill; with no pill the card uses the pointer's display. The ring overlay is primary-display only today; per-display overlays are a known limit, not tonight's work |
| Full-screen apps and Spaces | the existing window level (`screen-saver` plus 2) and `visibleOnFullScreen` stay; the pill is content-protected so a screen share never shows it |
| Screen sharing or a call | cards are held (hard quiet); the pill and the kill card still show to the worker (and not in the share) |
| Reduced motion | opacity only, no slide |

### How the older windows relate (never two competing overlays)

At any instant: at most one corner pill (a status), at most one interrupting surface (a corner card, an on-target Cue card, or the Ask bar), plus passive markers (the ring, the menu-bar state, the Dock badge, the in-window banner). Priority for the corner card is Stopped, safety, approval blocking a job, time-sensitive, digest, then a Cue card that has no target. The Ask bar holds every card except Stopped and safety while it is open. Cue cards anchored to an on-screen target belong to the annotation layer and are dropped (reason `agent_acting`) while Knack is acting and while any corner card is up. The ring overlay is hidden while the Knack window is focused (the coach does not annotate its own app) and draws no label while the agent acts. The dock panel is not drawn: a hidden window stays only as the microphone and Live audio host until that code moves; chat becomes the Ask bar and the voice pill, profile becomes Your data, settings become Settings, files become Settings and set-up becomes first run.

### Rejected for this section

- **Top-right for the pill.** macOS banners and Notification Center live there, so a card would collide with them. **Bottom-left** (the HUD's place today): chat sidebars, status bars and avatars sit there in the apps people use all day. Bottom-right is where the retired dock panel was, where Cue already falls back to, and it is free of both; the pill can be dragged if it covers something.
- **The window popping back when a run finishes.** It takes the screen from whatever the worker moved on to. The Dock badge, the menu-bar count and the digest say it is done.
- **Hiding the Dock icon when the window is closed** (an accessory app). The owner asked for the Dock icon; closing a window is not leaving the app.
- **An always-on-top main window.** It would sit over the very app the agent is working in.
- **A full-screen translucent status layer.** The ring overlay already owns the screen and is passive; a second one would block clicks.
- **A macOS Notification Center banner for every card.** It cannot be non-focusable, cannot carry Stop, and cannot be silenced from Knack. The existing native notification for a permission prompt stays; nothing else uses one.
- **A permanent in-window Stop bar.** The sidebar Stop button, the keyboard and the menu bar already reach it, and the pill carries it while something runs.

### What in the code changes

| File or area (`apps/desktop/src/main`) | Change |
|---|---|
| `windows.ts` | add the main window (new `mainwindow.ts`, `window-state.ts`); the old dock window stays hidden as the audio host; `close` hides; no always-on-top on the main window |
| `index.ts` | `app.setName('Knack')` (in an electron-builder build `productName` does the Dock label; in dev the Dock label stays Electron's); `app.on('activate')` shows the window; `window-all-closed` never quits on macOS; `before-quit` runs the quit sheet; start and stop the engine, agent and (for the sandbox sites) the sandbox as child processes in live mode when a Gemini key is present and in mock mode otherwise, reusing a service already listening; open the dashboard bundle in the main window instead of the browser |
| `hud.ts`, `hud-model.ts`, `renderer/hud/*` | extend into the corner column: bottom-right (`hudBounds` becomes `cornerBounds`), new state `activity {label, step, of, phase: working, done, error, voice}`, the done timer, the error hold, the card slot; the existing Stopped card, proposal card and notice card keep their actions |
| new `shell-machine.ts` | pure reducer for the 18 transitions; effects: minimise the main window, show or hide the pill, route a card |
| `toast.ts` | permission prompts render as a corner card (priority 3); the answer is still a real click validated by the confirm broker (`adoptOwner` for the corner window). If that slips, the toast stays top-right in phase 1 and is the only documented exception |
| `tray.ts`, `resources/tray` | 8-row menu; a click opens the menu; icon states (idle, working dot, needs-you count, glance ring, stopped, paused) |
| `hotkey.ts` | Option-Space: tap opens the Ask bar, hold talks (today it is hold only); Option-Command-P becomes pause or resume (the panel toggle is retired); Command-Shift-K in the app menu |
| `attention/adapter.ts`, `attention-wiring.ts` | `cuePort().admit` refuses unasked "now" items while an agent acts (reason `agent_acting`, a local check, no engine change; a cue the worker asked for still shows); the digest and notices render in the corner column; the Dock badge and Dock menu read the needs-you count |
| `login-item.ts` | handle `wasOpenedAtLogin` (no window); the one-time contextual prompt |
| `settings.ts` | retire `showDock` (ignored on load); add `moveAsideWhileWorking` (true), `cornerPosition` |
| `cue/place.ts`, `cue/panel-window.ts` | the no-target fallback docks into the corner column and yields to any card |

---

## 8. First run

Target: three clicks and no wall of text, from first launch to the first insight. The wireframes are in `docs/knack-ux/07-first-run.md`.

| Click | Screen | Words | What happens |
|---|---|---|---|
| 1 | "What work do you do?" three role cards (a pack is a card, at most five) | about 26 | choosing a card advances; the role pack's safe defaults are applied to the memory file: its tools, risky actions set to "never without me", short tone, gradual pace, its hours |
| 2 | "Let Knack learn from your work?" "It records when you are active, never what you read: no page text, no URLs, no field values. The record stays on this laptop." Yes, learn my times / Not now / Never; a "Times only" Details | about 48 | capture on (Yes), or off and asked again after a week (Not now), or off and never asked again (Never); equal weight |
| 3 | "Here is what Knack will remember." four plain lines from the file just written, "Edit any line later in Your data." and one button | about 40 | "Show my week" opens Home |

The first insight is on Home immediately: the example insight, badged "Example data", with "This is an example. Knack starts counting now." (see `01-home.md`). If capture was declined, Home says "Knack is learning your work." instead. Nothing else is asked.

Not at first run, each asked once in context with one sentence and one button: screen glances (a frame sent to a model; off until chosen, in Your data), the microphone (the first time the worker holds Option-Space), Accessibility and Screen Recording (the first time Knack must point at or act on the screen; macOS requires the owner to grant them in System Settings, a human-only step), Open at login (after the first Watch first).

The engine and agent start from the moment the app opens (warm-up is about 20 s per `/health`). Screen 1 is static and does not wait; if Home opens before they answer, it says "Starting Knack, about 20 seconds." and fills when they do; after 30 s it says what is wrong and offers Try again.

Replaces: the desktop's eight-step set-up (`renderer/dock/onboarding`) and the dashboard's seven-question Onboarding. The latter stays reachable as Settings, "Set up again" (the questions are the pack's, shown once more, one per screen).

Rejected: a tour as part of first run (the "Take the tour" row stays in the account menu); asking tone, pace and hours (defaults are editable, and three clicks is the budget); a memory-file preview that builds while answering (one idea per screen; it is shown once, on screen 3).

---

## 9. Keyboard and the command palette

| # | Command | Shortcut |
|---|---|---|
| 1 | Go anywhere or run a command | ⌘K |
| 2 | Ask Knack (tap to type, hold to talk) | ⌥Space (exists as the hold-to-talk key) |
| 3 | Stop everything | ⌥⇧⌘K anywhere (exists); ⇧⌘K and ⇧Esc inside Knack |
| 4 | Pause or resume for an hour | ⌥⌘P (reuses the retired panel toggle) |
| 5 | Home | ⌘1 |
| 6 | Needs you | ⌘2 |
| 7 | Routines | ⌘3 |
| 8 | Growth | ⌘4 |
| 9 | Your data | ⌘5 |
| 10 | About this screen | ⌘/ |
| 11 | Settings | ⌘, |
| 12 | Delete my data | palette only, **no shortcut by design** |

Standard macOS keys do what macOS does: ⌘W hides the window, ⌘M minimises, ⌘H hides the app, ⌘Q quits (with the sheet when something runs), ⌘[ goes back. In a list, the arrow keys move focus and Space opens the evidence. **No keystroke approves anything**; approval is a click, as it is today.

Palette: seven rows by default then "Show all N" (exists); groups Go to, Do, Ask. New rows: Pause for 1 hour, Stop everything, Ask Knack…, Copy my Monday note, Delete my data, Switch to Admin view, Explain this screen, Take the tour, Open System Settings for Accessibility. Typing a phrase that matches nothing adds a last row "Ask Knack: <phrase>" which opens the Ask bar with the phrase filled in. The "This week" and "Firm insights" groups stay. Hints stay in the palette (not in the sidebar).

---

## 10. Build plan

Four implementer agents, four directories, no shared files. The lead owns `docs/`, the Makefile and merges. Start 23:00 UTC; freeze 08:00 Sunday (CLAUDE.md).

### Order and dependencies

```
 23:00  D0 tokens, components, lockup, lint and budget scripts   (SYSTEM, first 60 min)
 23:00  B0 router and navModel contract, route redirects         (SHELL-WEB, first 30 min, pure)
 23:00  A1 window, activate, close, quit                         (SHELL-DESK, independent)
 23:30  C1 starts once B0 and D0 land; B1, B2, A2, A3 run
 02:00  phase 2: C2, C3, D2, A4, A5, B3
 05:00  phase 3: polish, light and dark at 1440 by 900, 390 by 844 and the 1152 by 735 window; the owner's walkthrough
 08:00  freeze
```

Cut lines if late: P2 items (Ask bar window, per-display pill, mobile bottom bar, login prompt, Roles drill-down) go first; then the corner confirm card (the toast stays); P0 is never cut (window, Dock, minimise-on-work and the pill, five-item nav, Home hero, Needs you, three-click first run).

### Track A: SHELL-DESK, the lead's KNACK-SHELL (`apps/desktop/**`)

| Step | Priority | Work | Proof |
|---|---|---|---|
| A1 | P0, 90 min | `window-state.ts` (default 80 by 84, clamps, restore rules), `mainwindow.ts`, activate, close hides, quit sheet, `app.setName('Knack')`, Dock menu and badge, services started and stopped by the app. Packaging with electron-builder (lead decision): `productName` Knack, so the Dock label reads Knack outside dev; unsigned local app and dmg | `window-state.test.ts`: table cases for 1280 by 800, 1440 by 900, 1920 by 1080, 2560 by 1440, a removed display, a half-offscreen save; `mainwindow.test.ts` with a fake window: close hides, activate shows, quit with a running job asks |
| A2 | P0, 90 min | `shell-machine.ts`: the 18 transitions as a pure reducer with effects | `shell-machine.test.ts`: one test per row of `08-window-states.md`; invariants: never two cards, the window never restores except after a Review click, kill always wins |
| A3 | P0, 60 min | the corner column: `hud-model.ts` activity, `cornerBounds` (bottom-right, per display), pill, done, error, card renderer in the new look | extend `hud-model.test.ts`, `HudView.test.ts`; `corner-place.test.ts` (inset 16, card above pill, drag snap, display change); a light and dark screenshot through the existing `hudPng` debug route compared by eye to `06-corner-states.svg` |
| A4 | P1, 60 min | 8-row tray menu and icon states, Option-Space tap and hold, ⌥⌘P, ⇧⌘K, login prompt, the rename pass over desktop strings (tray, toast and notification titles, window titles, `Quit Knack`, `Talk to` becomes `Ask Knack`) | `tray.test.ts`: at most 8 rows, the states and their priority; `login-item.test.ts`: a login launch shows no window |
| A5 | P1 | permission prompt as a corner card; `agent_acting` refusal in the cue port; digest and notices in the corner | `attention/adapter.test.ts`: unasked now-items refused while acting, asked ones still shown; `confirm.test.ts`: an approval still needs a real click |
| A6 | P2 | Ask bar window; retire the dock panel UI; per-display pill | manual with the owner |

Dev hook for proof without real input: the existing debug server (`ALONGSIDE_DEBUG=1`) gains `POST /hud/activity` to drive working, done and error, and `GET /state` reports the main window's visibility and bounds. `scripts/shell-smoke.mjs` uses it. No real click, keystroke or capture is needed (the minimise happens to Knack's own window).

### Track B: SHELL-WEB (`apps/dashboard/src/{App.tsx,router.ts,main.tsx,components/home/**,screens/Home/**,screens/FirstRun/**}`)

| Step | Priority | Work | Proof |
|---|---|---|---|
| B0 | P0, 30 min | new `router.ts` screens and `navModel.ts` (five worker, three admin, More at most ten, and `PINNED_VIEWS`, above), `routeRedirects.ts` for every old route | `navModel.test.ts`: exactly 5 worker and 3 admin primary entries, More at most 10, every old route redirects; `jobs.test.ts`: every job in `docs/knack-ux/jobs.json` has a path within budget over the nav graph |
| B1 | P0, 90 min | `Sidebar.tsx`, `AccountMenu.tsx`, `MoreSheet.tsx`, `SettingsSheet.tsx` shell, retire `framenote` and `datanote`, ⌘1 to ⌘5, ⌘, and ⌘/, one left-aligned column, bottom bar at 390 px | `scripts/check-clicks.mjs` (replays the ten paths; fails above budget); `scripts/check-copy.mjs` sidebar rule: at most 6 rows, 0 hint words |
| B2 | P0, 90 min | Home hero and states per `01-home.md`; `FirstRun` (three screens) replaces Onboarding as the entry; the rename pass in shell strings | `screens/Home/model.test.ts` (title template, at most 16 words, one quantity); `oneQuantity.test.ts`; `firstRun.model.test.ts` (three states, one click each); `check-clicks.mjs` "launch to Home" at most 3 |
| B3 | P1 | palette verbs and "Ask Knack" row; "About this screen" panel | `palette.test.ts` extended |

### Track C: DECISIONS AND DATA (`apps/dashboard/src/screens/{NeedsYou,Routines,YourData,Settings}/**`, plus the pieces moved out of Queue, Briefing, Repeats, Memory, Privacy, Notices, Agents, Models)

| Step | Priority | Work | Proof |
|---|---|---|---|
| C1 | P0 | Needs you from Queue, Briefing and the proposal card (`02-needs-you.md`) | `check-copy.mjs`: Needs you at most 120 words above the fold, 0 long paragraphs; J2 at most 2 clicks, J3 at most 2 |
| C2 | P0 | Routines (Running, Could automate) per `03-routines.md` | same budgets: 100 words; "Run now" only if the endpoint exists |
| C3 | P1 | Your data: remembers, measures, looked at or sent, what your admin can see, glance and capture switches, "Delete everything". No file path in the default view (today's seeded home is named `demo-home`, which would put the banned word on screen; the path sits behind a Hint, and the lead may rename the seeded home) | J5: see in 1, delete in 3; delete wording identical in every section; honesty lines kept (text assertions in the existing smoke test) |
| C4 | P1 | Settings contents (Interruptions three-way plus per-kind disclosure, Coaching, Move aside, Open at login, Appearance, Views, About; "Use live models" first) | `Settings.test.tsx`: "Stops and blocking approvals always show." is rendered; "Use live models" is disabled with its printed line when no key is found, and while a job runs |

### Track D: SYSTEM AND INSIGHT SCREENS (`packages/design/**`, `apps/dashboard/src/screens/{Growth,Firm,Genome,Presence,Graph,Week,Git,Predictions}/**`, `apps/dashboard/scripts/**`)

| Step | Priority | Work | Proof |
|---|---|---|---|
| D0 | P0, 60 min | tokens and components of section 6, lockup component, icon set, the lockup and tray SVGs into `packages/design/brand/`, `check-copy.mjs` (budgets from section 5 as `qa/knack/budgets.json`), `check-clicks.mjs` skeleton | `design-tokens.test.ts` extended (new tokens present, AA pairs hold); `design-system.html` rebuilt with `node packages/design/build.mjs`; the measurement baseline committed |
| D1 | P0 | Growth per `04-growth.md`; Firm, Roles, Onboarding per `05-admin-firm.md` (retire the tab strip, one origin badge) | budgets: Growth at most 60 words with data, Firm screens at most 150; honesty: origin badge and printed n and intervals on Admin screens still asserted |
| D2 | P1 | Genome, Presence, Graph, Week, Git, Predictions: cut ledes, legends and notes to the budgets; breadcrumb in place of the frame note | `check-copy.mjs` on each: at most 120 words above the fold, 0 long paragraphs, at most 1 pill |
| D3 | P1 | the copy lint: banned phrases and a user-visible "Understudy" scan | `copy-lint.test.ts` scans source strings and rendered text; the allow-list is internal identifiers only |
| D4 | P2 | Evidence stays whole; only its entry point and header chrome change | existing Evidence smoke stays green |

### Dashboard code map (what each existing file becomes)

| Existing file (`apps/dashboard/src`) | Action | Track |
|---|---|---|
| `App.tsx` | split the shell into `Sidebar`, `AccountMenu`, `StatusLine`, `StopButton`, `Lockup`; remove `DataNote` (becomes the status line), `ThemeSwitch` (to Settings, Appearance), `AuthControl` (into the account menu), `Wordmark`; `KillSwitch` keeps its logic, its button becomes `StopButton`, its bar stays as the in-window stopped banner | B |
| `router.ts`, `components/home/navModel.ts` | new screen ids, five worker and three admin entries, More, `PINNED_VIEWS`, redirects for every old route | B |
| `components/home/RoleNav.tsx` | replaced by `Sidebar` (no folds) | B |
| `components/home/ScreenFrame.tsx` | keep the admin gate, remove `framenote`, add the breadcrumb | B |
| `components/home/ViewAsSwitch.tsx` | moves into the account menu | B |
| `components/home/PointerCard.tsx` | becomes the hero and the quiet row | B |
| `components/home/CommandPalette.tsx`, `palette.ts`, `GuidedTour.tsx`, `tour.ts` | new rows and verbs; tour steps follow the five destinations | B |
| `components/AttentionBanner.tsx` | retire: the sidebar count and the Home row say the same thing | B |
| `components/common.tsx` | `PageHead` loses `eyebrow` and the default lede; `SourceNote` shrinks to the badge and its Hint; the slow-loading sentence ("The first request after the engine starts can take several seconds while it works the numbers out. Nothing is wrong.", 24 words) becomes "Starting Knack, about 20 seconds." | D |
| `components/ui.tsx`, `components/Hint.tsx` | add `Row` and `ConfirmRow`; `Details` and `Hint` stay | D |
| `styles/app.css`, `components/home/home.css` | one left-aligned column, sidebar, status line; delete `.datanote`, `.framenote`, `.kill--fixed` | B (shell), D (tokens) |
| `screens/Queue.tsx`, `Briefing.tsx`, `Routines.tsx`, `Repeats/` | become `NeedsYou/` and `Routines/` | C |
| `screens/Memory.tsx`, `Privacy.tsx`, `Presence.tsx` (hours), the Growth ledger | become `YourData/` | C |
| `screens/Notices.tsx`, `Models.tsx`, `Agents.tsx`, `Today.tsx`, `Onboarding.tsx` | Settings sections, More rows, a live strip on Home, `FirstRun` | C and B |
| `screens/Growth/`, `Firm/`, `Genome.tsx`, `Presence.tsx`, `Graph.tsx`, `Week.tsx`, `Git.tsx`, `Predictions/` | copy cuts to the budgets; Firm loses its tab strip | D |

### Rules for every implementer

> 1. **Read first:** this file, `docs/knack-ux/*`, `docs/ATTENTION_DESIGN.md`, `packages/design/README.md`, `docs/DECISIONS.md` D45. Do not reopen section 3's list of five.
> 2. **One hero per screen.** One left-aligned column; two widths; no eyebrow, no lede unless it is a real limit.
> 3. **Budgets are tests.** Section 5's word, paragraph, pill, control and sidebar budgets are enforced by `check-copy.mjs`; the click budgets by `check-clicks.mjs`. A change that raises a number is a decision: send it to the lead, who records it in `docs/DECISIONS.md`.
> 4. **Never hide an honesty item.** The origin badge, consent text, "It will never", the consequence of an irreversible step, errors, limits, the kill and glance states, n and intervals on Admin and Evidence stay printed. A Hint is never the only copy of one. Existing smoke assertions for these are not loosened.
> 5. **No keystroke approves.** An approval is a real click. Safety is never held, batched or repeated.
> 6. **Rename in what people see**: "Knack" in strings, titles, tray, notifications, window titles, aria labels. Internal identifiers, env names, file names and storage keys keep `understudy`. `copy-lint.test.ts` fails on a visible "Understudy".
> 7. **Stay in your directory.** Cross-track needs go to the lead as a message with the file and the line; do not edit another track's files.
> 8. **No new dependency** without a decision. Icons are inline SVG. Fonts are the bundled ones.
> 9. **Look at it:** light and dark, 1440 by 900, 390 by 844 (web) and the 1152 by 735 window (desktop); keyboard focus visible; reduced motion respected; empty, loading and error states designed. Save before and after screenshots to `apps/dashboard/qa/knack/`.
> 10. **No real desktop input or capture** until spike S2 has passed with the owner present. Corner and window behaviour is proved with the debug hooks and fake runs.
> 11. **Models propose, code decides.** No model text on a surface; fixed templates for the hero, the pill and the cards.
> 12. **Commit small**, push at each checkpoint, end each commit with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; `make test` and the budget scripts pass before a handoff.

### Questions for the owner (answer by default if no reply)

1. Bottom-right for the pill (chosen); say if you prefer the HUD's current bottom-left. (Default: bottom-right.)
2. Kill key: the global shortcut stays Option-Shift-Command-K; Command-Shift-K is added only while Knack is frontmost, because a global Command-Shift-K would take a common shortcut from other apps. (Default: as written.)
3. Does the owner's walk-through need the Admin switch on screen? (Default: account menu, remembered.)
4. "Run now" and "Pause" on a routine need engine support; confirm they exist or accept their absence. (Default: omitted if absent.)

Decided by the lead since the first draft: Genome, Graph and Presence leave the sidebar (Pinned views brings them back); packaging is **electron-builder** (KNACK-SHELL builds the unsigned local Knack.app and a dmg; a signed release needs the owner's Apple Developer ID and notarisation later, a human-only step); provider is Gemini (D49); the live-models status line and the "Use live models" switch (above); no visible string uses the word "demo".
