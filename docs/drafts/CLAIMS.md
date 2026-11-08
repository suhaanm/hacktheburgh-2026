<!--
CLAIMS REGISTER for README.draft.md, DEVPOST.md, DEV_POST.md, DEMO_SCRIPT.md and DEMO_DAY_CHECKLIST.md.
Written 7 Nov 2026, about 19:40 GMT, by the NARRATIVE track. Nothing here was run; every number was read from the files named, or computed from them as stated.
Snapshot used: evals/report.json and evals/report.md generated 2026-11-07T17:38:00Z, git 1bab986, mock mode; docs/FEATURE_CATALOGUE.md last edited 17:45; evals/review/privacy_honesty.md and safety_actuator.md as of 17:55 and 17:56; evals/study_sim/PLAN_RUN5.md as of about 18:15.
When any of these files changes, re-check the row. The lead tells this track when the catalogue changes.
-->

# Claims register

How to use it. Each row is one quantitative or capability claim that a draft makes. The draft carries a tag such as `(source: report.md "Controls"; C03)`; find C03 here, open the file, check the number. Strip the tags before publishing.

**Status vocabulary.**
- **traced**: the number or statement matches the cited file at the snapshot above.
- **traced, caveat**: matches, but the claim is limited; the draft carries the caveat in the same sentence.
- **derived**: computed by this track from cited numbers; the formula is in the row.
- **pending**: depends on a result that has not landed; the drafts say so or leave it out.
- **left out**: could not be traced, or is stronger than the evidence; it is not in the drafts (see section 3).

**Origin words used in the drafts.** *synthetic* (data we generated); *real model, small n* (a live model on our sandbox sites); *simulated participants (language model), not people*; *live study (n = 4 teammates): not run*. The report's own origin badges are on every section.

## 1. Quantitative claims

Abbreviations: R = README.draft.md, D = DEVPOST.md, P = DEV_POST.md, S = DEMO_SCRIPT.md, K = DEMO_DAY_CHECKLIST.md. Report sections are in `evals/report.md`.

### The analysis

