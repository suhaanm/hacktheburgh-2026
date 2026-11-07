## Evaluations (`evals/`)

Draft fragment for the root README. Everything here is synthetic unless it says otherwise, and every number carries its n and an interval.

| Folder | What it is | Run |
|---|---|---|
| `redteam/` | 37 injected pages in 8 categories (hidden text, fake system banners, markdown-image exfiltration, tool-call mimicry, search results, PDF/OCR, alt text, multi-step), 4 more from the sandbox sites' own `?variant=injected` pages, and 31 benign pages (21 plain twins plus 10 hard negatives with benign hidden text). Every target is the invented domain `evil.example` or a sandbox endpoint. `attacks.json` is the catalog the red-team runner reads. | `uv run python evals/redteam/generate.py` (deterministic) |
| `cases/` | Answer keys: 20 households for the end-to-end runs and 200 for routing and site-disagreement analysis, each with the oracle's answer, what every sandbox calculator should show (including its deliberate quirk), the values to type, the expected cliff panel, an independent recomputation (the hand check) and routing labels. `skip_consequences.json` prices a skipped step in answers, not seconds. | `uv run python evals/cases/generate_cases.py`, then `uv run python evals/cases/skip_consequences.py` |
| `study/` | The live-study plan (committed before any data), protocol, fixed assignments, the analysis script and its tests. `results/` is empty until the first session. | `uv run python evals/study/analyze.py evals/study/results/participants.csv` |

Tests: `uv run pytest evals/tests packages/packs/tests -q`; extension: `cd extension && npm test`.

What the numbers mean, in one place:
- **Oracle.** The reference answer is a simplified internal rule set, illustrative, not law. Agreement between the oracle, the sandbox sites and the independent check says the code is consistent, not that it matches the UK system. The independent check shares the numeric parameters with the oracle and was written from the same documented rules.
- **Study.** n = 4 teammates, not benefits processors; synthetic households on local sandbox calculators; within-subject, counterbalanced, two skills by two orders. The headline is unassisted performance on a later matched case; assisted speed is reported separately and never combined with it. With four people the exact sign-flip p cannot go below 0.125, so the report gives per-person differences and a t interval and claims no significance. See `study/ANALYSIS_PLAN.md` for what is not claimed.
- **Red team.** Attack success rate and task success are measured on static pages and the sandbox variants with each defence layer switched off in turn; the false-pause rate is measured on all clean pages and, separately, on the hard negatives.

Limitations to add to the register (id, severity):
- `study-n4` (high): four teammates, one session each; intervals will be wide and include zero.
- `study-not-target-workers` (high): teammates are not benefits processors; the facilitator is the builder and cannot be blind.
- `oracle-simplified` (high): the benefits oracle is a simplified internal rule set, not law and not PolicyEngine UK.
- `sandbox-only` (medium): all agent and capture evidence comes from three local sandbox calculators and one case-note page.
- `redteam-synthetic-static` (medium): attack pages are authored by us, static, and cover the categories we thought of; a low attack success rate is not a security guarantee.
- `extension-one-browser` (medium): the capture extension is verified on one Chromium build (158) with Playwright and jsdom; Chrome stable, Edge and Safari were not tried.
- `rect-calibration-narrow` (medium): the overlay ring was measured at under one point of error on one Retina display in headed Chromium at 100% page zoom only. Not verified at other zooms, with docked DevTools, on a second display, or in cross-origin frames (those answer in frame coordinates). The extension now also reports viewport, outer and screen geometry so the desktop app can work out zoom itself.
- `health-field-not-captured` (low): the calculators' "limited capability" question matches the sensitive list and is deliberately never captured or recorded, so ENTER_HOUSEHOLD time on that field is missing and a recorded routine must take it from the household.
- `thin-pack-zones-best-effort` (low): the data-analyst and programmer packs' zone selectors for real tools are starting points, not tested against live sites.
- `task-markers-sandbox-only` (low): task_start, progress and task_end are inferred from the sandbox pages' structure (first calculator page, result page, saved note); they fit those pages only, and the thin packs declare none.
- `skip-consequence-policies` (low): the answer-error numbers for skipped steps depend on the stated policies (a random single calculator for reconcile, documented nudges for the cliff panel) and on the planted quirks.
- `zones-heuristic` (low): meta.zone comes from CSS selectors; a redesigned page falls back to generic zones until the selectors are updated.
