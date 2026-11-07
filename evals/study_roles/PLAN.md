# PLAN: simulated study for the programmer and data-analyst roles (pre-registration)

**Label used everywhere: "simulated participants (language model), not people".**

**Status: written before any model-driven participant has run.** The commit that adds this file must come before the first model-driven run; its git timestamp is the proof.
Until the lead replies GO the harness has been run only on FAKE participants (scripted, no model, no cost, section 14); `pilot` and `run` refuse to start without the file
`evals/study_roles/GO`. After GO this file changes only by dated entries in the amendment log at the bottom. No prompt, persona, case, cap, pace, scoring rule, pilot criterion or
analysis is tuned after any result, ever: if the harness is broken it is fixed on FAKE participants only and the fix is logged.

## 1. What this is for, and what it cannot show

The live study with people is run by `evals/study/` (four teammates, benefits role only). The benefits role also has a simulated study (`evals/study_sim/`). This plan extends the
simulated study to the **programmer** and **data-analyst** roles, **as a test, never as a substitute for people**. Its purposes:

1. **An end-to-end test of the real pipeline for the two thin role packs**: real extension -> real engine with the role pack -> real coach brain -> a prompt drawn on the page -> a
   participant reacts -> `POST /coach/feedback`; every case scored by an ORACLE in code, no model involved.
2. **Evidence on whether the coach's prompts change the behaviour of a language-model novice on a later unassisted case**, per skill: a statement about a model reading our prompts in
   sandboxes we built.
3. **An A/A control** (a sham arm in which the coach is silent in every block) that estimates how biased the measurement chain is.
4. **A measure of how often a participant declares work done that the oracle says is wrong** (`claimed_done_wrong`), the false-claim rate the project cares about.

It **cannot** show: that people learn from the coach; that novices become experts; anything about real programming or analysis work; anything about speed in seconds; that a model's
self-written note is memory. It never touches the `study` section of the report (`section.evaluate_study_roles()` is a separate section). Every table and sentence carries the label.

## 2. Design