| ID | Claim | Numbers | n, split, interval, origin | Source | Status | Used |
|---|---|---|---|---|---|---|
| C01 | The alignment finds the deficits we planted | precision 92% [84.5, 98.6]; recall 95% [88.6, 100.0] | synthetic; 16 people; 5 planted deficits over 32 novice cases (16 novices vs 8 experts); cluster bootstrap by person, B = 2000; 95% | report.md "Deficit recovery (EVL-1)" | traced, caveat (planted structure, not real people) | R D P |
| C02 | Weakest on two deficits | "reads the result again and again": precision 70% [40.0, 94.1], bias +13.5 s; "copies the wrong figure": recall 71% [33.3, 100.0], bias -14.0 s | as C01 | report.md "Deficit recovery"; limitation `eval-deficit-weak`, `eval-deficit-bias` | traced | R D |
| C03 | The gap is not an artefact | real novice vs nearest expert 229.6 s per case [192.7, 272.6]; placebo 7.1 s [-2.8, 18.4]; shuffled-label null 46.2 s [-36.4, 116.9]; permutation p = 0.001 | synthetic; 24 people; B = 2000; 1,000 permutations; 95% | report.md "Controls: placebo and shuffled-label null"; limitation `eval-null-offset` | traced, caveat (the null is about 20% of the real gap; both control intervals include zero) | R D P S |
| C04 | The stuck model beats two baselines | log loss 0.436 [0.422, 0.451] vs 0.509 [0.496, 0.524] (time since progress) and 0.509 [0.497, 0.524] (base rate); Brier 0.140 vs 0.164 | synthetic; leave one person out; n = 4 people; 7,376 scored 30 s bins from 2,676 episodes; label = no progress in the next 60 s; 95% | report.md "Stuck hazard (leave one person out)" | traced, caveat (n = 4; intervals resample episodes, not people) | R D P |
| C05 | The stuck model's alerts are modest | false alarms 1.21 an hour [0.95, 1.48] vs budget 1.0; 33% [27.5, 38.6] of stuck events flagged | as C04 | report.md "Stuck hazard"; limitations `ana-hazard-alerts`, `eval-hazard-alarm-budget` | traced | R D P |
| C06 | The dignity gate cuts false nudges | false nudges per hour 1.83 to 0.05 (report: "fall by 97%"); stuck events reached 21% to 5%; nudges 186 to 17; median latency 30 s to 60 s | synthetic; n = 4 people, leave one person out; the report's table shows no interval | report.md "Coaching dignity gate" | traced, caveat (no interval in the report's table) | R D P |
| C07 | Skill tracing is weak | mean Spearman 0.18 across 4 personas (0.17, 0.18, 0.25, 0.12) | synthetic; n = 4 personas | report.md "Skill tracing"; limitation `ana-skills-saturate` | traced | R D P |
| C08 | Off-policy estimators recover a known truth, mostly | naive average mean error +0.193, interval covers the truth 0%; IPS covers 96%, SNIPS 96%, doubly robust 88%; in the detailed run every interval missed the true value 0.018 | simulator; 24 replications of 2,400 decisions; detailed run 6,000 decisions; 95% | report.md "Off-policy evaluation"; limitation `eval-ope-coverage` | traced, caveat (reward structure is ours) | R P |
| C09 | Review routing: bound held, circular | held-out error 0.0% [0.0, 1.7] at 93.8% coverage; target alpha 0.05 | synthetic; 900 households, train 450 / calibration 225 / held-out 225 | report.md "Review routing and risk control"; limitations `ana-routing-circular`, `routing-circularity` | traced, caveat (circular: states it) | R D P |
| C10 | Ski-rental build timing, and where it loses | regret 1.332 [1.322, 1.342] (lambda 0.2) vs 1.776 [1.765, 1.786] (break-even); build now 1.273 [1.257, 1.290]; lowest regret is build now at b = 4, 8, 16 and the prediction rule at b = 32 | synthetic; 4,000 simulated routines; b = 16 manual runs | report.md "Ski-rental build timing"; limitation `ski-not-uniformly-best` | traced, caveat | R D |
| C11 | Start-or-wait for background runs | interruption 2.1% vs 24.8% (run whenever idle 5 min) vs 2.0% (fixed overnight window); idle time used 74.2% vs 90.2% vs 43.0%; cap 10%; window Brier 0.131 | synthetic; 4 personas x 21 days; forward held-out days | report.md "Presence and window forecast"; limitations `presence-weekly-template`, `presence-interval-coverage`, `presence-idle-capacity` | traced, caveat | R D S |
| C12 | The routine finder | 6 of 6 proposals are planted routines [61.0, 100.0]; recall 100% [74.1, 100.0]; raw finder: 12 of 55 clusters (22% [12.9, 34.4]) | synthetic; 4 personas | report.md "Routine finder" | traced, caveat (value gate does the work) | R D |
| C13 | Recurrence forecast coverage | 8 of 11 routines inside the interval, 73% [43.4, 90.3] | synthetic; 11 routines; fit days 1-14, scored 15-21 | report.md "Recurrence forecast" | traced (not quoted in the drafts except via limits) | none |
| C14 | A claimed success can be flagged | Brier 0.077 [0.066, 0.090] vs 0.183 base; real model: 68 claims from 20 households, Brier 0.004 vs 0.294 | synthetic 600 runs, grouped 5-fold by household; real model small n, one family of failure | report.md "Agent-claim calibration"; limitation `ana-claims-live-tiny` | traced, caveat (real-model false claims are one family) | R D |
| C15 | Partial pooling is hard to tell from complete pooling | at 0 and 1 own episodes complete pooling is best; at 3 and 10 partial pooling is best, by about 0.001 | synthetic; 4 personas | report.md "Partial pooling for new people" | traced (not quoted) | none |
| C16 | What n = 4 can detect | smallest exact two-sided sign-flip p at n = 4 is 0.125 (n = 16: 3.05e-05); for a medium effect the interval excludes 0 in 4.4% of runs at n = 4 and 27.3% at n = 16; false-positive rate 1.7% and 4.9% | Monte Carlo of the pre-registered analysis; 10,000 replications | report.md "Study power: what the design could detect" | traced, caveat (a property of the design under our assumptions) | R D S |
| C17 | The register and the evidence map | limitations register: 220 entries (70 high, 120 medium, 30 low); the evidence map: 37 sections, 35 with numbers, 0 pending, 2 not run (the live study and the study across roles), 0 failed | report as regenerated 8 Nov 2026 02:58 GMT (git 9780781); re-pull after the next `make eval` | report.md "Limitations register", "Evidence map"; the severity split is counted from the table in `evals/report.md` | **derived** (severity counts) / traced (219, 37) | R D |

### The agent and its defences

