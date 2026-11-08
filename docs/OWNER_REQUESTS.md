# Owner requests: the checklist

Everything the owner asked for in chat on the night of 7 to 8 Nov 2026, one line each, in the owner's order, so none is forgotten. The lead ticks a box only when the item is built, tested and seen working; a half-done item stays open with a note. Each item names its track. Source decisions are in `docs/DECISIONS.md` (D57 to D63). Updated by the lead; tracks report to the lead, never edit this file.

Tracks: **A** shell and desktop (KNACK-SHELL), **B** web shell, nav, Home, first run (SHELL-WEB), **C** Needs you, Routines, Your data, Settings, Agents (DECISIONS-DATA), **D** insight and firm screens (SYSTEM-INSIGHT), **W** wording, **V** voice and wake (WAKE-VOICE), **H** HRT, **E** connections, **F** role depth, **T** open-ended tasks and skills (new), **R** roles and views, firm data (new), **G** graph design system (new).

## Message 1 (about 00:15)

- [ ] **1.1** Remove "synthetic" from the app everywhere (D57; plain provenance stays true in other words). W plus A to D.
- [ ] **1.2** Improve overall usage and design; think through edge cases for all data shown. B, C, D, A, V (matrices in `docs/knack-ux/edge-cases-*.md`).
- [ ] **1.3** Enable "Listen for Hey Knack" and everything else disabled for the demo; no "demo mode" text. V, A.
- [ ] **1.4** Defaults as automated as possible for every toggle and state, inside the safety rules (`docs/knack-ux/defaults.md`). All tracks.
- [ ] **1.5** Reduce clutter inside expanded dropdowns. C, D, B.
- [ ] **1.6** Polish the whole design and UX to a professional standard. All tracks.
- [ ] **1.7** Everything functional; the lead says when the fresh build is ready. Lead.

## Message 2 (about 00:35)

- [ ] **2.1** Strengthen the HRT position (D59; `docs/HRT_BRIEF.md`). H. *Pre-registered runs done on Track H's branch; Evidence block pending.*

## Message 3 (about 00:45)

- [ ] **3.1** Knack has its own onboarding; Alongside's wizard never shows (D58). A, B. *In main (legacy wizard pinned off, Ask bar, bridge); not yet seen in the rebuilt app.*
- [ ] **3.2** The owner can onboard for a role; first run opens whatever the engine already knows. B. *In main (first run opens on first launch, role choice with an existing identity); not yet seen.*
- [ ] **3.3** Voice features and on-screen annotation work; permissions handled step by step in first run. V, A, B.

## Message 4 (about 00:50)

Worker view and data
- [ ] **4.1** A worker must NOT see firm-wide or other people's data (no insights about everyone). Define and enforce what each view shows (`docs/knack-ux/views.md`). R, B, C, D. *Worker strip merged and audited by Track D (12 of 12 routes pass); full audit rerun pending.*
- [ ] **4.2** A worker does not need model logs: hide Models, call logs, evidence and diagnostics from the worker; bare bones only. R, C, D.
- [x] **4.3** Admin view must not be blank: find the cause and fix it. R. *Seen live 8 Nov 02:15: Firm, Roles, People, Brief, Forecasts, Automation, Risk and Onboarding all draw content for 32 people.*
- [x] **4.4** Fill the admin view with made-up data for multiple users, with no tag anywhere saying it is made up. R (engine seed), D. *Seen live: 32 people in three roles, names and numbers consistent; no tag on any admin screen.*
- [x] **4.5** No "made up" tag of any kind anywhere in the code's visible text (same as 1.1). W. *Words and chips removed app-wide, guard in place (lint ratchet empty); only the closed 'About this data' sentence and Evidence's measured-on column state provenance.*

Device and permissions
- [ ] **4.6** Set up device permissions so everything works. The lead cannot grant macOS permissions (only the owner can, by design); first run walks through each one with an Open System Settings button. B, A, V.

