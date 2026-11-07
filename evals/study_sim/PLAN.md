# PLAN: simulated study with language-model participants (pre-registration)

**Label used everywhere: "simulated participants (language model), not people".**

**Status: written before any model-driven participant has run.** The commit that adds this file must come before the first model-driven run; its git
timestamp is the proof. Until the lead replies GO the harness has been run only on FAKE participants (scripted, no model, see section 13); the `run`
command refuses to start without a `GO` file. After GO this file changes only by dated entries in the amendment log at the bottom. No prompt, persona,
case, cap, pace, scoring rule or analysis is tuned after any result, ever: if the harness is broken it is fixed on FAKE participants only and the fix is logged.

## 1. What this is for, and what it cannot show

The owner cannot run the live study with four teammates (`evals/study/ANALYSIS_PLAN.md`), so this simulated study runs in its place **as a test, never as a
substitute**. It has three honest purposes:

1. **An end-to-end test of the real pipeline under realistic use:** real extension -> real engine -> real coach brain -> a prompt drawn on the page ->
   a participant reacts -> `POST /coach/feedback` -> score read from the sandbox state exactly as `analyze.py score` does.
2. **Evidence on whether the coach's prompts change the behaviour of a language-model novice on a later unassisted case.** That is a statement about a
   model reading our prompts, in a sandbox we built. It is not evidence that people learn.
3. **An A/A control** (a sham arm in which the coach is silent in every block) that estimates how biased the measurement chain is and what its
   false-positive rate looks like on these scores.

It **cannot** show: that people learn from the coach; that novices become experts; anything about real benefits work, real calculators or real claimants;
any effect on human speed; or that a model's "memory" (a self-written note in a prompt) is memory. It never touches the `study` section of the report: that
stays `not_run` until people do the live study. Every table, chart and sentence it produces carries the label above.

## 2. Design

**Same design as the live study, more people.** The sequences S1 to S4 (counterbalanced: two skills x two orders) and the two matched household pairs are
exactly those of `evals/study/assignments.json` (read-only; the file is not touched):

| Sequence | Block 1 (skill, practice) | Block 2 (skill, practice) |
|---|---|---|
| S1 | cliff, coached | reconcile, uncoached |
| S2 | reconcile, coached | cliff, uncoached |
| S3 | cliff, uncoached | reconcile, coached |
| S4 | reconcile, uncoached | cliff, coached |

* **Coached arm: N = 16 silicon participants, 4 per sequence** (`p_sim01` to `p_sim24`, ids assigned in run order, section 5).
* **A/A sham arm: 8 silicon participants, 2 per sequence**, the same sequences, cases and personas, but the coach is silent in every block
  (study mode `off` in every practice case, `post_test` in every post-test). The sequence labels "coached"/"uncoached" are *nominal* for these participants
  and are used only so that the headline analysis can be run on them unchanged. Their true effect is zero by construction.
* Each block is the protocol's block: **reset** the sandbox (`POST /__reset`); set the study mode through the engine's own API (`POST /study/mode`: `train`
  with `skill_on` = the block's skill id and level `L1` for a coached practice, `off` for an uncoached practice, `post_test` for the unassisted post-test);
  run the **practice case**; the participant writes its **note**; reset again; **post-test case** (same skill, matched household, no coach); save `/__state`
  to `results/raw/<pid>-block<k>-post.json`; score with `analyze.score_post_test`. Calculators GovCalc (a) and Quick Estimator (b) only; the case note is
  saved as a draft only.
* **Case roles.** In each (arm, sequence) cell the practice and post-test case of each matched pair are swapped for half the participants (cell members with
  an odd `within` index), as the live plan does between participants, so a case effect is spread, not removed.
* **The participant is told only the protocol's task script** (verbatim, plus the consent sentences about a "coaching tool"), the bookmarks (the three
  local URLs), the household on paper (age, earnings, rent, savings and so on, from `households_200.json`; no archetype, no notes, no oracle values) and
  the case reference. It is **not** told what "cliff" or "reconcile" mean.

## 3. The participant (a language model)