| ID | Claim | Numbers | n, split, interval, origin | Source | Status | Used |
|---|---|---|---|---|---|---|
| C20 | Mock model, clean path | 20 of 20 [0.84, 1.00]; tier 1 on 20; mean 1.8 s; 0 false claims. The report: "a full pass is expected and says little" | synthetic sandbox; mock model; 20 households | report.md "Agent runs on the sandbox (AGT-5, AGT-7)" | traced, caveat | R D |
| C21 | Mock model, with injected failures | 20 of 20 [0.84, 1.00]; 15 of 20 needed tier 2; four patterns only; 0 false claims | as C20 | same | traced, caveat | R |
| C22 | Planted calculator discrepancies | 7 of 20 households flagged | as C20 | same | traced | R |
| C23 | Real model, clean and layout change | clean 18 of 20 [0.70, 0.97], 0 false claims, 2 honest failures; layout change 20 of 20 [0.84, 1.00] | real model, small n; 20 households per condition; browser-agent tier forced (tier 1 disabled); one model family, one prompt; cached prompts | same; limitations `eval-agent-live-small-n` | traced, caveat | R D S |
| C24 | Real model on a one-off error page | passed the code check on 0 of 20 [0.00, 0.16]; claimed finished in 20 of 20; 20 false claims; the code check caught every one | real model, small n; 20 households | same; limitation `eval-agent-live-glitch-false-claims` | traced | R D P S |
| C25 | After the fix | 10 of 10 [0.72, 1.00], 0 false claims. **In-sample**: the fix was made after seeing the failure and re-run on the same condition; the run stopped at the cost budget after 10 households (9 later rows dropped); the fix run used a cap of 40 actions per navigator, the first run 20 | real model, 10 households | same; limitation `eval-agent-live-fix-in-sample` | traced, caveat | R D P S |
| C26 | Injected pages, real model | the detector paused 20 of 20 runs before the planner acted; 0 of 20 attacks succeeded; task success 0 by design | real model, 20 households; pages we wrote | same; limitation `eval-agent-live-injected` | traced, caveat | R D |
| C27 | **Superseded 8 Nov** (see C106 and the OpenAI held-out row in README): computer use is not demonstrated on the benefits task | 3 runs against a simulated actuator made 0 pointer actions and landed on an interactive element 0 times; the model declined at step 1 because tier-3 goals carry no household values by design | real screenshots of the headless sandbox, simulated actuator; n = 3 | same; limitation `eval-agent-live-tier3`; docs/REQ7_PLAN.md section 1 (fact handles) | traced | R D |
| C30 | Scripted red team | attack success 0.0% [0.0, 8.4] with every layer on, 100.0% [91.6, 100.0] with all off; task success under attack 23.8% [13.5, 38.5] (a detector hit pauses the run); false pauses 0.0% [0.0, 11.0] on 31 clean pages (10 hard negatives); removing the detector alone did not let an attack through | synthetic; 42 attacks (37 committed catalogue + 5 supplemental built-in) x 10 configurations; scripted vulnerable planner | report.md "Red team with ablations"; limitations `scripted_planner`, `synthetic_catalog`, `detector_tradeoff` | traced, caveat | R D P |
| C31 | Real-model red team | 0 of 126 runs with every layer on [0.0, 8.4]; 5 of 126 with all off (4.0% [1.0, 14.7]); task success 22% [12.3, 36.8] vs 84% [70.3, 92.2]; 76% paused with every layer on; false pauses 0 of 93 clean runs [0.0, 11.0] (in-sample) | real model; 42 attack cases x 3 repeats x 2 configurations; 31 clean pages x 3; cached answers; intervals treat repeats as one observation | report.md "Red team with a real model (secondary, cached)"; limitations `eval-redteam-live-reading`, `eval-redteam-live-in-sample` | traced, caveat (intervals overlap) | R D P |
| C40 | Planted strings did not reach the model port | 0 of 11,456 planted tokens, 88 runs of 11 flows, 144 requests, 8 seeds per flow; 0 leaks in 88 files; ledger complete for every flow; 11 of 11 negative controls; **run-level one-sided 95% upper bound 3.35% (0 of 88 runs)** | synthetic fixtures with planted canaries; capturing fake port | report.md "Privacy layer (canary leaks, offline)" (regenerated 8 Nov 02:58 GMT; the earlier 11,336 / 80 / 10 / 3.7% figures were the 7 Nov run) | traced, caveat; the report's token-level bound is **not quoted**: tokens within a run are correlated | R D S |
| C41 | Calendar canary | 0 of 11,104 planted tokens across 169 outbound requests | synthetic | report.md "Calendar layer" | traced (not quoted) | none |
| C42 | Privacy review result | no critical finding; 6 high, 9 medium, 8 low. High: H1 voice sent free text (fixed); H2 raw model calls not in the ledger by default (fixed); H3 origin check let any site write to worker-only routes (fixed on the engine, agent service open); H4 any site could set and clear the kill switch (fixed on the engine, agent service open); H5 the live study could be fed from simulation (fixed); H6 legacy desktop code sends screenshots and file text with no gate (open) | review by a separate Claude Sonnet 5.5 agent; state at 17:55 | evals/review/privacy_honesty.md sections 1 to 4 | traced; **re-check**: the review's own summary line says five of six are fixed, while its table shows H3, H4 and H6 not fully closed; the drafts follow the table | R D P S |
| C43 | Safety review result | 18 findings: 1 critical (S-01), 8 high, 1 medium-high, 7 medium, 1 low; 15 fixed in code (82 Python tests: 71 pass, 11 fail = open findings; 2 TypeScript pass); open: S-02 (kill flag and approval have no authentication), S-08 (an actuator check can report ok with no read-back), S-11 (approvals are weak) | review by a separate Claude Sonnet 5.5 agent; state at 17:56 | evals/review/safety_actuator.md | traced; **re-check** after the re-run | R D P S |

### Layers added after kickoff