Fixes
- [x] **4.7** The Stop button shows two stop icons: fix. B, A. *One Stop everywhere (pill, sidebar); the old wizard's preview pill is gone; the Stopped card has Resume only.*
- [x] **4.8** The account menu shows the worker's name. B. *Account menu shows name and role; Change profile; Set up again.*
- [x] **4.9** The worker can change their profile (name and role: programmer, analyst, benefits processor, more), not stuck as benefits processor. B, R. *Account menu with name and role change in main; engine route by Track R pending merge.* Role switch seeds for programmer and analyst still being generated (Track R). *Verified on a copy of the live data: POST /profile per role, history kept per role, Home and Growth follow it.*
- [ ] **4.10** Forecasts: a clear, understandable layout, insights on top, data behind, not a data spam. D.
- [ ] **4.11** The same insight-first treatment for every screen. B, C, D.
- [x] **4.12** Admin: Firm brief and the other admin pages are on the main nav. B, D. *Admin nav with Brief and the rest in main; the admin pages' data is pending (Track R).* *Admin nav in main; every admin page draws content live.*
- [ ] **4.13** "How work connects" (the graph layer) uses the old design system: move it to the new one (`Understudy Design System` artifact): icons per node style, no visible text except on hover or click. G. *Merged to main, tests pass; not yet seen in the rebuilt app.*
- [x] **4.14** Bottom-right corner: a Knack pop-up and a "working on, 0 of 1" pill conflict, and the pill stays after the work finished: fix the state and the layout. A. *Root cause fixed on Track A's branch (ghost runs from stale records); merges at the next checkpoint.* *Root cause (ghost run records) fixed, corner column single, regression test in the hidden e2e.*
- [ ] **4.15** Background tasks update live on the page, no refresh needed. C, A, agent service. *Built (SSE plus polling, ghost rules); not yet seen in the rebuilt app.*
- [ ] **4.16** Task and progress UI as minimal as Claude Code's task list. C, A.
- [ ] **4.17** Cluster related things on one page; fewer navigations; everything easy to find. B, C, D (`docs/knack-ux/views.md` navigation map).

Open-ended work
- [ ] **4.18** Tasks are not a preset list: the worker types or speaks any task. T (API contract v1 sent), B (task box), V (voice tool). Owner answers: D63. *Task box and API built; typed task creation not yet seen end to end in the app.*
- [ ] **4.19** Skill files and plugins load into context automatically, like Claude Code. T, E. *Skills index and Claude CLI spawner built and tested; two approved real runs done.*
- [ ] **4.20** Computer use and background agents that can create code. T.
- [ ] **4.21** Background agents show at the top right of the screen as small pills with animated icons while they work. A, T. *Top-right pills built (hidden harness); not yet seen on the owner's screen.*
- [ ] **4.22** Seamless and double-checked end to end; ask questions when in doubt. Lead.

Process
- [x] **4.23** Keep this checklist and tick items off. Lead (this file).
- [ ] **4.24** Use parallel agents. Lead.

## Rules every track follows

Think from the worker's side. Fewer things on screen. The safety layers stay: no consent card is pre-answered, nothing is auto-approved, unattended and irreversible actions stay opt-in per routine, a real click is the only approval. No "demo" or made-up tags in visible text. Fix errors properly; never switch a feature off or loosen a test.

## Message 5 (about 05:00 to 05:30)

- [x] **5.1** Pages load slowly: find the cause and fix it. P1 (profile and cache), lead. *Causes found and fixed: GC thrash on a large heap, per-request re-parsing of events and role packs, abandoned heavy requests piling up, 610k date parses in the growth score. Measured live 8 Nov 05:38: briefing 0.09 s, growth 0.21 s, hitlist 0.001 s warm, routines 0.04 s; /health 35 ms with 12 heavy reads in flight. Window-level polling cut (coach/state 30 s, one Stop poll).*
- [x] **5.2** Remove every example-data pill, tag, banner and sentence from the frontend, and anything that implies one (D57 truth rule kept on the Evidence page). X1, X2. *Dashboard live sweep: 30 screens, 0 on example data, 0 page errors; words guard covers dashboard source, fixtures and the desktop renderer; check-words 0 hits across 44 views.*
- [x] **5.3** Remove the printed "Default: X" from every Settings row. X1. *Gone; the values stay, a test pins that no Default text prints.*
- [ ] **5.4** The owner relaunches Knack.app and presses Resume. *Relaunched 06:0x with the debug port; stop file cleared on the owner's word at 06:12.*
- [x] **5.5** Routines shows developer work for a programmer (hit list read another role's traces; guard added; programmer history reseeded; plain step names). *Seen live 06:00: 7 and 30 day lists show programmer routines; Needs you shows the same.*
- [x] **5.6** First-click rung R1 run and passed with the owner present (06:17); the rung record exists and stays. Typed-task clicking behind one Allow click per task: TASKS-DESKTOP, in progress.
- [ ] **5.7** "The browser agent gave up": root cause found (navigate and search actions not understood); fix in progress (BROWSER-FIX).
- [ ] **5.8** Voice does not hear or speak: stop file was set; new build needs mic and speech grants again; silent failure paths being fixed with a Check voice action (VOICE-FIX).
- [ ] **5.9** Coaching opened a problem page: Today rewritten to read every answer safely, honest Home row, lesson names (merged 06:0x; not seen on the owner's screen).
