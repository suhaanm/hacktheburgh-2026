# Study protocol: one teammate, about 22 minutes

For the owner to run with four teammates (P1 to P4), one at a time. The plan is in `ANALYSIS_PLAN.md`, committed before the first session. Follow this script as written; note every deviation in the `notes` column. Do not help during a block, in either condition.

## Before anyone arrives (once, 10 minutes)

1. Commit `ANALYSIS_PLAN.md`, `protocol.md`, `assignments.json` and `analyze.py` **before the first session**. `results/` must be empty.
2. Pilot the whole script once on yourself or a non-participant. A pilot is never one of P1 to P4 and is not analysed.
3. Start the services with the sandbox sites on 7801 to 7803 (`uv run python -m understudy_agent.sandbox_sites`), the engine and the desktop coach. Run a quick check that `http://127.0.0.1:7801/step/1`, `7802/` and `7803/` load.
4. **Study mode (dependency).** The coach must be switchable per skill: coaching on for one named skill (`check-the-cliff` or `reconcile-before-noting`) at help level L1, everything else off, and **off entirely in post-tests**. It must log `coach_shown`, `coach_followed`, `coach_dismissed` per block. If this switch does not exist by the first session, the fallback is a printed prompt card with the L1 text of that skill from `packages/packs/benefits-processor/curriculum.yaml`, shown by you when the participant reaches the relevant step. That tests the prompts, not the system: record it as a deviation on every row and say so in the report.
5. Print the participant's row of `assignments.json`: which skill and condition in each block, and the practice and post cases (household ids and case references).
6. Have a stopwatch, the consent text below, and the three rating questions ready.

## Screening and consent (2 minutes)

Ask: "Have you ever processed benefits claims or worked with benefit calculators as a job?" If yes, thank them and stop: they are excluded (plan section 7). Otherwise read:

> "I'm testing a coaching tool, not you. You will check two households on two benefit calculators, write a short case note, and I'll time each part. The households are made up and the calculators are local test sites. Nothing you do is recorded except the clicks and results on those pages, your timings and your ratings, and none of it carries your name. I can't help during a case. You can stop at any time and your data will be deleted."

Get a yes. Assign the next unused sequence (S1 to S4 in order of arrival) and write it down.

## What the participant is told about the task (1 minute)

> "For each household you'll use GovCalc and Quick Estimator. Enter the household in each, then open the case note page, enter the case reference and the two results, choose how the calculators compare, and press Save draft. Never press Submit to claimant record. If I say stop, stop."

Give them the household details on paper (age, earnings, rent, savings and so on, as in `households_200.json` for the case) and the case reference. Nothing else is explained: the participant is not told what "cliff" or "reconcile" mean.

## Each block (about 9 minutes, twice)

Block structure, repeated for block 1 and block 2 with the skill, condition and cases in the assignment row.

1. **Reset** the sandbox state: `curl -s -X POST http://127.0.0.1:7801/__reset` (it is shared by all three sites). Open a fresh browser window with only the extension's capture on if you want the trace; coaching state set as below.
2. **Practice case** (cap **5 minutes**). Condition `coached`: coaching on for this block's skill only. Condition `uncoached`: coaching off. Start the stopwatch when they open the first calculator; stop when they press Save draft or at the cap. Say nothing except "stop" at the cap. Record `practice_seconds` and whether it was capped.
3. **Save the evidence** for the practice case is not scored; skip it. Reset again.
4. **Coaching off entirely** (both conditions). Tell them: "This one is on your own."
5. **Post-test case** (cap **4 minutes**), same skill, matched case. Stopwatch as above. At the end, **immediately** save the state: `curl -s http://127.0.0.1:7801/__state > evals/study/results/raw/P<n>-block<k>-post.json`.
6. **Score from the state, not from watching.** Run `uv run python evals/study/analyze.py score <cliff|reconcile> evals/study/results/raw/P<n>-block<k>-post.json`; it prints `post_checks_done` and `post_checks_possible`.
   - skill `cliff`: the number of calculators (a, b) whose cliff panel was opened during the post-test (`cliff_opens` in the state; it was reset before the case). Possible = 2.
   - skill `reconcile`: 1 if a saved note has `reconciliation` equal to `discrepancy`, else 0. Possible = 1. The form's default is "agree", so doing nothing scores 0.
   - If the participant never saved a draft, the reconcile score is 0.
7. Write the row (see Data entry). Take 30 seconds before the next block.

If a site crashes or answers 503 during a block, note it, reset, and repeat that block on the spare matched case only if you can do so within the session; otherwise the participant is excluded (plan section 7).

## After both blocks (2 minutes)

Ask three questions, answer 1 (no) to 5 (yes), and write them down:
1. "The help came at the moment I needed it." (coached blocks only)
2. "The help interrupted me." (coached blocks only)
3. "I would want something like this at work."

Then: "What was the most confusing moment?" Write one line. Keep it local; it is not analysed. Thank them. Do not tell them their scores or discuss the hypotheses until all four sessions are done.

## Timing budget

| Part | Minutes |
|---|---|
| Screening, consent, task briefing | 3 |
| Block 1: practice (cap 5) + post-test (cap 4) + reset | up to 10 |
| Block 2: practice (cap 5) + post-test (cap 4) + reset | up to 10 |
| Ratings and debrief | 2 |
| **Total** | **about 22 to 25** |

If the pilot shows the budget is far too long, cut the caps in the pilot and record the new caps as an amendment (dated, before P1).

## Data entry

One row per participant and block in `evals/study/results/participants.csv`, columns exactly as in `ANALYSIS_PLAN.md` section 11. `exclusion` is empty unless the participant is excluded; then give the reason on **every** row of that participant. `post_checks_possible` is 2 for `cliff` and 1 for `reconcile`. Use `yes` or `no` for the capped columns. Enter nudge counts from the coach log, per block (0 in uncoached blocks).

When all four sessions are done: `uv run python evals/study/analyze.py evals/study/results/participants.csv`. It checks the design against `assignments.json`, prints the headline (unassisted) and the assisted speed separately, and writes `results/summary.json`. Do not edit the analysis after seeing the data; if something must change, add a dated entry to the amendment log in the plan.

## Stop rules

Stop a session if the participant is distressed or asks to stop, if the coach does anything unsafe or unexpected (for example, tries to press Submit), or if a real account or real personal data appears on screen. Use the kill switch if the agent is running; this study does not run the agent at all.