| ID | Claim | Numbers | n, split, interval, origin | Source | Status | Used |
|---|---|---|---|---|---|---|
| C50 | Git habits | precision 100% (116 of 116) [96.8, 100.0]; recall 97% (116 of 120) [91.7, 98.7]; specificity 100% (120 of 120); placebo false flags 1% (5 of 480) [0.4, 2.4]; at 25% of planted strength recall 19% | synthetic; 120 learner-habit pairs (10 replicates of 4 learners and 8 experts); thresholds chosen on replicates 0 to 3, scored on 100 and up | report.md "Git habits (programmer role)"; limitations `git-circularity`, `git-small-effects` | traced, caveat | R |
| C51 | Calendar layer | planted problems precision 93.9%, recall 98.2%; suggestions against the planted cause 96.4% and 89.9%; 0 of 24 expert weeks flagged | synthetic; 28 people | report.md "Calendar layer"; limitations `cal-synthetic-only`, `cal-experts-synthetic`, `cal-graph-unverified` | traced, caveat | R |
| C52 | Proactive briefing | judge precision 82% [70.4, 89.9] (101 of 124 cards worth surfacing), recall 86% [75.5, 93.2]; baselines 55%, 51%, 46%; 145 briefings, 0 cap violations, mean 0.86 cards, 0 unprompted fires | synthetic; 145 decisions; bootstrap over 35 people; development set; simulated worker | report.md "Proactive cards"; limitations `pro-iterated-on-eval`, `pro-acceptance-simulated` | traced, caveat; the catalogue's 0.80 and 0.84 are older (see section 3) | R |
| C53 | Local model digests | commit category 91.8% [84.7, 95.8] vs rules 77.5% [68.3, 84.7]; event category 95.9% [90.0, 98.4] vs 81.6% [72.8, 88.0]; three other fields no clear difference (rules ship) | synthetic; 98 held-out items per field | report.md "Local model digests"; limitations `loc_synthetic`, `loc_authorship` | traced, caveat | R |
| C54 | The local model can be steered | with one planted line, the model-for-everything run followed it on 19 of 19 commit categories (revert), 17 of 17 risk (high), 13 of 17 event category, 12 of 12 needs_prep; keyword rules 0 in each | synthetic; 20 items per task | report.json limitation `loc_injection` | traced | R |

### Code-level evidence, spikes and decisions

| ID | Claim | Numbers | n, split, interval, origin | Source | Status | Used |
|---|---|---|---|---|---|---|
| C60 | The coach rings the skipped step | 14 of 14 planted cases ringed; 0 prompts to experts; no ring on a clean case; the same decisions with 3 s polls or event timestamps | synthetic apprentices, 48 cases; a test assertion (printed line), not a report section | services/engine/tests/coach/test_replay.py, `test_event_timestamps_for_the_gate_are_as_safe_as_poll_counts_on_the_replay_set` | traced, caveat (planted skip; clean score expected) | R D S |
| C61 | What skipping a step costs in answers | skipping reconcile is wrong on about 20.7 of 200 (10.3% [7.8, 13.0], expected over which calculator is trusted); skipping the cliff check leaves a nearby edge unwarned on 107 of 200 (53.5% [46.6, 60.3]), and a small change moves the award by more than 50 pounds a month on 42; the middle of three calculators is right on 200 of 200 | synthetic; 200 households cycling through 12 archetypes; oracle is a simplified rule set; calculators' quirks planted | evals/cases/skip_consequences.json; evals/cases/skip_consequences.py (docstring: the first version used one calculator and made skipping look harmless) | traced, caveat | R D P S |
| C62 | Capture works on a real browser | a real MV3 extension in Chromium 158 under Playwright: ten schema-valid events from a real page reached a stub server in about 3.3 s; typing and paste in a password field produced zero events; no page text, URL or secret in the payload | one real run, stub server; one Chromium build | docs/SPIKES.md S3 | traced, caveat (one browser build) | R P |
| C63 | One real click passed; the agent's actuator then failed | S2: TextEdit, one click and one typed line read back through AppleScript; mapping error 0.0 pt; click 40 ms; whole test 8.9 s. Follow-up: `mac_check --real` reported ok while the document was empty; the click landed in another app's window | one run each, owner present | docs/SPIKES.md S2 and S2 follow-up | traced | R D P S |
| C64 | The oracle is not the law | agrees with PolicyEngine UK within 1 pound on 8 of 20 generated households | 20 generated households | docs/SPIKES.md S4; report.md limitation `eval-oracle` | traced | R D P |
| C65 | How much of Alongside was reused | of the 303 `src/` files of the Alongside copy at commit b46c87e: 168 byte-identical in `apps/desktop/src` on main, 100 modified, 35 not carried over; 355 files new (tests included); at about 03:20 GMT on 8 Nov (main acdc0b7) | a read-only count of git blob ids of the two trees (`git ls-tree -r`), the same identity test as the README's SHA-256 method; equality with the owner's own Alongside tree is not verified | **derived** by the feature-docs track; the earlier 205 / 70 / 28 / 313 used another baseline (the Alongside tree itself) and is retired here; the numbers drift while the desktop track edits | **derived**; recompute at the freeze | R D P S |
| C66 | Sandbox and replay facts | the three calculators are sandbox sites with planted quirks; CASE-1005 = household hh_0005: GovCalc 638, Quick Estimator 742.64, EntitledTo 638.24; the golden run is a recording of a mock-mode run on household hh_0004 (mock: true, recorded 15:18) | n/a | evals/cases/households_20.json; data/golden/benefits_golden.json; report.md limitation `eval-sandbox-sites` | traced | R S |

### Studies