* Reached through `understudy_agent.models.get_model_port()` on the **fast tier**, `ModelPort.check(prompt, schema)` with a strict JSON schema. The model id
  is read from the environment by the port (`OPENAI_MODEL_FAST`); nothing is hard-coded here, and the id is recorded in the `model` column.
* It sees what a person would see: the page text, a numbered list of the visible controls with their labels and current values (no attributes, zones or
  ids), the tab list, the household card, the task script, the bookmarks, what it has done so far, how many actions are left, and the coach overlay when
  one is up (the note text, and a flag on the control the ring is drawn around).
* **Actions are typed** and run through Playwright (trusted CDP events, so the real extension captures them): `click`, `fill`, `select`, `goto`, `wait`,
  plus `new_tab`, `switch_tab` (a browser has tabs; a person comparing two calculators would use them), `dismiss_coach` and `finish`. At most 4 actions per
  model reply, executed in order; the rest are dropped if the page changes or a coach note appears. `goto` only to the world's own three origins.
* **Step budget: 60 actions per case** (a stand-in for the 5 and 4 minute caps), and **a 2 s pause after every action**, plus a 900 s wall-clock hang guard
  (reported as `capped`). *Deviation from the first brief (40 actions), accepted by the lead and decided before data:* the shortest honest path through two
  calculators and the note, with only the required fields, is 21 actions, about 33 with both cliff checks and tab switches, so 40 would cap many honest
  cases and make the reconcile score unreadable. The 2 s pace makes a case last tens of seconds rather than seconds, so that the coach (polling every 3 s,
  needing two consecutive signals, fed by an extension that batches every 2 s) can act before a fast model has finished the note page; its measured
  latency from the first case-note-page action to a prompt in the fake runs was 8 s (section 13), which a person typing five fields would also exceed.
* **Submit.** The case ends when the participant presses Save draft and the saved page appears (the stopwatch stops), but that page shows the forbidden
  button, so the participant gets one more look. If it tries to press "Submit to claimant record" (before or after saving) the click is **not sent**; a
  protocol violation is recorded (`notes`, `protocol_violation`) and the case stops as it stands. The sandbox is local and synthetic, but the violation
  counts and is reported. This extra look is not an action and is not counted against the cap.
* **Personas** (all neutral about benefits knowledge; every persona is told it has no prior experience): carefulness low/medium/high, tendency to read
  on-page prompts low/high, verbosity of its own notes terse/normal/wordy. Assigned by a fixed seed (20261107) and balanced across sequences: each sequence
  cell of four has carefulness {low, medium, medium, high}, prompt-reading {low, low, high, high} and verbosity {terse, normal, normal, wordy}, each
  shuffled with the seed. The A/A participants repeat the personas of the first two coached participants of the same sequence (matched). The persona texts
  are in `participant.py` and are frozen by this plan.
* **Learning proxy.** After each practice case the participant writes a note to itself, at most 280 characters, "what I will do next time", from a digest of
  what it did, the coach notes it saw and what it did about them (the same call in both conditions, for symmetry). The note is shown to it at the
  post-test of the **same skill block only**; it is never carried into the other block (every case otherwise starts from a fresh model context). So any
  difference between conditions can only come from what happened in practice, which differs by what the coach showed. The note is kept in `actions.jsonl`
  (it is the one piece of model text we keep).
* Model calls are cached by prompt hash (the participant code is in every prompt, so two participants never share a hash); a retried case replays its
  answers.

## 4. The coach path (real) and the renderer (simulated)

* The harness polls the engine's `GET /coach/next?person=p_simNN` **every 3 s, steady pace, committing polls** exactly as the desktop app would, in a
  background task while the participant acts. When `action` is `annotate`, `nudge` or `takeover_offer` the overlay is drawn: a message line plus, for
  `annotate`, an orange ring around the element carrying `data-understudy-zone=<target.zone>` if the active tab has one. The ring follows the active tab (the
  participant may have to switch to a calculator tab to see the cliff ring); the reconcile target zone `results_tabs` has no page element, so that prompt is
  a message line only. Both facts are reported as pipeline findings (section 8).
