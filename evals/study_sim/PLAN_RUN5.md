# PLAN, run 5 (EXPLORATORY): a stronger language-model participant, pre-registered before any run-5 model call

**Label used everywhere: "simulated participants (language model), not people". This run is exploratory.** It is separate from `PLAN.md` (run 4, the pre-registered study) and
never replaces or re-labels it. Nothing here touches the live `study` section.

**Status: written while run 4 is still running, before any run-5 model call.** The lead commits this file; its git timestamp must precede the first model call of the pilot. The
`GO5` file that unlocks the harness is created only after the lead replies GO. After GO this file changes only by dated entries in the amendment log. No tuning after any result.

## 1. Why this run exists

Run 4 (24 participants, the fast tier, `PLAN.md`) hit the floor: most post-tests ended at the 60-action cap with no calculation done, so the scores are almost all zero in both arms and
say nothing about the coach. The causes were in the participant, not the pipeline: the fast model types junk or placeholders into form fields, and the first calculator's wizard carries
step-1 values as hidden fields, so one bad value makes the final Calculate fail on a page whose faulty field is no longer visible, and the participant loops. Run 5 asks one narrow
question: **if the participant is a stronger model, does the study come off the floor, and then does the coach's effect on the later unassisted case show?** It cannot answer anything else.

## 2. What changes and what does not

