# QA-WORKER (Track Q1): the worker's journeys, driven and looked at

Run on 8 Nov 2026 from 02:40 to 03:40 GMT on a PRIVATE stack (own data directory, own ports, no model key, mock off like live, `seed` + `seed-firm` + `seed-growth --role benefits-processor`, a private agent service with the test fake `claude`), driven with Playwright at 1440 by 900, 1152 by 735 and 390 by 844, light and dark, in the Worker view. Nothing touched the owner's stack, keys or accounts. Pictures are kept outside the repository (not committed).

Browser limits: the Knack desktop shell (three consent cards, macOS permissions, the corner pill, Hey Knack) cannot be driven in a browser tab, so those were not exercised here.

Status words: **fixed** (committed on the Q1 branch with a test), **reported** (sent to the owning track, copy to the lead), **open** (not yet sent), **won't fix** (with reason). Priority: P1 breaks an owner rule or a journey, P2 visible polish or confusion, P3 small.

| id | screen, size, theme | what was seen | pri | status |
|---|---|---|---|---|
| Q1-01 | Every screen, 1440 light | The sidebar badge on Needs you counted the SAMPLE person's briefing (the shell asks for the identity and for the count in the same tick), so it said 7 while the list held 2. A worker's screen fetched another person's briefing. | P1 | fixed: `screens/NeedsYou/count.ts` (+ `count.test.ts`) |
| Q1-02 | Needs you and Home hero, Evidence open, 1440 light | A worker saw "Run r_demo_0001" and a routine id in the evidence block, a screenshot placeholder "not available in example data", and an image alt "from run r_..." (run id, the word demo, an example-data tag). | P1 | fixed: `components/needsyou/Evidence.tsx`, `components/home/ApprovalHero.tsx` |
| Q1-03 | Evidence table, 1440 light | Field names printed as code: `calculators_agree`, `case_ref`, `note_fields`. | P2 | fixed: `fieldName()` in `screens/NeedsYou/model.ts` (+ test) |
| Q1-04 | Needs you, 1440 light, fresh load | For about two seconds the screen said "Nothing needs you. Knack asks when a step cannot be undone." (a wrong statement), then "2 things", then "5 things" as the slower sources arrived. | P1 | fixed: loading state until every source has answered once (`firstLoadDone`, + test) |
| Q1-05 | Your data, More (17 more lines), 1440 light | A memory line ended with the note "demo seed" (the banned word, visible); another with the raw code `corr:summary_length=detailed`; three lines with "onboarding 2026-11-08". | P1 | fixed: `cleanNote()` in `screens/YourData/model.ts`, the seed writes "set up for you" (`demo.py`), tests; also takes Your data from 92 to 86 words against its 90 budget |
| Q1-06 | Growth, all sizes, both themes | An "Example data" chip beside the title; the sidebar footer reads "Some example data" on every screen; a yellow banner "Showing example data: the engine could not answer yet." under My steps and My commits; a fragment ". the service reported a problem". Owner rule: no tag or chip of any kind. | P1 | reported to D (af8f7d92471c9a6ba), copy lead |
| Q1-07 | Growth, same stack | Cause of Q1-06: the worker's own person (`GET /identity` gives p_learn01) has no data on four routes: `/calendar/week`, `/calendar/suggestions`, `/genome/t_entitlement_check` and `/git/habits` all answer 404 unknown_person. The same calendar 404 is on the owner's live engine (checked read-only through the :5173 proxy). | P1 | reported to R (a0bfa6509153496b8), copy lead |
| Q1-08 | Needs you, 1440 light | The same routine twice: a prepared action "Automate: Enter the household into three calculators" (Approve and run, Not now, Never) and the proposal "Enter the household into three calculators" (Watch first, Not now). 5 things for 2 ideas. | P2 | reported to lead (Track C not active) |
| Q1-09 | Needs you, "Since you left", 1440 light | "Ran 1: benefits-workflow, approved, 481.3 min" and "Stepped aside 1 ... when you came back at 21:49": an internal slug, a duration that is really time since the item was created, and the phrase "Stepped aside". | P3 | reported to lead |
| Q1-10 | Your data, More, 1440 light | Raw memory lines: `calc-entry-3x \| rung A1 \| consent: shadow \| unattended: not allowed`, `reads-error-first: L1, streak 0, last seen never`, `Checklist: read_case, then calc_a or calc_b ...`. And "Run without my click: submit, close case, approve payment ..." reads as if Knack may do those without asking (it is the list of classes that always need a click). Buttons "Copy location", "Edit as text" are developer words. | P2 | reported to lead |
| Q1-11 | Settings, 1440 light | "Most a task may spend ... US$0.50 to US$20" is a cost control on a worker screen (views.md: no costs). | P2 | reported to lead |
| Q1-12 | Routines, 1440 light | Opens on the empty "Your routines" tab ("No routines yet") while "Could automate 2" holds the content. Status pill "proposed" in mono is jargon. | P3 | reported to lead |
| Q1-13 | First run (Set up again), 1440 light | Role card text clipped mid-phrase: "Pulls numbers from a . Full pack". The SharePoint chip carries a brown "Community server" tag that wraps inside the pill. | P2 | reported to B (adaa677ce7ff598bc) |
| Q1-14 | Sidebar, while stopped, 1440 light | The Resume button draws the same square stop icon as Stop. | P3 | reported to B |
| Q1-15 | Sidebar and Settings, no model key | "Live models" and "On, because a key is set" show when the engine has no key (the label follows the mock flag, not `key_present`). No effect for the owner, who has a key. | P3 | reported to B |
| Q1-16 | Needs you, with a task waiting | Every 2 seconds the screen re-asks six endpoints, including the slow ones (`/routines`, `/briefing`); calls pile up under load. | P2 | reported to lead |
| Q1-17 | check-copy at 390 | growth 64 over 60 words; your-data one paragraph over two lines; the retired routes genome, presence, week, git land on Growth sections with one paragraph over two lines. | P3 | reported (D for Growth) |
| Q1-18 | Your data, Delete everything, 1440 light | The confirm sentence is long and uses "how loud to speak and the counts of your cursor and apps". | P3 | reported to lead |

## What worked (seen, with a real click)

- Home: hero, task box, background tasks list (a typed task reached the agent service; with no model key it asks which way to do it: answer, web, files or code, screen), account menu with the name field and role, Change profile form, Set up again (role, one consent with Yes, Not now, Never, ready, Show my week).
- Needs you: Evidence opens; Approve and submit (real click, the item left, the badge fell 7 to 3); Keep mine; Watch first (the proposal moved to Routines, Your routines 1); Not now; Never.
- Routines: tabs, Could automate list.
- Your data: Forget this line with an inline Keep or Forget it (count 20 to 19); Delete everything asks first with a Keep button.
- Settings sheet, command palette (Cmd-K, results, Enter), Cmd-1 to Cmd-5, Cmd-comma, Cmd-slash (About this screen), Stop (red banner, Resume) and Resume.
- No horizontal scroll at 390, 1152 or 1440 on Home, Needs you, Routines, Growth, Your data, light and dark.