* **Following** (the participant "does the missed step"), judged by code from the participant's executed actions: for a cliff prompt, pressing "Check cliff
  edges" on any calculator; for a reconcile prompt, choosing a value in the case note's reconciliation dropdown or switching between browser tabs (the
  engine's own RECONCILE cog is a tab switch). On follow the harness posts `POST /coach/feedback {outcome: followed}`. On `dismiss_coach` it posts
  `dismissed`. A note still up at the end of the case, or replaced by a newer one, is recorded as `ignored` and posted as `dismissed` (as the desktop would
  when it drops a note). The CSV `nudges_dismissed` is explicit dismissals plus ignored; the split is in extra columns.
* **False nudge:** a prompt for a step the participant had already done more than 6 s before the prompt arrived (cliff: the n-th distinct calculator's panel
  already opened; reconcile: already chose a value or switched tabs). Done within 6 s of the prompt is a **lagging prompt** (event pipeline latency), counted
  separately.
* **Delay** = seconds from the participant's first action on the case note page to the prompt being shown.

## 5. Private worlds, process model and determinism of assignment

The first design used the shared sandbox sites on 7801 to 7803 under `sandbox_lock`. On its first fake run another actor drove those sites without taking
the lock (cliff panels opened on sites a, b and c within one second while my scripted fake never pressed the button), which would silently corrupt
post-test scores, and a serial run would take 3 to 4 hours. So, as the lead directed, **each participant worker has a private world**:

| Worker | Sandbox ports a / b / c | Sandbox process | Extension build | Engine | Browser |
|---|---|---|---|---|---|
| ssim0 | 7911 / 7912 / 7913 | one `SandboxCluster` process | `node scripts/build.mjs --out dist-ssim0` with `SANDBOX_PORT_A/B/C` set | one per participant, ephemeral port, temp `UNDERSTUDY_HOME` and `UNDERSTUDY_DATA_DIR`, copy of `data/synthetic` | one Chromium context per case (new headless, `channel: chromium`), fresh profile |
| ssim1 | 7921 / 7922 / 7923 | same | `dist-ssim1` | same | same |
| ssim2 | 7931 / 7932 / 7933 | same | `dist-ssim2` | same | same |

* **3 parallel workers** (fallback: `--shared`, one worker on 7801 to 7803 under `sandbox_lock("study-sim")`, per case).
* **Isolation.** Never the engine on :7700, the agent on :7710 or the dashboard. The engine is started with `AGENT_PORT=1` (a dead port) and **no model
  key**, so it can never reach the owner's agent or a model; `UNDERSTUDY_MOCK=1` is set for the engine process only (it selects offline data loading; the
  coach, study mode and event store do not use a model). The kill-flag check writes the `KILL` file in the participant's own data dir; it never calls
  `POST /kill`. Extension builds live in `extension/dist-ssim*` and are deleted at the end.
* **Determinism of assignment.** The run order, and for every position the arm, sequence, case roles and persona, are a pure function of the seed and are
  fixed in `design.py` (tested): positions 1 to 4 coached S1..S4, 5 to 8 A/A S1..S4, 9 to 12 coached, 13 to 16 A/A, 17 to 20 coached, 21 to 24 coached.
  Workers take positions from one queue in that order, whichever worker is free; **which worker runs a participant is dynamic, is recorded in the `worker`
  column and is not a design factor**. A budget stop therefore leaves a prefix that is balanced to within one participant per sequence and arm.
* **Belt and braces.** In every case the participant's own action counts are compared with `/__state` (calculations, cliff panels opened, notes saved,
  submissions, exfil hits, sites never visited): anything the participant cannot have caused marks the case contaminated, and it is restarted (up to 3
  attempts, waiting out the coach's 120 s cooldown if the coach had spoken; the model's answers are cached) rather than scored.

## 6. Measures

* **Headline (unassisted).** Skill score of the post-test in [0, 1] read from the sandbox state exactly as `analyze.score_post_test` does (cliff: panels
  opened on a and b, out of 2; reconcile: 1 if a saved note has reconciliation `discrepancy`, else 0). Per participant d = score(nominally coached skill) minus
  score(nominally uncoached skill). The headline is the mean of d over the **16 coached-arm participants**.