**Changes (only this):** the participant's model call. Run 4 used the shared model port's fast-tier `check` call. Run 5 uses the port's **planner-tier `plan` call at the port's configured
planner effort** (the port's default is "low"; nothing is overridden), model id read from the environment by the port (`OPENAI_MODEL_PLANNER`), recorded in the `model` column.

**Options for the stronger participant, declared in advance (nothing else will be tried under this plan):**

| Option | Call | Effort | Status |
|---|---|---|---|
| P1 | planner tier, `plan` | the port's default for the planner, "low" | **the only option that will be run** |
| P2 | fast tier, `check` | raised to "low" | declared, not run |
| P3 | planner tier, `plan` | "medium" | declared, not run |

If the pilot of P1 fails its criterion (section 4), **we stop and say so**; P2 and P3 would need a new plan, written after seeing that failure, and are not covered by this one.

**Unchanged, exactly as in run 4:** the sandbox sites, the coach, the study-mode API, the extension, the households and case roles, the task script, the persona texts and their seeded assignment, the
overlay renderer, the follow, false-nudge and delay definitions, the cap of 60 actions per case, the 2 s pause per action, at most 4 actions per reply, the typed-value cleaning (Amendment 1), the one-more-look
after Save draft, the per-case contamination check with up to 3 attempts, the scoring (`analyze.score_post_test`), and the analysis code. **The code under test is run 4's frozen copy:** the harness reuses `evals/study_sim/frozen_run4/`
(a copy of `services/engine`, `services/agent`, `packages` as run 4 used them, git 4e12dd8c plus 93 uncommitted files, fingerprint `5630b3c99e9f734a`, and the three extension builds, fingerprints
`456cdba315422688`, `8aca835fb01cd573`, `c32fc1e85d21f4df`), and **refuses to start if any fingerprint differs**. So any change other tracks make to the coach, sites or extension after run 4 does not reach run 5.

## 3. Design

* **Pilot (3 participants, A/A arm only, coach silent in every block, discarded from every analysis).** Ids `p_pil01` to `p_pil03`, sequences S1, S2, S3, base case roles, personas matched to run 4's first A/A participants of the same sequences. Used only to decide
  whether the stronger participant is off the floor and what a participant costs.
* **Main (n up to 12): 8 coached (2 per sequence) and 4 A/A (1 per sequence), ids `p_ex01` to `p_ex12`,** same design and same case-role rule as run 4 (`within` parity picks base or swapped cases). Run order: the 8 coached participants first (two rounds over S1 to S4), then the 4 A/A, so that a
  budget stop loses the A/A control, not the headline, and every prefix of 4 or 8 coached participants is balanced over the sequences. If the pilot's cost allows only 8 participants, the main run is the 8 coached alone and says it has no A/A arm.
* **Why 8 + 4.** Exact counterbalancing needs the coached participants in multiples of 4 (one per sequence). Twelve coached and no A/A would have a little more power (interval excludes 0 in 22% of runs for a medium true effect, against 16% at n = 8, from the engine-analytics Monte Carlo) but no bias estimate, and
  the A/A arm is how a floor, a ceiling or a skill-difficulty bias is seen. We choose the control.
* Participants run 3 at a time in the same private worlds as run 4 (ports 7911 to 7933).

## 4. The feasibility pilot and its declared criterion (decided by code, not judgement)

`pilot-decide` reads the pilot's `participants.csv` and cost and writes `results_run5/pilot/PILOT_DECISION.json`; the main stage **refuses to start** unless it says `pass`. The criterion, fixed now:

1. all 3 pilot participants completed with no harness exclusion (6 unassisted post-tests exist), **and**
2. **at least half of the 6 pilot post-tests (at least 3) score above zero** on their skill (cliff: at least one calculator's cliff panel opened; reconcile: a saved draft with `discrepancy`), **and**
3. the pilot's measured cost per participant, times a safety factor of 1.25, lets the remaining budget pay for at least 8 participants (so `n_planned` = 12 if 12 are affordable, else 8, else stop).

If any part fails, the decision is "stop", the reasons are printed and kept, the pilot's facts (scores, action counts, cost) are reported as a pilot, and **there is no run 5 proper**. A pass is not evidence of anything about the coach; it only says the participant is off the floor.

## 5. Measures and analysis (same as run 4, `PLAN.md` sections 6 and 7)

Headline: unassisted skill score of the later matched case, coached skill minus uncoached skill, per participant, mean over the coached participants, 95% t interval (df = n - 1) with the exact sign-flip p beside it
(smallest possible p 0.0078 at n = 8), degenerate zero-width intervals flagged; per-skill descriptive table with bootstrap intervals; A/A arm (n = 4) descriptive only, with the relabelling check and the
difference in differences reported if it exists; effort as action counts, never seconds; nudges shown, followed, dismissed; pipeline checks, findings and the transcript-free statement as in run 4. Fixed wording: an interval that excludes zero is the only thing called clear; an interval that includes zero is "consistent with no effect and with a moderate one"; a negative difference is shown and named.
`analyze.py` is imported, never edited.

**Expected power, stated before any data** (engine-analytics Monte Carlo of exactly this analysis on the counterbalanced design, 500 replications, seed 20261107; made-up assumptions): at n = 8 coached the 95% interval excludes zero in
5.6% of runs under no effect (false positives), 9.8% for a small (10 point), 15.6% for a medium (21 point) and 48.6% for a large (39 point) true effect; sign-flip p < 0.05 in 0.6%, 2.0%, 5.8% and 22.0%. **A null from run 5 says almost nothing about the coach.** The design does not cancel spill-over of the coached gain to the other skill in block 2.

## 6. Budget: hard, in code

* **US$7 for the pilot and run 5 together.** The prices of the planner model must be supplied in `STUDY_SIM_PRICE_IN` and `STUDY_SIM_PRICE_OUT` (US$ per million tokens); **the harness refuses to start without them**, so the guard is real. They will be recorded in the report as an assumption.
* The spend is estimated from the port's own token usage and logged to `results_run5/cost_ledger.jsonl` call by call. **No new participant starts** if the estimate plus 1.5 times the mean cost of finished participants for every participant in flight would pass 95% of the cap; **a call that would pass 100% raises and ends the run** (`budget.py`). The main stage starts with the pilot's spend already counted.
* Run 4's spend and the earlier aborted runs are not part of this cap; the lead holds the overall cap.

## 7. Gates, outputs, exclusions, claims

* **Gates:** `evals/study_sim/GO5` must exist (created only after the lead commits this plan and replies GO); the frozen-pipeline fingerprints must match; prices must be set; the main stage needs a passing `PILOT_DECISION.json`.
* **Outputs** (all under `evals/study_sim/results_run5/`, each folder with `PROVENANCE.json`; never under `evals/study/`): `pilot/` (its own CSV, raw, checks, cost, decision), `main/` (CSV, raw incl. `engine_events.jsonl` per participant, checks, summary.json), `REPORT_RUN5.md`.
  Pilot data are in no analysis.
* **Exclusions:** harness errors only, as in `PLAN.md` section 10, never for scores, caps or refusals to follow the coach.
* **We will not claim:** that people learn; that a null shows no effect; that run 5 confirms or rescues run 4; anything about other models; significance beyond the exact sign-flip test; that the planner participant is a better model of a person. The report states that the run was designed after run 4 hit the floor,
  that the participant tier was changed to get off the floor, and that its pilot was used only to decide whether to proceed.
* **Known risk, declared:** the wizard trap (hidden carried fields, an error page without the faulty field) is unchanged by design; if the stronger participant still loops on it the pilot fails and we stop.

## 8. How it is run

```
UNDERSTUDY_MOCK=0 STUDY_SIM_PRICE_IN=<x> STUDY_SIM_PRICE_OUT=<y> uv run --package understudy-agent --env-file .env python -m evals.study_sim run5 --stage pilot --workers 3
uv run --package understudy-agent python -m evals.study_sim pilot-decide                 # prints and writes the declared decision
UNDERSTUDY_MOCK=0 STUDY_SIM_PRICE_IN=<x> STUDY_SIM_PRICE_OUT=<y> uv run --package understudy-agent --env-file .env python -m evals.study_sim run5 --stage main --workers 3
uv run --package understudy-agent python -m evals.study_sim analyze5                     # summary.json and REPORT_RUN5.md
```

## Amendment log

_Entries below are dated and never edit the sections above; where an entry contradicts a section above, the entry governs._

**Amendment 1 (2026-11-07, about 18:15 GMT, before any run-5 model call; at the lead's decision "C with P2").**
Costing before spending, from run 4's measured use: about **116 model calls, 119k input tokens and 12k output tokens per participant**. At the placeholder planner rates (US$5 in, US$30 out per million tokens) that is
US$0.96 per participant if the planner's reasoning added nothing, US$1.33 if it doubled the output and US$2.06 if it quadrupled it, so the 3-participant pilot would cost US$2.9 to 6.2 and leave room for 0 to 3 participants,
below the declared minimum of 8: the plan as written could only end in "stop: not affordable" after spending most of the cap. Therefore:
1. **P1 (planner tier, `plan` call) is withdrawn as unaffordable.** Sections 2 and 6 and the table in section 2 are superseded wherever they say P1, planner tier or `plan`.
2. **P2 is authorised, and only P2:** the same fast-tier `check` call as run 4, with the port's reasoning effort for the fast tier raised from its default ("none") to **"low"** (`OPENAI_EFFORT_FAST=low`, set by the harness itself before it
   creates the model port; the model id is read from the environment as always and recorded in the `model` column with the suffix `@effort-low`). **P3 stays unrun** and is not covered by this plan.
3. **Hard cap US$6 for the pilot and run 5 together** (US$1 stays in reserve), enforced in code (`pilot.BUDGET_USD`, `budget.py`): no new participant starts above 95% of the cap counting 1.5 times the mean cost of finished
   participants for each participant in flight, and a call that would pass 100% raises. **Prices are the fast-tier rates, US$0.75 in and US$4.50 out per million tokens, an assumption** supplied by the lead and not checked against a bill;
   the harness refuses to start without `STUDY_SIM_PRICE_IN` and `STUDY_SIM_PRICE_OUT`, and every report labels them as an assumption.
4. **Expected cost, stated before any call.** Run 4 cost about US$0.10 to 0.21 per participant at these rates (US$0.14 from the token means above). Raising the effort adds reasoning output tokens; if that multiplies the output tokens by 2 to 4 the cost per participant is about
   US$0.25 to 0.40, the pilot about US$0.75 to 1.2 and 12 participants about US$3 to 4.8, inside the cap; if it multiplies them by more than about 6 the pilot will say so and the declared affordability rule decides.
5. **Affordable n is recomputed from the pilot's measured cost** exactly as in section 4 criterion 3 with the new cap: projected cost per participant = pilot mean x 1.25; `n_planned` = 12 if the remaining US$6 minus the pilot's spend pays for 12, else 8, **else stop**.
   The minimum for the main stage is **8 coached participants** (the first 8 of the fixed order, so then no A/A arm and the report says so). **If fewer than 8 are affordable the run stops and says so; there is no silent shrinking.**
6. **Unchanged:** the pilot (3 A/A participants, discarded from every analysis), its criterion (all 3 complete without harness exclusion, and at least 3 of the 6 pilot post-tests above zero, and affordability), the stop if it fails, the frozen run-4 pipeline and its fingerprint gate,
   the design, order, ids, measures, analysis, power statement (n = 8: interval excludes zero 5.6% / 9.8% / 15.6% / 48.6% for none / small / medium / large; sign-flip p < 0.05: 0.6 / 2.0 / 5.8 / 22.0%), exclusions, claims and gates (`GO5` is created only after run 4 has finished and its analysis is written).
7. The run-5 report will say that the participant is the same model as run 4 with its reasoning effort raised to low, that this option was chosen after run 4 hit the floor and after the planner option was found unaffordable, and that the pilot was used only to decide whether to proceed.

**Amendment 2 (2026-11-07, about 18:12 GMT, before any run-5 model call; reporting only, requested by the lead).** The build machine is heavily loaded by other agents' tests (1-minute load average 107 to 131 on 12 CPUs), which affects wall-clock timings and the coach's timing-sensitive behaviour (3 s polls,
event flush, action pace, prompt delays). Run 5's harness records the load average when each participant starts and ends (columns `load1_start` and `load1_end` in `participants.csv`), the report states the load as a limitation, and heavy commands started by this agent go through `scripts/heavy.sh`.
Participants' worker processes do not (they are the thing being measured). Nothing else changes.