Per role there are three skills and a participant works **two of them (a pair)**; each skill is one **block** of three cases of that skill:

    pre-test (unassisted)  ->  practice (coached or not)  ->  post-test (unassisted, a held-out variant of the pre-test's task)

| Role | Skills (pack skill id) | Tasks (2 per skill, 2 variants each: 12 cases) |
|---|---|---|
| programmer | `boundary` (probe-the-boundary), `missing` (inspect-the-inputs), `discipline` (test-first-clean-commits) | p-boundary-1/2, p-missing-1/2, p-discipline-1/2 |
| data analyst | `sanity` (profile-before-querying), `reconcile` (reconcile-to-control), `aggregation` (segment-before-concluding) | d-sanity-1/2, d-reconcile-1/2, d-aggregation-1/2 |

* **Pairs and sequences.** Pairs cycle (s0,s1), (s1,s2), (s2,s0). For a pair (X, Y) there are four sequences: X coached then Y uncoached; Y coached then X uncoached; X uncoached then Y
  coached; Y uncoached then X coached. 12 sequences per role (`R01` to `R12`). Within each pair each skill is coached in two of its four sequences and each order occurs twice, so
  differences in how hard a skill is cancel in the headline mean.
* **Matched cases.** Pre-test and post-test are the SAME task, variants 1 and 2 (same structure and difficulty, different data, names and numbers). The practice case is the OTHER task of
  the skill. Two bits per participant (which task is the practice task, which variant is the pre-test) are spread over the 12 sequences (`design.cell_bits`).
* **Units and arms.** The run order has three **units**, one per pair; a unit is 4 coached participants (the four sequences of the pair) followed by the same four sequences as the **A/A
  sham arm** (same personas, same cases, the coach silent in every block; sequence labels are *nominal* for them and only serve to run the headline analysis unchanged; their true effect is
  zero by construction). A unit has 8 participants; a budget stop at a unit boundary leaves a design balanced within each pair. **Full design: 3 units = 12 coached + 12 A/A per role
  (24 participants).** The number of units actually run is fixed by the measured pilot cost (section 8).
* **Study mode.** Each case sets the engine's own study mode through `POST /study/mode`: `train` with `skill_on` = the block's pack skill id and level `L1` for a coached practice, `off`
  for an uncoached practice, `post_test` for every pre-test and post-test (always silent). Per-task `steps_off` drops pack steps that do not apply to a task (stated in the sandbox
  catalogue; e.g. the test-first task has no failing test to read, so `read_trace_first` is dropped).
* **Order and interleaving.** The order of the two skill blocks is counterbalanced across sequences (as in the benefits study). An interleaved SCHEDULE within a participant and the weaker "novice" prompt of a prompt-sensitivity check are **not part of this plan** (the lead did not fund them); the `novice` persona text exists in `participant.py` only so that a later, separately funded amendment can state it in advance.
* **The participant is told only** the facilitator's text for the role (`roles.py`), which says what the workbench is, to commit/answer and press the finishing button, and never to press
  the forbidden control; the case text is on the page. It is **not told** what the checks are called or why they matter.

## 3. The sandboxes (private ports, oracle in code)

`services/agent/understudy_agent/sandbox_roles/`. Programmer ports 7941 to 7948, analyst 7951 to 7958 (never the shared 7801-7803 sites, the engine :7700, the agent :7710 or the dashboard).
In-page JavaScript, no CDN, no network (strict CSP; a sandbox page may only talk to its own origin).

* **Programmer workbench.** A ticket, a file tree, one editor, Run tests with a failing trace, a console (`Try an expression`), a sample-inputs panel, docs, a git panel (stage, review
  diff, commit, log), Mark done, and a forbidden "Deploy to production". **How participant code runs:** only inside the browser, in a Web Worker served with its own CSP
  (`connect-src 'none'`), `fetch`/XHR/WebSocket removed before any user code, 1.5 s wall-clock cap after which the worker is terminated; nothing runs on the host and the repository's
  `run_python` runtime is not used. Hidden tests are not in the page: the harness passes them to `window.__grade` after the case.
* **Data-analyst workbench.** A ticket-like question, a 15-row table view with sort, filter, a profile panel, a group-by pivot (two dimensions, seven aggregates, a ratio measure), cleaning
  actions (duplicates, units, ID normalisation, a lookup join, exclude, undo), a control-figure panel, a chart, an answer form with a status, and a forbidden "Publish to the shared
  dashboard". Datasets are generated from fixed seeds; the truth of each case is recomputed independently in the tests.
* **Forgiving forms (declared in advance).** A bad value never silently changes state and never forces a restart: a filter value that is not a number is refused with a visible, correctable
  message on the same page; a commit with nothing staged or no message says so; the answer parser takes the first number in what was typed; there is no wizard and there are no hidden fields
  that carry earlier values forward; the participant's text is never "cleaned" by the harness (study-sim's `clean_typed` is NOT used here). An unforgiving form would measure typing noise.
* **Glitch variants** exist in both sandboxes (`?glitch=503once|503always` shows a retry page; `?layout=v2` renames labels and rearranges panels, zones unchanged). The study runs the clean
  variants; the glitches are tested in the sandbox tests.

**The oracle** (`oracle.score(task, variant, state)`, pure, no model): `correct` = 2 points, `partial` = 1, `wrong` = 0, `claimed_done_wrong` = 0 (shown separately).

* Programmer: wrong state = a visible or core hidden test fails. correct = all visible and hidden tests pass, the fix is committed, and the task's discipline conditions hold (test-first task: a
  new test that fails on the original code and passes on the fix, written before the first source edit, committed with it; clean-commit task: the commits hold only the fix file(s), the
  message has at least three words, is not generic and names the change, and the diff was opened before the first commit). partial = the reported bug is fixed but a hidden EDGE test fails (the
  naive fix), or all passes but a commit/discipline condition is missing. claimed_done_wrong = Mark done pressed while the bug is not fixed.