* **Assisted effort, reported separately and never combined with the headline: ACTION COUNTS, not seconds** (model latency is not human speed): actions in
  the practice case, by actual condition; actions in the post-test, by nominal condition. In `participants.csv` the human columns `practice_seconds` and
  `post_seconds` hold these action counts (column `effort_unit` = `actions`; wall-clock seconds are in `practice_wall_s`, `post_wall_s`) so that `analyze.py`
  runs unmodified; `summary.json` relabels them.
* **Nudges** shown, followed, dismissed (ignored split out), false and lagging prompts, rings drawn: counts, from the participant's coached blocks.
* **Not measured:** ratings (a model's "1 to 5" is not a rating of anything) and speed in seconds.
* **CSV:** `results/participants.csv`, one row per participant and block, the human columns exactly as `analyze.COLUMNS` plus `arm, persona, model, effort_unit,
  actual_condition, case_variant, practice_actions, post_actions, practice_wall_s, post_wall_s, practice_end, post_end, protocol_violation, nudges_ignored,
  false_nudges, lag_prompts, rings_drawn, worker`.

## 7. Analysis (fixed now)

Reuses `evals/study/analyze.py` (imported, never edited) on the CSV: `analyze.load`, `analyse` (design check against an in-memory copy of the assignments
keyed by the silicon ids; `assignments.json` untouched), `paired`, `skill_score`, `t_interval`, `sign_flip_p`, `score_post_test`.

1. **Design check** per arm; problems are listed, not silently fixed.
2. **Headline:** the 16 differences, their mean, the 95% t interval (df = 15) and the **exact two-sided sign-flip p** over all 2^16 sign patterns (smallest
   possible 3.1e-05). The t interval has a degenerate case (all differences identical gives a zero-width interval); the report always prints the sign-flip p
   beside it and flags a zero-width interval. Wording fixed in advance: if the interval excludes 0 *and* no difference is negative, "coached skills scored
   higher than uncoached ones for these model participants; this is instruction following plus a self-written note in a sandbox we built"; if the interval
   includes 0, "consistent with no effect and with a moderate one; 16 participants cannot tell"; if the interval is below 0 or any difference is negative,
   it is shown and named. A result counts as clear only if the interval excludes zero.
3. **Per skill** (cliff, reconcile): mean post-test score where that skill was coached vs where it was not (different participants, same skill), difference
   with a 95% percentile bootstrap interval (10000 resamples, seed 20261107). Descriptive, no p-value.
4. **A/A:** the same headline analysis on the 8 sham participants (mean difference with t interval df = 7, exact sign-flip p over 2^8 patterns), the
   **coached-arm mean difference minus the A/A mean difference** with a percentile bootstrap interval (secondary), and the A/A false-positive check: every
   balanced relabelling (C(8,4) = 70) of which A/A participants are "nominally cliff-coached", with the share whose sign-flip p is below 0.05 and the share
   whose t interval excludes 0 (nominal 0.05; exact, no sampling, conditional on these scores).
5. **Effort and nudges:** descriptive counts and means by condition, never combined with the headline.
6. No pooling across blocks, no covariates, no model, no multiplicity adjustment (one primary comparison). The persona and worker are not analysed (a
   descriptive table of scores by worker is in the checks as a sanity read only).

**Expected power, stated before any data** (engine-analytics Monte Carlo of exactly this analysis on the exactly counterbalanced design,
`understudy_engine.study_power.evaluate_study_power(fast=True)`, 500 replications, seed 20261107; assumptions are made-up: how much people differ, effect size,
carry-over; it shows what the design could detect, not that an effect exists). Chance the 95% t interval excludes 0, and chance that sign-flip p < 0.05:

| n | true effect none (false positive) | small, 10 points | medium, 21 points | large, 39 points |
|---|---|---|---|---|
| 16 (CI excludes 0) | 5.6% | 11.6% | 28.6% | 75.6% |
| 16 (sign-flip p < 0.05) | 2.4% | 5.6% | 18.2% | 66.4% |
| 24 (CI excludes 0) | 4.0% | 12.4% | 40.8% | 90.2% |
| 24 (sign-flip p < 0.05) | 2.4% | 9.4% | 33.0% | 86.8% |

**So a null or small result from 16 silicon participants does NOT show that the coach has no effect.** The simulation also assumes the design cancels generic
carry-over and fatigue; it does not cancel **spill-over of the coached gain to the other skill in block 2**, which dilutes the contrast (limitation 7).

## 8. Pipeline checks (reported with counts in REPORT.md and `summary.json`)

1. **Events landed** per participant (counts by type and zone) and **schema-valid** (Draft 2020-12, `packages/schema/event.schema.json`, against the files the
   engine stored).
2. **Coach decisions issued** and how many were followed, dismissed or ignored; decision kinds; the stuck-signal source (hazard vs heuristic).
3. **Ring target correct:** the decision's zone equals the zone of the missing step's control (cliff: `cliff_button`; reconcile: `results_tabs`); whether a
   ring could actually be drawn (element present on the active page on arrival, at some point, never); delay from the missed step to the prompt.
4. **False nudges** (prompts for a step already done) and lagging prompts.
5. **Study-mode enforcement: zero nudges in any post-test block, in any uncoached or A/A practice block, and none for the non-trained skill** in a coached block.
   Checked three ways: every 3 s poll is tagged with the mode the harness set and any non-silent answer outside the allowed set is a violation; the engine's
   stored `coach_shown` events are compared with the participant's trained skill; and `coach_shown` events are counted by block and skill. **Any violation is
   a bug: the lead is told immediately.**
6. **Errors:** engine tracebacks, error lines and non-2xx answers to `POST /events`; extension web errors; coach poll errors; harness tracebacks; contaminated
   attempts and exclusions.
7. **Consent and kill flag:** with the consent toggle off the extension must send nothing (probed before capture is switched on and again after it is switched
   off); the kill flag is written in the participant's own data dir, and the engine's report of it and the coach's behaviour under it are recorded.

## 9. Budget and stop rules

* **Cap US$8.** Token counts come from the model port's own usage statistics; prices come from `STUDY_SIM_PRICE_IN` and `STUDY_SIM_PRICE_OUT` (US$ per million
  tokens) if set, otherwise conservative defaults (2.50 and 15.00) that make the estimate an upper bound for a cheaper model; the report says which. Every call
  is logged to `results/cost_ledger.jsonl` as it happens (thread-safe). Cache hits cost nothing and are counted.
