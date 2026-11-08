# QA-ADMIN defect log (Track Q2)

Read as an admin of the 32-person firm, 8 Nov 2026 about 02:45 to 03:40 GMT. A private stack (own ports, own data folder, seeded with `demo seed` and `seed-firm`, mock off, no keys, a private agent service), driven with playwright at 1440 by 900, 1152 by 735 and 390 by 844, light and dark: every admin page read from the screenshot and from the page text, with every disclosure opened, a person opened, the palette, the account menu, the More sheet, the 390 bottom bar and its sheet, the keyboard path (Tab order, Ctrl-1 to Ctrl-8, Ctrl-K, Enter, Esc) and a worker typing admin addresses. Pictures are not committed.

Status: fixed (by whom, commit), reported (to whom), won't fix (why). Owners: D insight and firm screens, B shell and nav, R engine firm data, H HRT and Evidence blocks, Q2 this track.

What agrees: 32 people, 12 benefits processors, 10 data analysts, 10 programmers, 3 roles, 31 with enough data, on Firm, Brief, People, Risk and Roles; no blank page; no NaN, undefined, null or raw ids on the nine main pages; no sideways page scroll at any size; no banned word on any screen (check-words); the Admin gate sentence on every admin address typed as a worker.

| id | page | size and theme | what | status |
|---|---|---|---|---|
| A1 | Forecasts, Roles | all | "Expect juniors in Data analyst to finish 38 points fewer..." (capital D, no plural, no comparator); "the widest gap of 3" | fixed by D (verified: "Junior data analysts ... than experts, the widest gap across 3 roles") |
| A2 | Automation headline, Forecasts chart | all | Habit names cut mid-phrase ("Enter the household into three...") | fixed by D (full names, two-line chart labels) |
| A3 | Forecasts, How reliable are these forecasts? | all | "generated person", "Generated people from our own generator", "four generated personas", reviewer charts for the coach's stuck forecast under a firm forecast | fixed by D (one plain sentence and a link to Evidence; verified) |
| A4 | Firm | all | "24 other candidates were left out"; 5 things need a look vs Show all 7 | fixed by D (verified) |
| A5 | Risk, Firm | all | "injected page" jargon; "2 more things need a look" | fixed by D (verified) |
| A6 | Onboarding | all | Data analyst missing from the first view without a word; "design target ... A line to aim at" | fixed by D (verified: "Not drawn: Data analyst, with fewer than 5 people far enough in") |
| A7 | People | all | "numbers and enums only"; the 5-people rule said twice | fixed by D (verified) |
| A8 | People vs Roles | all | Role cards said Programmer 92% and Benefits 88% finished without help, Roles said experts 96% and juniors 71% | fixed by D (People names its measure: "Everyone here, finished without help") |
| A9 | People, an opened person | all | "-2.6 s (-5.6 to 3.5) shorter than the expert's median" | fixed by D (verified: "against the expert's median, no clear difference") |
| A10 | People table | 390 | Name column 50 px: "Arjun / Bhatt / over / a / year" | fixed by D (a card under 480 px; verified) |
| A11 | Firm, Show all 7 | all | "about 15 seconds" over "16.9 seconds" | fixed by D |
| A12 | Brief, Risk | 390 | "n / = 3 approvals" split; "2 in 30 / days" wrapped | fixed by D |
| A13 | More (sidebar row) | 1440 by 900 | The More sheet opened at the top of the window, not beside its row | fixed by B (verified: opens at the row) |
| A14 | Evidence, Agent runs | 1440 | Headline printed `live.false_claims_by_condition`; the block note printed `*_by_condition` | headline fixed (1f8d0c4); note fixed in the commit after this log |
| A15 | Evidence, deficits chart | 1440 | Row label clipped at the left edge ("ads the result again...") | fixed (f0ea7e8, wraps to two lines, tested) |
| A16 | Evidence | all | The two computer-use rounds were three sentences in the Limits register | fixed (1f8d0c4): new block after Agent runs, headline from the newest round, a two-row table (Round 1 OpenAI, Round 2 Gemini), gate builds, seeds and stops behind a disclosure; tested on the fixture and on bad data; 390 checked |
| A17 | Models and cost | all, no keys | "model id not resolved" nine times, 130 words above the fold (budget 120) | fixed (877ec62; D made the same two edits) |
| A18 | Account menu | all | Placeholder "Your name" when no name is set | fixed by B ("Add your name") |
| A19 | Forecasts | all | Reviewer calibration charts for the coach's stuck forecast under "How reliable are these forecasts?", 6,500 px when opened | fixed by D with A3 |
| A20 | Evidence map | 1440 | The Model benchmark row says "0 people" | reported to the lead (a count of people that is zero; the unit should be "models" or the row should say not applicable) |
| A21 | Background runs | all | Raw run id in the card line ("Foreground · r_a01 · started ...") and in the started toast | fixed (3ca8458) |
| A22 | Palette | Admin | "Delete my data" (a worker screen) offered to an admin; the no-match hint named Growth | fixed by B (in main, e1799b8) |
| A23 | Forecasts | 1152, 1440 | Top rule full width, cards 720 px | fixed by D |
| A24 | Risk | 390 | After D's first fix the long label squeezed the figures to one character a line and scrolled the page sideways | fixed by D (e469dab, label above value under 480 px; verified no scroll) |
| A25 | Forecasts chart | 390 | Two-line labels overlapped the next row and hid "18.5 h" and "5.1 h" | fixed by D (f958f2a: a wrapped label gets a taller row) |
| A26 | More sheet | 1440 | The chevron of the page's disclosure ("24 other findings...") shows through the sheet at x 253, y 428 | reported to B |
| A27 | Evidence | all | The deficits block kicker still says "Does the genome find the deficit we planted?" (an old screen name) | reported to H |

Commands run on this tree (private stack, no model calls, no desktop input):
- `view-audit.mjs --only admin`: 12 PASS, 0 FAIL.
- `check-words.mjs`: OK, 44 views, no banned word.
- `check-copy.mjs --view=admin --narrow`: 29 of 30 reads pass; the one FAIL (Models at 1440, 130 words against 120) was A17, fixed.
- `check-clicks.mjs`: A1, A2, A3 PASS; J7 FAIL is a worker job (no routine to Run now on the empty stack), not an admin route.
- Dashboard `tsc --noEmit` clean; `vitest run` 106 files, 1481 tests pass.

Lead, 8 Nov ~04:05: A20 fixed (a section measured on no people prints 'not applicable', evidence.ts), A27 fixed (the kicker names My steps), A26 fixed (the sidebar layer sits above the page: shell.css z-index var(--z-panel), so the More sheet is never drawn under a page control).