* Analyst: correct = the answer is within tolerance of the truth and the status is not "I did not check". partial = a designated half-fixed value, or the right answer with the status "I did
  not check". claimed_done_wrong = a wrong answer with status "Checked and consistent" or "Found problems and handled them". wrong = no answer, or a wrong answer honestly marked "I did not check".
* **Process indicator** (secondary): `skill_check_done`, did the participant use the check the task's skill is about (probe after the first source edit; inputs opened before the first edit;
  test edit before the first source edit; diff opened before the first commit; profile before any use of the data; a control comparison; a pivot grouped by the right dimension).

## 4. The participant (a language model)

* Reached through `understudy_agent.models.get_model_port()` with `port.check(prompt, schema)`. **Declared options, fixed now** (`participant.TIERS`): (1) **`fast`**: the fast model at reasoning
  effort none (the port's default for the fast role); (2) **`fast-low`**: the same call with `OPENAI_EFFORT_FAST=low` set by the harness before the port is built. **There is no larger tier:**
  if both options fail the pilot, the study stops and says so (a bigger model needs a new plan). Model ids come from the environment through the port and are recorded in the CSV (`model`, `tier`).
* It sees what a person would see: the page text, the full text of the text boxes (the code editor), a numbered list of the visible controls with labels and current values (no attributes,
  zones or ids), what it has done so far, how many actions are left, and the coach overlay when one is up (its text and a flag on the ringed control).
* **Actions** are typed and run through Playwright (trusted events, so the real extension captures them): `click`, `fill` (replace everything), `replace` (replace the first occurrence of a
  text in a box), `select`, `goto` (reload the page; the participant is not shown the address, which would carry the task id), `wait`, `dismiss_coach`, `finish`. At most 4 actions per reply; the rest are dropped if the page changes or a coach
  note appears. **The cap of a case is set from a no-model scripted walk of the oracle path, not from the benefits study:** `cap = max(30, 3 x L)` where `L` is the length in actions of the
  longest scripted expert program (four allowed orders) that the oracle scores `correct` on that case (`roles.case_cap`, tested; the table is in section 14). A cap that binds hides the skills: the
  benefits study (run 4) ended 18 of 32 post-tests at the cap and scored 30 of 32 at the floor. Also **a 2 s pause after every action** and a 900 s wall-clock hang guard (reported as capped).
* **The forbidden control.** If a participant tries to press "Deploy to production" / "Publish to the shared dashboard", the click is **not sent**; a protocol violation is recorded and the
  case stops as it stands (scored as it stands).
* **Personas** (as in the benefits study; neutral about the job's habits; every persona is a first-week junior): carefulness low/medium/high, reading of on-page prompts low/high, verbosity
  of its own notes terse/normal/wordy, assigned by seed 20261107, balanced within each pair of four sequences. A/A participants repeat the persona of their coached twin.
* **Learning proxy.** After each practice case the participant writes a note to itself (at most 280 characters) from a digest of what it did and what the coach showed (the same call in both
  conditions); it sees the note at the post-test of the **same skill only**. Every case otherwise starts from a fresh model context.
* Calls are cached by prompt hash (tier and participant code are in every prompt), so a retried case replays its answers at no cost; the cost ledger records every call.

## 5. The coach path (real) and the renderer (simulated)

The harness polls `GET /coach/next?person=...` every 3 s (steady pace, committing polls) while the participant acts; on `annotate`, `nudge` or `takeover_offer` it draws an overlay (message
line plus an orange ring round the element carrying `data-understudy-zone=<target zone>` if the page has one). The coach's step -> skill map comes from the **pack's expert steps**; what
counts as following a prompt is an action on a control in the step's zone (probe: `edge_probe`; inputs: `input_data`; write the failing test: `test_editor`; review the diff: `diff_view`;
profile: `profile_panel`; control comparison: `control_panel`; pivot: `pivot_panel`), so it holds in both layouts. Followed / dismissed / ignored (still up at the end of the case or
replaced) are posted to `POST /coach/feedback`. A prompt for a step already done more than 6 s earlier is **false**; within 6 s it is **lagging**. The ring cannot be drawn for the
test-editor zone while the source file is open (the element only exists while the test file is open): that case is a message line only and is counted (`banners_only`).

## 6. Private worlds, process model, determinism

Each worker has a private world: its own sandbox process on its own port (programmer 7941 + k, analyst 7951 + k), one extension build per world (`extension/dist-roles-*`, copied to a
private temp folder and the in-tree copy removed), one isolated engine per participant (ephemeral port, temp home and data dir, `AGENT_PORT=1`, no model key, copy of the synthetic data), one
Chromium context per case. **The code under test is frozen for the whole run**: `services/engine`, `services/agent` and `packages` are copied once at the start and every engine and sandbox
process runs from that copy (git head, number of uncommitted files and a content fingerprint go to `snapshot.json`). **At most 2 workers** (the lead's limit while the machine is shared).
The run order and, for every position, the arm, sequence, cases and persona are a pure function of the seed (`design.py`, tested). Which worker runs a participant is dynamic and is not a design
factor. After every case the sandbox's epoch and log are checked (a reset or a shrinking log means someone else touched the world: the case is restarted, up to 3 attempts, never scored).
Output folders go through `analysis_io.check_output_dir` (never under `evals/study/`, no symlinks), every folder of the results tree carries `PROVENANCE.json`, and the results live in
`evals/study_roles/results/<role>/` (pilots in `pilot_<tier>/`).

## 7. Measures and analysis (fixed now)

Reuses `evals/study/analyze.py` (imported, never edited): `t_interval`, `paired`, `sign_flip_p`, and the generic parts of `evals/study_sim/analysis.py` by import. CSV rows are in the human
format of `analyze.py` plus this design's columns; `post_checks_done` holds the oracle points of the post-test (out of 2). Effort is **ACTION COUNTS**, never seconds.

1. **Design check** (listed, never silently fixed).
2. **PRIMARY OUTCOME.** Per coached-arm participant: the post-test oracle points of the coached skill minus those of the uncoached skill (on the held-out variant, unassisted). The headline is
   the mean of these differences over the coached-arm participants (in fractions of the 2 points), with the 95% t interval (df = n - 1) and the **exact two-sided sign-flip p** over all 2^n
   sign patterns (smallest possible 2 / 2^n). Wording fixed in advance: if the interval excludes 0 and no difference is negative, "coached skills scored higher than uncoached ones for
   these model participants; this is instruction following plus a self-written note in a sandbox we built"; if the interval includes 0, "consistent with no effect and with a moderate one;
   n participants cannot tell"; if below 0 or any difference is negative, it is shown and named. A result counts as clear only if the interval excludes zero. A zero-width interval is flagged
   and the sign-flip p is read beside it.
3. **Secondary (descriptive, no multiplicity adjustment):** (a) the pre-to-post change contrast (post minus pre of the coached skill minus the same of the uncoached skill); (b) per skill: the
   baseline (pre-test mean, share at the floor, share fully correct), post-test mean where the skill was coached vs not with a percentile bootstrap interval (10000 resamples, seed
   20261107, people resampled within group); (c) outcome counts (correct / partial / wrong / claimed_done_wrong) for pre, practice and post by condition; (d) the **claimed-done-but-wrong
   count** in pre and post and the share of finished post-tests with edge cases missed; (e) the process indicator `skill_check_done` pre vs post coached vs uncoached; (f) effort in actions
   and the coach's nudges (shown, followed, dismissed, ignored, false, lagging, rings drawn, banners only, zone correct).
4. **A/A:** the same headline on the sham participants, coached-minus-A/A (percentile bootstrap, secondary), and the **false-positive check**: every balanced relabelling of the A/A participants
   (half keep the sign, half flip it; C(n, n/2) patterns) analysed like the headline: the share with sign-flip p < 0.05 and the share whose t interval excludes 0 (nominal 0.05; exact, no
   sampling, conditional on these scores).
5. No pooling across blocks or roles, no covariates, no model. Roles are analysed and reported separately. Persona and worker are not analysed.

**Expected power, stated before any data** (a small Monte Carlo of exactly this primary analysis, 4000 replications, seed 20261107; the assumptions are MADE UP: the per-participant difference is
Normal(effect, SD 0.5) rounded to half-points and clipped to [-1, 1]; effects are mean differences in fractions of the 2 points, so 0.15, 0.3 and 0.5 are 0.3, 0.6 and 1 point). Chance that the
95% t interval excludes 0, and that the exact sign-flip p is below 0.05:

| coached n | effect 0 (false positive) | 0.15 | 0.3 | 0.5 |
|---|---|---|---|---|
| 8 (CI excludes 0) | 6.3% | 13.8% | 33.7% | 69.8% |
| 8 (sign-flip p < 0.05) | 0.9% | 2.8% | 11.9% | 41.8% |
| 12 (CI excludes 0) | 4.6% | 14.9% | 45.9% | 85.9% |
| 12 (sign-flip p < 0.05) | 1.9% | 8.2% | 32.0% | 75.1% |

**So a null or small result from 8 to 12 coached participants does NOT show that the coach has no effect.** The design cancels generic carry-over and block-order shifts; it does not cancel
spill-over of a coached gain to the other skill of the pair.

## 8. Feasibility pilot, participant option, and how n is chosen (all declared now)

The benefits study found the fast model at the floor (run 4: 30 of 32 post-tests scored 0, 18 ended by the cap; the run 5 pilot at effort low also failed: 0 of 6 post-tests above zero, 57 to 60 of
60 actions used, so the cap bound before any skill was reached). That makes a coach comparison uninformative. So, before any main run:

1. **Pilot.** For each role, **3 participants, A/A arm only** (`design.build_pilot`: one per pair, sequences R01, R05, R09; the coach silent in every block), working **only their unassisted cases**
   (the pre-test and the post-test of each of their two blocks: 4 cases each, **12 cases per role**; no practice case, no note, so a pilot participant costs about two thirds of a study participant).
   They are **discarded from all analysis** and used only to decide whether an option is usable and what a participant costs. Options, in order: `fast`, then `fast-low` (only if `fast` is not usable).
2. **Usable** (all must hold, decided by code, `analysis.pilot_verdict`, tested; thresholds fixed now): (a) **floor:** at most 50% of the 12 unassisted cases score 0 points; (b) **ceiling:** at most 80%
   score the full 2 points (a coach needs room to help); (c) **cap-binding:** at most 25% of them end by the action cap or the wall cap or use at least 95% of their cap; (d) no harness exclusion and the pilot
   is complete (all 3 participants ran).
3. **Stop rule.** If an option is not usable on a role, try the next option for that role; **if every option fails, STOP and report that the participant model cannot do these tasks in these sandboxes (a
   floor finding), or has no room to improve (a ceiling finding), or that the cap binds (a cap finding): that is itself the result. Do not escalate to a bigger model or change a threshold, a prompt or a
   cap to rescue it; that needs a new plan.** `run` refuses to start on an option without a usable pilot.
4. **How many units (n).** The measured mean cost per pilot participant `c` fixes the number of whole units `u` (8 participants each) a role may run: the largest `u <= 3` with
   `u * 8 * c * 1.5 * 1.3 <= (budget left) / (roles still to run)` (1.5: a study participant works 6 cases plus two notes against the pilot's 4 cases; 1.3: a safety factor; `analysis.plan_units`).
   **If `u < 2` the role is not run** (8 or fewer participants could not say anything). The programmer role goes first with half of what is left; the analyst role then gets what is really left.
   The two roles are never pooled.

## 9. Budget and stop rules

* **Cap: US$8 in total for BOTH roles including every pilot, and the pilots together at most US$2** (the owner's US$60 is shared with other tracks and about US$20 is already used; if more is needed I
  report and the lead asks the owner). One ledger (`results/cost_ledger.jsonl`) for all runs; each run carries the spend of every earlier run in the tree (`cost.json: usd_this_run`), so the caps hold across
  processes. **Hard stops in code** (`budget_roles.RolesBudget`): the pilots run under a budget capped at the carried spend plus what is left of their US$2; no new participant starts when the estimate plus
  1.5 times the mean cost of finished participants for every participant in flight would pass 95% of the cap; a call that would pass 100% raises and ends the run. A participant cut off mid-way is excluded
  and listed (budget stop), never half-analysed; a pilot cut off is "incomplete", hence not usable. Runs are resumable (finished participants are in `participants.csv` and are skipped; model answers are cached).
* **Prices** come from `STUDY_SIM_PRICE_IN` / `STUDY_SIM_PRICE_OUT` (US$ per million tokens) if set, else the guard's conservative defaults (2.50 and 15.00). Token counts come from the model port's own usage
  statistics. The report says which prices were used and that the cost is an estimate.
* **Cost estimate, before any data.** The benefits study measured about 116 calls and 119k input plus 12k output tokens per participant, US$0.32 per participant at the fast tier with effort low (4 cases per
  participant). A role participant has 6 cases plus two notes and longer prompts (page text up to 6000 characters, the editor or the table, 12 history lines): **about US$0.25 to 0.5**. A pilot participant (4
  unassisted cases) about US$0.15 to 0.3, so one role's pilot of 3 about US$0.5 to 0.9 and both roles about US$1 to 1.8: inside the US$2 for one option, **not for two options on both roles**. With US$8 and
  pilots of about US$1 to 1.8, **the most likely outcome is one role run with 2 units (8 coached + 8 A/A, US$3 to 6) and the other role not run**; both roles run only if the measured pilot cost is at most about
  US$0.1 per pilot participant (2 units of one role cost `2 * 8 * c * 1.5 * 1.3`). The study may therefore end with one role, or with none (a floor, ceiling or cap finding). All of this is decided by the rule in
  section 8 on the measured cost, not by this estimate.

## 10. Exclusions (harness error only, decided before looking at any score)

A participant is excluded **entirely** (both blocks) only for a harness error: the model provider failing, a sandbox crash, the engine or extension failing, an unrecoverable contaminated case
after 3 attempts, a budget stop mid-participant. Never for a score, an action count, a refusal to follow the coach, a cap hit or a protocol violation. Every exclusion is listed with its reason;
tables print the n they actually have. If fewer than 8 coached-arm participants of a role survive, that role's status is `harness_failure` and no headline claim is made.

## 11. Pipeline checks (reported with counts)

Events landed per participant (by type and zone; schema-valid against `packages/schema/event.schema.json`); task starts and ends; coach decisions issued and what became of them; the zones
served for each skill and whether a ring could be drawn; false and lagging prompts; **study-mode enforcement: zero coach actions in any pre-test, post-test and uncoached or A/A practice block,
and none for a skill that was not switched on** (checked three ways: the mode tag of every poll, the stored `coach_shown` events, and the counts by block; **any violation is a bug and the lead is
told immediately**); errors (engine tracebacks, error lines, non-2xx answers to `POST /events`, web errors, harness tracebacks, contaminated attempts); consent (with the toggle off the extension
must send nothing, probed before capture is on and after it is off); the kill flag in the participant's own data dir.

## 12. What we will NOT claim

That people learn from the coach, or would; that the coach works on real programming or analysis work; that novices become experts; that a model's note is memory or that instruction following
is retention; anything about speed in seconds; anything about other models or options than the one piloted; statistical significance beyond what the exact sign-flip test gives (a result is
clear only if the interval excludes zero); that the simulated study validates the product; that a null shows the coach has no effect; anything pooled across the two roles.

## 13. Limitations (also in `summary.json.limitations`)

1. The participants are language models, not people. 2. Their only memory is a 280-character note they wrote themselves; each case starts from a fresh context. 3. A model told to "try the edges"
can just do it: instruction following, not retention. 4. The prompts, sandboxes, tasks, oracles and personas were all written by us. 5. Power is low (section 7): 8 to 12 coached participants, possibly one role only (section 9).
6. The counterbalanced design cancels carry-over and block order within a pair, not spill-over. 7. Timing is not human: effort is action counts. 8. The overlay renderer is ours (rings only where
an element with the zone exists). 9. One model family and one option (fast, effort none or low), chosen by a pilot of 3 participants per role that is not part of the evidence; the cap, the floor and the ceiling are judged on 12 cases. 10. Scores are discrete (0, 1, 2), so ties and ceilings
are likely and the t interval is not exact. 11. The oracles encode our idea of a good fix and a good analysis (for example the commit-message rule); another reasonable rule would score some
cases differently. 12. The sandbox tasks of one skill are matched by construction, not by measurement; the pre-test measures the real baseline per skill.

## 14. Pre-GO addendum (2026-11-07 20:06 UTC): calibration on FAKE participants, the cap lesson, what was fixed

Written before any model call (pilot included); nothing here is a study result. The fake participants are scripted (no model, no cost): `skipper` (the naive path), `expert` (the scripted oracle path),
`claimer`, with `obeys` (do the step the coach note points at) or `dismisses` (close the note). They drove the REAL pipeline: the extension build (with the actor header), an isolated engine per participant
with the role pack, the coach, a private sandbox world, the oracle and the CSV writer.

**Facts established**

* **Capture.** Per participant (6 cases) 144 to 217 events landed from the extension for the programmer (24 to 36 per case: skipper 24, expert 36) and 69 to 80 for the analyst (about 12 per case), 0 schema-invalid, one `task_start` and one
  `task_end` per case, `progress` events from the hash navigations, 0 `POST /events` failures, consent probe 0 events with the toggle off and 0 after switching off, kill flag respected, no contaminated case,
  no engine traceback. Zones that landed include `test_report`, `edge_probe`, `input_data`, `diff_view`, `commit_box`, `profile_panel`, `pivot_panel`, `clean_panel`, `run_control`, `decision_btn`.
* **Oracle through the whole path.** Programmer: skipper = partial in all cases, expert = correct in all cases. Analyst: skipper = claimed_done_wrong in all cases.
* **The coach fires in the real pipeline, per skill, and stays silent where the plan says.** Coached practice cases at a 4 s pace: programmer `boundary` (annotate on zone `edge_probe`, step
  `probe_edges`, followed), `missing` (annotate on `input_data`, step `inspect_inputs`, followed once and dismissed once), analyst `sanity` (annotate on `profile_panel`, step `profile_inputs`, followed),
  `reconcile` (annotate on `control_panel`, step `reconcile_to_control`, dismissed). For the two skills not reached through the browser (programmer `discipline`, analyst `aggregation`) the same event
  sequences were replayed through the real `CoachBrain` with the role pack: `Write a failing test before you change the code.` (zone `test_editor`), `Cut the data by the right dimension before you compare or
  average.` (zone `pivot_panel`), `Reconcile the total with the control figure before you report it.` (zone `control_panel`). Every prompt was one L1 annotate, once per task. **0 non-silent decisions in any
  pre-test, post-test or uncoached practice block; 0 study-mode violations in the stored events.** Rings were found for every prompt (`rings_drawn` = shown), no false or lagging prompt.
* **Timing fact.** The coach needs two signals after the violating step (a prompt arrived 3 to 30 s after the participant's first action, 6 s after the violating step in the in-process replay). A scripted
  participant at a 2 s pace finishes the case first (8 actions in 16 s): that is why the fake coached runs used a 4 s pace; a model's own latency per step is of that order.

**Bugs found by this calibration and fixed before the plan was committed** (each has a test): (1) the extension's `POST /events` was refused by the new engine guard (no actor header): fixed by the extension and
engine owners; (2) the pack's `task_end` marker matched the HIDDEN done banner at page load, which closed every task at once and silenced the coach: the marker is now `#case-done:not([hidden])`, and
`services/agent/tests/roles/test_capture_config.py` evaluates every marker and navigation selector of the pack against the real pages before and after the action it stands for; (3) the analyst coach
could not fire for a naive participant (the only later step needed a cog the sandbox cannot produce): `run_and_inspect` is now the Apply button (the RUN_QUERY cog) and typing in the answer panel
starts the report step; (4) the participant was shown the page address, which carried the task id (and so the skill name): the address is no longer shown; (5) the engine's temp folder prefix collided with
study-sim's cleanup: the harness uses its own prefix.

**The cap lesson (set before any model call).** The benefits study ended 18 of 32 post-tests at its 60-action cap and scored 30 of 32 at the floor; its run 5 pilot at effort low used 57 to 60 of 60 actions and
reached no skill. So the caps here are not taken from that study: `cap = max(30, 3 x L)` with `L` the longest scripted expert path the oracle scores correct (`roles.case_cap`). Table (oracle path -> cap, in
actions): programmer p-boundary-1/2 15 -> 45, p-missing-1/2 16 -> 48, p-discipline-1 20 -> 60, p-discipline-2 16 -> 48; analyst d-sanity-1 8 -> 30, d-sanity-2 9 -> 30, d-reconcile-1 18 -> 54, d-reconcile-2
22 -> 66, d-aggregation-1 19 -> 57, d-aggregation-2 14 -> 42 (both variants of a task have the same cap). The pilot decides on the floor (share of unassisted cases scoring 0), the ceiling and the
**cap-binding rate** (share ending by the cap or using at least 95% of it), by code, and the study stops if every option fails (section 8).

**Reused from study-sim** (imported or copied by idea): the output-directory guard (`check_output_dir`, never under `evals/study/`, no symlinks), `PROVENANCE.json` in every folder of the results tree, the
frozen pipeline snapshot, private temp copies of the extension build, the landing checks of the stored events, the budget guard (extended with a shared cap), the overlay renderer. **Not reused on purpose:**
`clean_typed` (value cleaning): the role forms are forgiving and code, expressions and filters legitimately contain brackets and quotes; nothing is repaired for the participant.

**Tests.** 178 tests: the two sandboxes (every case: expert correct, skipper partial or claimed_done_wrong, claimer, layouts, glitches, worker safety, markers), the packs and the extension bundle (zones,
cog mapping, capture sites on the private ports), the design (balance, matched cases, personas, run order, pilot), the coach rules, the analysis on made-up numbers (headline, A/A relabelling, pilot criteria,
unit planning), the report and the section (`not_run` until results), output safety, and the refusals of the model-driven commands (no GO, mock set, no usable pilot, pilot cap used).

## 15. How it is run

```
uv run --package understudy-agent python -m pytest evals/study_roles/tests services/agent/tests/roles -q                       # unit tests and browser tests of the sandboxes (no model)
uv run --package understudy-agent python -m evals.study_roles fake --role programmer --plan "1=skipper+obeys,5=expert"        # harness check on FAKE participants
uv run --package understudy-agent python -m evals.study_roles experts --role programmer                                       # record 8 scripted EXPERT runs (no model)
uv run --package understudy-agent --env-file .env python -m evals.study_roles pilot --role programmer --tier fast              # feasibility pilot (GO needed)
uv run --package understudy-agent --env-file .env python -m evals.study_roles run --role programmer --tier fast --roles-left 2 # the study (GO and a usable pilot needed)
uv run --package understudy-agent python -m evals.study_roles analyze --role programmer                                        # summary.json and REPORT.md
```

Outputs after GO: `results/<role>/participants.csv`, `raw/`, `actions.jsonl` (action kinds, element ids, zones; never page text; the only model text kept is the 280-character note),
`checks/<pid>.json`, `cost.json`, `summary.json`, `REPORT.md`, `PILOT_<tier>.json`; `experts/<role>/run_NN.json` for the synthetic experts.

## Amendment log

_Entries are dated and never edit the sections above._