* **Stop rules.** No new participant starts when the estimate plus 1.5 x the mean cost of finished participants for every participant in flight would pass 95%
  of the cap; a call that would pass 100% raises and ends the run. A participant cut off mid-way is excluded and listed (budget stop), never half-analysed.
  The report says plainly how many participants ran. Because the run order is balanced, a stop leaves a balanced prefix.
* **Harness failure.** If fewer than 8 coached-arm participants survive, the section's status is `harness_failure` and it is reported as such, with no
  headline claim. A study-mode violation is reported immediately and the run is stopped if the lead says so.

## 10. Exclusions (harness error only, decided before looking at any score)

A participant is excluded **entirely** (both blocks) only for a harness error: the model provider failing, a site crash or 503, the engine or extension failing,
an unrecoverable contaminated case after 3 attempts, a budget stop mid-participant. Never for a score, an action count, a refusal to follow the coach, a cap hit
or a protocol violation (a submit attempt stops its case and is scored as it stands). Every exclusion is listed with its reason; excluded participants reduce n
and every table prints the n it actually has.

## 11. What we will NOT claim

That people learn from the coach, or would; that the coach works on real benefits work; that novices become experts; that a model's note is memory or that
instruction following is retention; anything about speed in seconds; anything about other models; statistical significance beyond what the exact sign-flip
test gives (and we flag a clear result only when the interval excludes zero); that the simulated study validates the product; that a null shows the coach
has no effect.

## 12. Limitations (also in `summary.json.limitations`)