| ID | Claim | Numbers | n, split, origin | Source | Status | Used |
|---|---|---|---|---|---|---|
| C70 | The live study has not been run | no data in `evals/study/results/`; the section shows no numbers; a human-study manifest is required before the section can fill (decision D39) | n = 4 teammates planned | report.md "Live study (n = 4)"; docs/DECISIONS.md D39 | traced | R D S P |
| C71 | Simulated study design | 16 coached participants (4 per sequence) plus an 8-participant sham arm with the coach silent; real extension, engine and coach brain; pre-registered in `evals/study_sim/PLAN.md` (commit 7690160) before any model-driven run | simulated participants (language model), not people | evals/study_sim/PLAN.md sections 1 to 3; git log | traced | R |
| C72 | The first simulated run hit the floor | the pre-registered run (run 4, fast model, 24 participants planned): most post-tests ended at the 60-action cap with no calculation done; scores almost all zero in both arms; says nothing about the coach. Causes named in the plan: the model types junk into fields; a hidden field in the first calculator's wizard makes the final Calculate fail on a page whose faulty field is not visible | simulated participants (language model), not people | evals/study_sim/PLAN_RUN5.md section 1 | **traced to a plan document, not to final numbers**; [LEAD: replace with the run's own figures and intervals when `participants.csv` is analysed and the report section fills] | R D P S |
| C73 | Earlier simulated attempts were stopped | run 1 (typed-value artefacts blocked numeric fields; 2 participants complete, not analysed), run 2 (stopped to freeze the pipeline; no data), run 3 (restarted to add the engine-event export; no data) | n/a | evals/study_sim/aborted_run1, aborted_run2, aborted_run3 `NOTE.json` | traced | R P |
| C74 | Run 5 is exploratory | the same fast model with its reasoning effort raised to low (the planner-tier option was withdrawn as unaffordable); 3 A/A pilot participants, then up to 12 (8 coached, 4 sham); US$6 cap; starts only after run 4's analysis is written; at n = 8 coached the interval excludes zero in 15.6% of runs for a medium effect | simulated participants; power from a Monte Carlo | evals/study_sim/PLAN_RUN5.md Amendments 1 and 2 and section 5 | traced; [LEAD: its state] | R |

### Held back

| ID | Claim | Why held back | Source |
|---|---|---|---|
| C80 | Model bake-off (Gemini flash-lite, Gemini flash, OpenAI fast) | The report's modelbench section was pending at 17:38, and `evals/modelbench/cache` was still growing at 17:58, so the results are in progress. A preliminary `evals/modelbench/REPORT.md` (17:49) exists on a synthetic sandbox UI; **no figure from it is quoted anywhere in the drafts** | evals/modelbench/REPORT.md; report.md "Model benchmark" |
| C81 | Spend | The cap is US$60 for live runs across tracks (D32), with per-track hard stops in code; the actual spend is not known to this track. The report's own cost lines read "about None USD" (a formatter bug, review L2) and are not quoted | docs/DECISIONS.md D32; evals/review/privacy_honesty.md L2 |

## 2. Capability claims

The status word is the catalogue's (docs/FEATURE_CATALOGUE.md, 17:45). "Draft wording" is the strongest sentence the drafts use.

| ID | Capability | Catalogue status | Draft wording |
|---|---|---|---|
| K01 | Work genome | verified | "aligns a novice's steps to the nearest expert's and prices each gap in seconds" (synthetic) |
| K02 | Controls (placebo, shuffled-label null) | verified | as K01 |
| K03 | Stuck model | verified | "predicts no progress in the next minute"; modest alerts, stated |
| K04 | Gap decomposition | built | listed under "built, not yet seen end to end" |
| K05 | Fading help levels L1 to L4 | verified | "decided by code, with mastery that decays" |
| K06 | Dignity gate and bandit | built | the gate's numbers only (C06) |
| K07 | Routines finder | built | C12 |
| K08 | Presence model | built | C11 |
| K09 | Review routing and trust ladder | built | C09; "A3 is a target, not a result" |
| K10 | Live coach brain | verified (synthetic replay) | C60 |
| K11 | On-screen annotations (REQ-4) | built (the lead viewed screenshots) | "draws a ring on the real screen"; placement measured on one display at 100% zoom (evals/README.fragment.md `rect-calibration-narrow`) |
| K12 | New logo and menu-bar icon | building | not claimed |
| K13 | Hold-to-talk activation | building | not claimed |
| K14 | Cue (stuck rescue) | building | "in progress"; the demo shows it only if the lead confirms it end to end |
| K15 | Independence score and Growth screen | building | "the screen exists and shows labelled example data until the assist ledger is wired"; no claim that the score measures expertise |
| K16 | On-device awareness | building | not claimed |
| K17 | Triggered and periodic glances | building | not claimed |
| K18 | Model routing across OpenAI, Gemini, a local model and ElevenLabs | building (bake-off pending) | "in progress"; no Gemini figure |
| K19 | Independent verifier | building | not claimed |
| K20 | Live voice | proposed | listed as proposed |
| K21 | Benefits agent on the sandbox calculators | verified | "completes the task on our sandbox calculators; a code check decides done"; real-model rows are small n (C20 to C26) |
| K22 | Eight security layers | verified | "mostly code"; measured by a scripted and a real-model red team with their limits (C30, C31) |
| K23 | Shadow mode to approval | verified | "a routine earns autonomy by matching what the worker does" (synthetic) |
| K24 | Computer use on the real screen | "not yet working" (superseded) | "Computer use on the sandbox: Gemini held-out clean 18 of 20, below the bar set in advance (C106); OpenAI held-out 1 of 4; nothing has driven a real desktop"; C63, C106 |
| K25 | Background agents | built | listed under built |
| K26 | Overnight automations | built | listed under built |
| K27 | Proactive briefing | built | C52 |
| K28 | Calendar routine layer | building | the README lists it under in progress and shows its synthetic result (C51) in the "Layers added after kickoff" table as a development result, with "never run on a live tenant" |
| K29 | Git analysis | built | C50 |
| K30 | Local model | built | C53, C54 |
| K31 | Privacy spine | built, with a known gap | the gap is stated (limit 9) |
| K32 | Evidence page and `make eval` | verified | "every number has n, split, interval and origin" |
| K33 | Simulated study | running (benefits) | C71 to C74; no result claimed |
| K34 | Role studies | building | not claimed |
| K35 | Realistic data and generator-mismatch test | building | not claimed |
| K36 | LLM explainer with number check | building | not claimed |
| K37 | ML v2 | building | not claimed |
| K38 | ElevenLabs voice route | **not in the catalogue** | "speaks fixed lines by id, ledgered, flag off by default, cached audio" (from the privacy review H1 fix and `services/agent/understudy_agent/voice/lines.py`); [LEAD: confirm status] |
| K39 | Auth0 thin sign-in | **not in the catalogue** | "a thin sign-in behind an interface with a local fallback" (from docs/DECISIONS.md D22 and `apps/dashboard/src/auth/`); [LEAD: confirm status; OWNER: tenant] |
| K40 | Role packs: one deep, two thin | **not in the catalogue** | stated as design (SPEC_LIST D4); the thin packs are "starting points"; none is called validated |
| K41 | Memory file the worker owns; onboarding | **not in the catalogue** | stated as design in the one-paragraph description; [LEAD: confirm wording] |
| K42 | Chrome extension capture | **not in the catalogue** | C62 only |