1. The participants are language models, not people. 2. Their only "memory" is a 280-character note they wrote themselves; each case starts from a fresh model
context. 3. A model told to "check cliff edges" can just do it: instruction following, not retention. 4. Coach prompts, sandbox, households, scoring and
personas were all written by us. 5. Power is low at n = 16 (section 7). 6. The counterbalanced design cancels generic carry-over and a fixed block-2 shift,
not spill-over of the coached gain to the other skill; and because blocks start from a fresh context, order and fatigue effects are absent by construction.
7. Timing is not human (fixed 2 s pause, model latency varies): effort is action counts and the coach latency is a property of the pipeline. 8. The overlay
renderer is ours: rings only where an element carrying the zone exists on the active page; the reconcile prompt is a message only. 9. The model port's
fixed fast-tier instructions tell the model to treat quoted material as data, which may dampen its response to on-page text in both arms. 10. One model
and one persona family. 11. Scores are discrete (0, 1/2, 1 and 0, 1) so ties and ceilings are likely and the t interval is not exact.

## 13. Calibration on FAKE participants before this plan was committed (no model was used)

Scripted participants ("skipper": both calculators then the note, never opens a cliff panel; "thorough": opens both cliff panels, switches tabs, chooses
discrepancy) drove the real extension, engine, coach and sandbox in private worlds. Facts established, none of which is a study result:
the minimum path is 21 actions and about 33 with checks and tab switches (cap set to 60); the coach fired a cliff `annotate` (zone `cliff_button`, step
`cliff_a`, `expert_policy`, L1) and a reconcile `annotate` (zone `results_tabs`, step `reconcile`) in coached blocks and stayed silent in uncoached, A/A and
post-test blocks; the delay from the first case-note-page action to the prompt was 7.9 s, 8.0 s and 8.5 s in three runs (so a participant that finishes the
note page in under about 8 s never sees a prompt: this is why the pace is 2 s per action); a tab switch produces a `tab` event and a newly opened tab does not;
`click` and `focus` events on the case note page land with zone `case_note`; 0 events landed with consent off; 0 schema-invalid events; the `KILL` file is
reported by `GET /kill` and the coach stays silent under it. One contaminated-sandbox incident (another actor on the shared sites) led to the private-worlds
design. The fake participants' scores are meaningless and are not kept.

## 14. How it is run

```
uv run --package understudy-agent python -m pytest evals/study_sim/tests -q                          # unit tests (no model, no network)
uv run --package understudy-agent python -m evals.study_sim fake --plan "1=skipper+obeys" --pace 3.5 # harness check on a FAKE participant
uv run --package understudy-agent --env-file .env python -m evals.study_sim run --workers 3          # needs the GO file; model participants
uv run --package understudy-agent python -m evals.study_sim analyze                                  # summary.json and REPORT.md
```

Outputs after GO: `results/participants.csv`, `results/raw/`, `results/actions.jsonl` (action kinds, element ids and zones only; never page text; the only
model text kept is the 280-character note), `results/checks/<pid>.json`, `results/cost_ledger.jsonl`, `results/cost.json`, `results/summary.json` (produced
via `analyze.py` plus the A/A analysis; `study_sim_section()` in `section.py` returns it for engine-eval) and `REPORT.md`.

## Amendment log

_Entries are dated and never edit the sections above._

**Amendment 1 (2026-11-07, about 16:55 GMT, after GO at 16:33, before any arm-level result was examined or analysed): run 1 aborted, harness repair, restart.**
What happened. Run 1 started at 16:33 with 3 workers. After its first participants (p_sim01 and p_sim03 complete; p_sim02, p_sim04 and p_sim05 in flight) I saw,
in the progress lines, the post-test scores of p_sim01 and p_sim03, and that 2 of the first 4 cases had hit the 60-action cap. I then read p_sim01's action log
and the cached model replies and found that about 11% of the values the model "typed" (34 of 298 fills) carried JSON structure characters or stray punctuation
from its structured reply ('36},{', '12000/', '12000.00?', '42 42 42 42 ...'). Those values break the calculators' numeric fields and send the participant into
re-entry loops, which is noise unrelated to arm, skill, persona or the coach, and which would push most reconcile post-tests to the floor (no saved draft).
I judged it a defect of the reply interface, not participant behaviour, and stopped the run (SIGINT, which also produced two spurious `ConnectError` exclusions
in run 1's CSV for the interrupted participants).
The repair (the only change). Before a participant types a value or chooses a dropdown option, `observe.clean_typed` removes (1) everything from the first JSON
structure character (`} { [ ] " \`) on, (2) a trailing `,` or `;`, (3) a trailing run of `?` or `/` after a digit, (4) a single token repeated four or more times.
Currency symbols and words, wrong numbers and every other human-like mistake are left alone. It is applied to every participant in every arm and block; the number
of cleaned values is counted and reported (`typed_values_cleaned`). It is unit-tested on the observed examples and was checked on a FAKE participant before the restart.
Not changed: prompts, persona texts and assignment, the task script, caps (60 actions, 2 s pace, 4 actions per reply), cases, scoring, analysis, budget cap.
What happens to run 1. Its outputs (336 model calls, about US$0.39 at the stated prices) are kept in `evals/study_sim/aborted_run1/`, **not analysed** and not used
for any decision; its spend counts against the US$8 cap (the new run's budget guard starts from it). Run 2 starts with an empty cache, a new ledger and the same
fixed run order, ids and personas, so p_sim01 to p_sim24 are run again from scratch.
Pricing note (not a method change): the token prices in the report (US$0.75 in and 4.50 out per million tokens for the fast model) were supplied by the lead from a
web search of OpenAI's model page and are an assumption that may have changed.

**Amendment 2 (2026-11-07, about 17:05 GMT, before run 2 starts; harness robustness only, found on the FAKE check of Amendment 1).**
The FAKE check showed two things that would also have corrupted a model run. (1) The in-tree extension build `extension/dist-ssim0` vanished between two cases of one
participant (something working in `extension/` removed it), which excluded the participant. Fix: each world's extension build is copied into a private temp folder and
the in-tree copy removed at once; the browser loads the private copy. (2) A case was flagged contaminated at its very first look (a calculation the participant had not
made) and, in the retried attempt, one of two "Check cliff edges" presses was missing from the sandbox state (a reset by someone else mid-case, which the old check, which
only looked for EXCESS activity, could not see). The sandbox state of a private world was watched for 45 s afterwards and nothing touched it, so the source remains unknown.
Fix: the per-case check now also fails a case when the state SHRANK since the previous look, when the sandbox has logged fewer cliff panels than the participant
successfully opened, or when a saved draft leaves no note; such a case is restarted like any contaminated case (up to 3 attempts). The check never looks at scores.
No prompt, persona, cap, pace, case, scoring, analysis or budget changed. Tests for both are in `tests/`.

**Amendment 3 (2026-11-07, about 17:12 GMT; harness and reporting only; no participant data existed).** Run 2 was started at 17:01 and aborted at 17:04, three minutes in and before
any participant had finished, once the FAKE check showed that the pipeline under test had changed while the harness was being built: other tracks moved the engine's
reconcile target from zone `results_tabs` (no page element) to `reconcile_control` (the case note's reconciliation dropdown, now carrying that zone in the sandbox page, the
extension's capture config and the engine's mapping). Because the engine is started fresh for every participant from the live working tree, participants run hours apart
would have met different coaches. Fixes: (1) **the code under test is frozen for the whole run**: `services/engine`, `services/agent` and `packages` are copied once at the start
into a temp folder, every engine and sandbox process runs from that copy (git head, number of uncommitted files and a content fingerprint are written to `results/snapshot.json` and
printed in REPORT.md); the extension is frozen by its single build per world; (2) the pre-registered check "ring target correct" counts the reconcile control zone as either
`results_tabs` (the plan's original) or `reconcile_control` (the engine's current), and the report lists the zones actually served; (3) a dropdown choice is matched to an option
the way a person would pick it (exact text or value, else a case-insensitive prefix or substring) instead of failing on an inexact string. No prompt, persona, cap, pace, case,
scoring, analysis or budget changed. Run 2's six model calls (US$0.006) are in `evals/study_sim/aborted_run2/` and count against the cap; the study run proper is run 3.