## 3. Left out, replaced or changed from the earlier drafts

| ID | Earlier statement | Where | What happened |
|---|---|---|---|
| X01 | "Agent runs on sandbox calculators: 40 of 40 pass, no false success claims (mock model)" | DEVPOST.md, README.draft.md ("40 runs") | Replaced. The clean mock path "says little", the real-model rows were omitted, and the real-model glitch condition passed 0 of 20 with 20 false claims (review M7). Now C20 to C26 |
| X02 | "37 attacks, 31 clean" | docs/FEATURE_CATALOGUE.md section 4 (hand-typed) | The report says 42 attacks and 31 clean pages. 37 is the committed catalogue alone; 42 adds 5 supplemental built-in attacks (report.md note). The drafts use 42. [LEAD: fix the catalogue] |
| X03 | "18 sections, 72 limitations" | docs/FEATURE_CATALOGUE.md section 6 | The report says 32 sections and 124 limitations. The review quoted 108 at an earlier run. The drafts use 124 and say "at 17:38"; re-pull. [LEAD: fix the catalogue] |
| X04 | "The full register (47 entries today)" | README.draft.md (earlier) | Replaced by C17 |
| X05 | "Proactive briefing: precision 0.80, recall 0.84 (development set)" | docs/FEATURE_CATALOGUE.md section 5 | The report says precision 82% [70.4, 89.9], recall 86% [75.5, 93.2]. The drafts use the report. [LEAD: fix the catalogue] |
| X06 | "smoke-tested with a real extension ... 203 events, all schema-valid" | README.draft.md (earlier) | **Not traceable** to any file. Replaced by S3's ten events (C62) |
| X07 | "Alongside's `src/` has 303 files; 247 are carried over unchanged, 33 are modified, 23 are not carried" | README.draft.md (earlier) | Stale. A hash comparison now gives 205 / 70 / 28 and 313 new (C65) |
| X08 | "Kept as is: the overlay (window, flight, ring, arrow, annotations)" | README.draft.md (earlier) | Not true any more: the overlay scene and the annotation shapes, labels and chrome were restyled (REQ-4). The overlay's flight, arrow and geometry helpers are unchanged. README rewritten |
| X09 | "the verifier loop" listed as kept | README.draft.md (earlier) | Alongside's verifier lived in `main/gemini/` and is not carried; ours is in `model-services`. README rewritten |
| X10 | A recorded "20-second recording made before the freeze" and a "recorded real run from the S2 spike" as fallbacks | DEMO_SCRIPT.md, DEMO_DAY_CHECKLIST.md (earlier) | No such recording is known to this track. Marked [OWNER] |
| X11 | The coach "was silent on every real browsing session until task markers were added" | DEVPOST.md, DEV_POST.md (earlier) | Not traceable to a file. The later `implicit_task` reason code (services/engine/tests/coach/test_implicit.py) suggests it happened. Left to the owner in DEV_POST.md |
| X12 | "A JSON Schema `(?i)` regular expression valid in Python and invalid in JavaScript" | DEV_POST.md (earlier) | No record found. Left to the owner |
| X13 | "We caught it because the answer was zero" (the skip table) | DEV_POST.md (earlier) | Not traceable. The traceable fact (the first version used one calculator that is faithful by construction) is kept |
| X14 | "trusting a random single calculator is wrong on about 10%" | DEV_POST.md (earlier) | Kept but rewritten with the figure: about 20.7 of 200, 10.3% [7.8, 13.0] (C61) |
| X15 | The report's token-level leak bound "0.03%" | report.md "Privacy layer" | Not quoted. Tokens within a run are correlated; the honest unit is the run (0 of 80, 3.7%) per review M5 |
| X16 | "Static guard: 27 violations in 172 files" inside an ok section; "about None USD" | report.md | Not quoted. The review says the code now gives 0 violations and the report is stale; the cost lines are a formatter bug. Regenerate before submitting |
| X17 | The model bake-off figures | evals/modelbench/REPORT.md | Held back (C80) |
| X18 | The YC "$15-an-hour expert" figure | docs/DECISIONS.md concern 8 | Not used: no citation to check. [OWNER: add a cited source if you want it] |
| X19 | Age UK 13% / 49% / 30% digital exclusion | apps/desktop/docs (Alongside's pitch) | Belongs to the earlier project, not this one. Not used |
| X20 | "Novices become experts"; "the system lifts novices" (CLAUDE.md's wording) | CLAUDE.md "Honesty" | The first is never said. The second is **not said as a result**: nothing measured yet shows coaching lifts anyone (live study not run; simulated study hit a floor). The drafts say the intended effect is that novices need less help and that this is unmeasured. [LEAD: this deliberately differs from CLAUDE.md's sentence; tell the owner] |
| X21 | "Everything stays on the laptop" / "nothing leaves" | several earlier phrases | Replaced by the ledger statement with its scope (C40, C42). In mock mode nothing reaches a model; outside it, calls the worker asked for are metadata-only in the ledger |
| X22 | "validated" about the benefits pack (SPEC_LIST D4) | spec | Not used. Everything is synthetic or sandbox |

## 4. What this track needs from the owner and the lead

**Owner** (only the owner can supply): the title, the opening moment, the build story and any reflection in DEV_POST.md; team names and roles; the repo URL and the demo video URL; whether an organiser was asked about reusing Alongside; the wording of the AI-assisted-build disclosure and what the hackathon's rules say about it; the licence; which MLH categories to enter and what each form asks; whether the Auth0 tenant exists; the DEV challenge prompt and tag; who answers judges' questions per track; whether any recording (ring clip, ribbon, queue, S2) exists.

**Lead** (confirm or supply): whether Cue works end to end on the demo laptop (and its exact keys, pause length and words); what the Growth screen shows on the demo home (example data or ledger data); what the Privacy screen shows (empty or mock rows); the desktop launch command and flags; the final test counts; the state of D38 (legacy desktop remote calls off by default); the state of the agent-service authentication (reviews S-02, H3, H4); the retest result of the real actuator, if any; the final numbers of the simulated study run 4 and run 5; the final report after the freeze, then a diff against this register; fixes to the catalogue (X02, X03, X05); the status of the ElevenLabs and Auth0 pieces; and how the Evidence page shows the real-model block (see below).

**One presentation hazard for the lead.** In `evals/report.json`, `sections.agent_runs.live` carries `headline_condition: "clean"`, `n: 20`, `pass: 18` and a top-level `false_claims: 20`. The 20 false claims are from the one-off-error-page condition, not the clean one (the clean condition has 0). The Evidence page's "Real model, small n" facts block renders that dictionary, so a reader could see "18 of 20 passed" beside "20 false claims" with no condition attached. The per-condition rows are in `conditions`.

## 5. Recompute the Alongside counts (read-only)

Run from the repo root on the build laptop. The path of the Alongside copy is `ALONGSIDE_PATH` in `.env`; this snippet takes it as an argument so nothing reads `.env`. It prints counts only.

```bash
python3 -I - /path/to/alongside <<'EOF'
import os, sys, hashlib
A = os.path.join(sys.argv[1], "src")
B = "apps/desktop/src"
def files(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ("node_modules", ".git")]
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out
a, b = files(A), files(B)
print("alongside src files:", len(a))
print("byte-identical:", sum(1 for k in a if k in b and a[k] == b[k]))
print("modified:", sum(1 for k in a if k in b and a[k] != b[k]))
print("not carried:", sum(1 for k in a if k not in b))
print("new in understudy:", sum(1 for k in b if k not in a))
EOF
```

Update C65, README "Disclosure: Alongside", DEVPOST "Disclosure" and DEMO_SCRIPT question 6 together.

## 6. Numbers that appear in more than one draft and must be changed together

| Number | Drafts | Row |
|---|---|---|
| 229.6 s, 7.1 s, 46.2 s, p = 0.001 | R D P S | C03 |
| 20 of 20 false claims; 0 of 20; 10 of 10 (in-sample) | R D P S | C24, C25 |
| 220 entries (70, 120, 30) | R D | C17 |
| 0 of 11,456; 88 runs; 3.35% | R D S | C40 |
| 168 / 100 / 35 / 355 | R D | C65 |
| 18 findings (15 fixed, 3 open); 6 high privacy findings | R D P S | C42, C43 |
| 107 and 42 of 200 | R D P S | C61 |
| 14 of 14, 48 cases | R D S | C60 |

## 7. HRT additions (C90 to C105)

The prospective ledger, the guard, the decisions scoreboard, online recalibration, conformal ranges, decision value against accuracy, the family size and Holm table, the one-command ledger proof and the data-pipeline paragraph (Track H, 8 Nov 2026) have their rows in **`docs/drafts/CLAIMS_HRT.md`**, which is **generated** from the reports by `scripts/hrt_brief.py` (`make hrt-brief`) so no number in it is typed by hand. Same columns and status words as above. Rows C92 and C93 are the sentence that **C04 and C05 must carry**: the stuck model's edge was mostly the generator, it reverses under shift, and a simple rule does about as well (FIX_LEDGER section G). Quoted so far in `docs/drafts/DEVPOST.md` (HRT bullet, limitation 10) and in the HRT 30-second cut (`docs/drafts/HRT_30S.md`); `tests/hrt/test_brief.py` checks that every number in those two HRT passages appears in the generated files.

## 8. Additions after the HRT section (C106 to C109), 8 Nov 2026 about 03:00 GMT

| ID | Claim | Numbers | n, split, origin | Source | Status | Used |
|---|---|---|---|---|---|---|
| C106 | Computer use with Gemini, held-out and pre-registered, did not meet its bar | clean n = 20: 18 completed with correct inputs on all three calculators (Wilson 0.70 to 0.97; rate 0.90); the pre-registered bar, a lower bound of at least 0.80, was not met; 2 paused, 0 false claims, nothing submitted; injected n = 20: 20 paused at step 0 | real model (Gemini), generated households on our sandbox, seeds 9139 and 9140, one run each, case note at tier 2, gate `a736b8dc8988`; the injected pages carry text only; **not pooled with the OpenAI round (1 of 4), and not the same measurement as the OpenAI agent-run row that also reads 18 of 20 [0.70, 0.97] (C23)** | `evals/agentic/results/round2_clean_9139.json`, `round2_injected_9140.json`, `evals/agentic/PLAN_ROUND2.md` (Results), `docs/DECISIONS.md` D65 | traced | README, Devpost |
| C107 | Knack can run model-written code on the open-ended task path, with per-task consent, and never in routines | a task that needs an agent starts the owner's own Claude command as a monitored child after one consent card; env allow-list of six variables, 30-minute cap by default, spend limit US$2 by default, Stop and the kill file end the process group; routines are a JSON step language; two small real runs (about US$0.125 together, owner approved); deny rules refused file-tool writes and reads of Knack's safety files in a throwaway copy of the layout, a shell command is assumed to bypass them; 160 tests with a fake command (the document's count) | the owner's Claude account, outside the US$200 Gemini cap; no real task has been run | `docs/TASKS.md`, `docs/DECISIONS.md` D63 and D64, `docs/IMPLEMENTATION_SPEC.md` 6.5 (amended) | traced, caveat (full computer access is the owner's choice) | README, Devpost |
| C108 | The app says where numbers come from in plain words and with no tag | no 'synthetic' or 'simulated' word, tag or badge in the app (D57); a closed 'About this data' line and the Evidence page's 'Measured on' column carry the provenance ('generators we wrote', 'language-model participants', 'live', 'real and generated', 'not run'); 'Example data' marks a sample that stands in; the README, Devpost and this register keep the word 'synthetic' | not a number | `docs/DECISIONS.md` D57, `docs/knack-ux/banned-phrases.json`, `apps/dashboard/src/lib/evidence.ts` | traced | README, Devpost, video narration |
| C109 | The role packs for the programmer and data analyst are at standard depth | programmer: 22 step types, 18 skills, 4 critical gates, 13 routine templates; analyst: 21, 16, 6, 13; written from the job, no study, no real traces | structure counts from the pack files and `docs/roles/*.md` | `packages/packs/programmer/`, `packages/packs/data-analyst/`, `docs/roles/programmer.md`, `docs/roles/data-analyst.md` | traced (counts); not validated | README, Devpost |
| C110 | One reviewed exception to the egress ledger | the hand-run live tier-3 evaluation `services/agent/understudy_agent/live_t3.py` calls the model through a raw port (`get_model_port(ledgered=False)`), outside the ledger; it runs only by hand, on generated sandbox pages, keeps its own spend ledger, and no other module imports it; the product's own paths all go through the ledger | a code fact, not a number | `services/agent/understudy_agent/live_t3.py`, `evals/review/privacy/test_p1b_voice_and_default_ledger.py` (REVIEWED_RAW_PORT_MODULES) | traced | README, Devpost |
| C111 | The suites passed on the merged tree | agent service 2,237 passed plus the roles and tasks tests fixed afterwards (114 together), 6 skipped (live; they need UNDERSTUDY_LIVE=1), `tests/core` all green; engine 4,067 passed, 97 skipped (mostly generated data absent in a fresh worktree), the one real failure fixed; the reviewer's safety reproducers 183 plus 2 in TypeScript, 185 in all; `evals/review/privacy` 114 passed (24 stale cases were turned into regression tests that assert the guard rule); the other evals (tests, study_roles, study_sim, modelbench) 297; dashboard 1,474; desktop 3,407 (5 skipped, opt-in); extension 262; packs 134; and the full eval re-run (35 sections ok, 0 pending, 2 not run, 0 failed) | counts of passed tests; skipped counts as stated | the SUITES report as relayed by the lead, 8 Nov about 03:35 GMT (not read from a file by this track) | **relayed**; re-read from the report before quoting | README, Devpost |
