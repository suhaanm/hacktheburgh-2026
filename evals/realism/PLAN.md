# Pre-registration: realism and generator-mismatch evaluation (REALISM track)

**Status: DRAFT.** Written Sat 7 Nov 2026 before any analytic has been run on v2 data. While the status is DRAFT the generators are still being implemented and the parameter table may gain rows or move a range if a marginal check shows a bug (never because of an analytic result: none has been run). The status becomes FROZEN when the lead is told "PLAN FROZEN" with the hash; the commit of that version is the evidence that it predates the analytics. Any change after that is listed under "Deviations" in `REPORT.md` with the reason, and the report states whether the generator-parameter hash below still matches.

**Honest boundary.** The v2 data are synthetic. Every table says "synthetic, realism-calibrated". The claim tested is *"the pipeline's results hold when the data come from generators it was not built on and whose marginals sit inside published ranges"*, never *"the pipeline works on real people"*. I do not tune the generators to make an analytic look good or bad: the generators are set from the published regularities in `personas_v2/cited.py` (checked marginals) and from structural plausibility, and whatever the analytics then do is reported.

## 1. Data

**Generator families** (`personas_v2`, deterministic given a seed): `markov` (plan-guided variable-order Markov chain over an augmented state, person-specific detour matrices, self-exciting detours), `latent_skill` (hidden flow, hesitate, stuck, recover process driven by per-skill mastery that learns), `process_trace` (task-grammar sampling with Dirichlet strategy mixtures, durations built bottom-up from KLM operators with a Fitts term and a Hick-Hyman term, retries). Shared by all three, stated up front: the person hierarchy, the interruption post-process, the capture-noise emitter, the role cog vocabulary and the task grammar's valid paths.

**Roles.** `benefits-processor` (deep: the five deficits of the pack, genome, hazard, routines), `data-analyst` and `programmer` (thin: pack cogs and two pack deficits each; hazard and routines only, because the genome's named-deficit labels are benefits-specific).

**Two kinds of dataset, each with the v1 event and truth structures:**

| Kind | Call | Size (per family, role, replicate) | Used for |
|---|---|---|---|
| cohort (the household-entry task, many people, 8 cases each) | `generate_cohort(family, role, n_people=48, cases_per_person=8, seed)` | 48 people, 384 episodes | genome (first 2 cases per person), marginal checks |
| workweeks (continuous work over days: routines and ad hoc tasks, interruptions, breaks, days off) | `generate_workweeks(family, role, n_people=40, n_days=14, seed)` | 40 people, about 14 days each | hazard (primary), routine finder, presence marginals |

**Replicates.** K = 3 independent replicates (independent hyper-parameter draws and independent people) per (family, role, kind). Seeds: `20261107 + 1000 * family_index + 100 * role_index + 10 * k + kind_index` with family_index markov 0, latent_skill 1, process_trace 2, role_index benefits 0, analyst 1, programmer 2, kind_index cohort 0, workweeks 1, k = 0, 1, 2. **v1** is a fourth "family" with its own seeded data (personas for hazard and routines, apprentices for the genome; the v1 generators are run with their own seeds into a temporary directory and are never modified).

## 2. Frozen generator parameters

Each dataset draws one value per row below from its range (domain randomisation). The rows are in `personas_v2/params.py`, which has SHA-256 `8e0801924e7fa915b3450aa5da85ed883d6f017f5c4e62bcad95e17658bbb1dc` at the time of this file. `REPORT.md` prints the hash at run time and flags a mismatch.

| Parameter | Low | High | Scale | Cited regularity (status) | Meaning |
|---|---|---|---|---|---|
| `sd_log_speed` | 0.12 | 0.3 | uniform | klm_keystroke_s (secondary) | SD across people of log speed (KLM tiers 0.12 to 0.28 s span a factor 2.3: SD about 0.2) |
| `sd_within` | 0.25 | 0.55 | uniform | assumption | within-person log-SD of a cog's dwell |
| `sd_within_person` | 0.1 | 0.35 | uniform | assumption | SD across people of the log multiplier on the within-person log-SD |
| `p_pause_med` | 0.03 | 0.12 | loguniform | pause_lognormal_mixture (secondary) | median per-step probability of a hesitation pause |
| `sd_logit_pause` | 0.4 | 0.9 | uniform | assumption | SD across people of the logit of the pause probability |
| `pause_mix_lognormal` | 0.3 | 0.7 | uniform | burstiness_cv (secondary) | share of pauses drawn from a lognormal (rest Lomax) |
| `pause_ln_median_s` | 4 | 12 | uniform | pause_lognormal_mixture (secondary) | median pause, lognormal component (s) |
| `pause_ln_sigma` | 0.8 | 1.3 | uniform | pause_lognormal_mixture (secondary) | log-SD of the lognormal pause component |
| `pause_lomax_alpha` | 1.1 | 2.2 | uniform | burstiness_cv (secondary) | tail index of the Lomax pause component |
| `pause_lomax_scale_s` | 3 | 10 | uniform | assumption | scale of the Lomax pause component (s) |
| `slip_med` | 0.01 | 0.05 | loguniform | slip_rate_per_step (secondary) | median per-step slip probability |
| `sd_logit_slip` | 0.4 | 0.9 | uniform | typing_population (qualitative) | SD across people of the logit of the slip probability |
| `rho_speed_slip` | -0.5 | 0.2 | uniform | typing_population (qualitative) | correlation of log speed (higher = slower) with slip propensity: faster people slip less, so negative |
| `g_loading` | 0.3 | 0.7 | uniform | assumption | loading of the general ability factor on speed, slips, hesitation and learning |
| `learn_alpha_mean` | 0.2 | 0.7 | uniform | power_law_exponent (secondary) | mean learning exponent across people |
| `learn_alpha_sd` | 0.05 | 0.2 | uniform | power_law_exponent (secondary) | SD of the learning exponent across people |
| `learn_beta_novice` | 0.5 | 1.2 | uniform | assumption | initial relative slowdown above the asymptote at zero practice |
| `p_exp_form` | 0.3 | 0.7 | uniform | power_law_exponent (secondary) | share of people whose individual curve is exponential, not a power law |
| `warmup` | 0 | 0.25 | uniform | practice_forgetting (assumption) | relative slowdown at the start of a session (decays over ten minutes) |
| `forget_tau_days` | 3 | 20 | uniform | practice_forgetting (assumption) | time constant of forgetting between sessions (days) |
| `fatigue_per_h` | 0 | 0.12 | uniform | fatigue_slowdown_per_hour (qualitative) | mean slowdown per hour of continuous work |
| `sd_fatigue` | 0.02 | 0.06 | uniform | assumption | SD across people of the fatigue slope |
| `circadian_amp` | 0 | 0.08 | uniform | circadian_amplitude (assumption) | amplitude of the time-of-day speed multiplier |
| `interrupt_per_h` | 0.5 | 5 | loguniform | interruptions_per_hour (secondary) | median interruptions per hour of work |
| `sd_log_interrupt` | 0.3 | 0.8 | uniform | assumption | SD across people of the log interruption rate |
| `int_len_median_s` | 15 | 120 | uniform | interruption_recovery_min (secondary) | median length of an ordinary interruption (s) |
| `int_len_sigma` | 0.8 | 1.4 | uniform | interruption_recovery_min (secondary) | log-SD of interruption length |
| `int_long_share` | 0.03 | 0.15 | uniform | interruption_recovery_min (secondary) | share of interruptions that are long (minutes) |
| `int_long_median_s` | 300 | 1500 | uniform | interruption_recovery_min (secondary) | median length of a long interruption (s) |
| `resume_reread_p` | 0.3 | 0.8 | uniform | interruption_recovery_min (secondary) | probability of re-reading after an interruption |
| `resume_slow` | 1.1 | 1.6 | uniform | interruption_recovery_min (secondary) | slowdown multiplier on the next two steps after resuming |
| `resume_error_mult` | 1 | 1.6 | uniform | interruption_recovery_min (secondary) | multiplier on slip probability right after resuming |
| `strategy_kappa` | 0.5 | 3 | uniform | assumption | Dirichlet concentration of a person's strategy mixture around the population's |
| `verify_reread_pop` | 0.05 | 0.3 | uniform | assumption | population share of the legitimate verification re-read strategy |
| `deficit_difficulty_sd` | 0.3 | 0.8 | uniform | assumption | SD of the skill-specific component of ability (deficits overlap through the general factor) |
| `pmax_skip_cliff` | 0.5 | 0.95 | uniform | assumption | per-check skip probability at zero mastery |
| `rework_found_p` | 0.3 | 0.9 | uniform | assumption | probability that a skipped check is found at reconciliation and reworked |
| `reread_mean_max` | 1 | 2.5 | uniform | assumption | mean extra re-reads after a result at zero mastery |
| `search_rounds_max` | 1.5 | 3.5 | uniform | assumption | mean search-read rounds at zero mastery |
| `copy_error_pmax` | 0.3 | 0.7 | uniform | assumption | probability of copying the wrong figure at zero mastery |
| `idle_pmax` | 0.5 | 0.9 | uniform | assumption | probability of a long hesitation before entering at zero mastery |
| `idle_lomax_scale_s` | 10 | 40 | uniform | assumption | scale of the long hesitation (Lomax, s) |
| `idle_lomax_alpha` | 1.3 | 2.5 | uniform | burstiness_cv (secondary) | tail index of the long hesitation |
| `material_s` | 5 | 5 | uniform | assumption | a deficit occurrence is material when it costs at least this many seconds (fixed) |
| `expert_share` | 0.3 | 0.5 | uniform | assumption | share of people labelled experts |
| `tenure_expert_median` | 100 | 600 | loguniform | assumption | median prior cases of a person above the tenure cut |
| `tenure_novice_median` | 2 | 30 | loguniform | assumption | median prior cases of a person below the tenure cut |
| `tenure_sd_log` | 0.5 | 1 | uniform | assumption | log-SD of tenure within the group |
| `tenure_g_corr` | 0.5 | 0.9 | uniform | assumption | correlation of tenure with the general ability factor (the label is only partly the ability) |
| `session_gap_days_mean` | 0.8 | 2.5 | uniform | assumption | mean days between sessions |
| `cases_per_session_mean` | 2 | 4.5 | uniform | assumption | mean cases per session |
| `between_case_gap_median_s` | 60 | 600 | loguniform | assumption | median pause between cases within a session (s) |
| `start_hour_mean` | 8.5 | 10.5 | uniform | assumption | mean session start hour (UTC) |
| `start_hour_sd` | 0.5 | 1.5 | uniform | assumption | SD of the session start hour |
| `drop_p` | 0 | 0.12 | uniform | assumption | probability an event is dropped |
| `drop_burst_p` | 0 | 0.3 | uniform | assumption | probability a drop starts an outage that drops the next 1 to 5 events |
| `jitter_sd_s` | 0.05 | 0.6 | uniform | assumption | SD of timestamp jitter (s) |
| `double_p` | 0 | 0.05 | uniform | assumption | probability an event fires twice within 20 to 400 ms |
| `zone_err_p` | 0 | 0.04 | uniform | assumption | probability an event carries a wrong zone |
| `label_missing_p` | 0 | 0.15 | uniform | assumption | probability an event has no label hash |
| `coarse_ts_p` | 0 | 0.05 | uniform | assumption | probability a timestamp is rounded to the whole second |
| `task_end_missing_p` | 0 | 0.08 | uniform | assumption | probability a task_end marker is missing |
| `os_skew_s` | 0 | 2 | uniform | assumption | clock skew between the OS source and the browser source (s) |
| `event_rate_per_s` | 0.15 | 0.7 | uniform | burstiness_cv (secondary) | mean interaction events per second of an active cog |
| `event_gap_sigma` | 0.8 | 1.4 | uniform | burstiness_cv (secondary) | log-SD of the gap between events inside a cog (burstiness) |
| `progress_emit_p` | 0.6 | 0.95 | uniform | assumption | probability a productive completion emits a progress event |
| `progress_lag_s` | 0 | 3 | uniform | assumption | mean lag of the progress event after the step ends (s) |
| `progress_early_p` | 0 | 0.2 | uniform | assumption | probability the progress event fires before the step ends |
| `spurious_progress_per_h` | 0.2 | 2 | loguniform | assumption | progress events not tied to a productive step, per hour |
| `stuck_report_p` | 0.05 | 0.6 | uniform | assumption | probability a stuck episode gets a self-reported stuck event |
| `stuck_false_per_h` | 0 | 0.5 | uniform | assumption | stuck reports outside any stuck episode, per hour |
| `mk_detour_base` | 0.02 | 0.12 | loguniform | assumption | markov: per-step probability of starting a detour |
| `mk_selfexcite` | 0.2 | 0.7 | uniform | burstiness_cv (secondary) | markov: probability a detour continues (self-excitation) |
| `mk_dirichlet_conc` | 2 | 12 | uniform | assumption | markov: concentration of people's detour matrices around the role's |
| `mk_backtrack_p` | 0 | 0.1 | uniform | assumption | markov: probability of going back a step |
| `mk_skipahead_p` | 0 | 0.08 | uniform | assumption | markov: probability of skipping ahead a step |
| `ls_hesitate_a` | -2.6 | -1.2 | uniform | assumption | latent_skill: intercept of the logit of leaving flow for hesitation at mastery 0.5 |
| `ls_hesitate_b` | 1 | 3 | uniform | assumption | latent_skill: how strongly low mastery pushes towards hesitation |
| `ls_hes_to_stuck` | 0.1 | 0.4 | uniform | assumption | latent_skill: probability a hesitation becomes a stuck episode |
| `ls_stuck_median_s` | 40 | 150 | uniform | assumption | latent_skill: median stuck episode length (s) |
| `ls_stuck_lomax_alpha` | 1.2 | 2.2 | uniform | burstiness_cv (secondary) | latent_skill: tail index of stuck episode length |
| `ls_theta_gain` | 0.5 | 2 | uniform | power_law_exponent (secondary) | latent_skill: gain in log-odds mastery from practice |
| `pt_pointing_a_s` | 0.1 | 0.8 | uniform | fitts_mouse_slope_s_per_bit (secondary) | process_trace: Fitts intercept (s) |
| `pt_pointing_b_s` | 0.08 | 0.2 | uniform | fitts_mouse_slope_s_per_bit (secondary) | process_trace: Fitts slope (s per bit) |
| `pt_keystroke_s` | 0.12 | 0.4 | loguniform | klm_keystroke_s (secondary) | process_trace: median keystroke time K across people (s) |
| `pt_mental_s` | 0.9 | 2 | uniform | klm_mental_s (secondary) | process_trace: mental operator M (s) |
| `pt_homing_s` | 0.3 | 0.6 | uniform | klm_homing_s (secondary) | process_trace: homing operator H (s) |
| `pt_hick_b_s` | 0.05 | 0.3 | uniform | hick_hyman_slope_s_per_bit (assumption) | process_trace: Hick-Hyman slope (s per bit) |
| `pt_method_switch_p` | 0 | 0.15 | uniform | assumption | process_trace: probability of switching method mid-task |
| `pt_retry_p` | 0.02 | 0.15 | uniform | assumption | process_trace: probability a step fails and is retried |
| `wk_p_work_weekday` | 0.75 | 0.97 | uniform | assumption | workweeks: probability of working on a weekday |
| `wk_p_work_weekend` | 0 | 0.2 | uniform | assumption | workweeks: probability of working on a weekend day |
| `wk_start_mean_h` | 8 | 10 | uniform | assumption | workweeks: mean start hour |
| `wk_start_day_sd_h` | 0.3 | 1.5 | uniform | assumption | workweeks: SD of the start hour across days |
| `wk_start_ar` | 0 | 0.5 | uniform | assumption | workweeks: day-to-day autocorrelation of the start hour |
| `wk_len_h` | 5 | 8.5 | uniform | assumption | workweeks: mean working window length (h) |
| `wk_holiday_p` | 0.02 | 0.08 | uniform | assumption | workweeks: probability a weekday is a day off |
| `wk_tasks_per_h` | 2 | 6 | uniform | assumption | workweeks: tasks started per active hour |
| `wk_task_gap_sigma` | 0.8 | 1.3 | uniform | burstiness_cv (secondary) | workweeks: log-SD of the gap between tasks |
| `wk_routine_share` | 0.25 | 0.6 | uniform | assumption | workweeks: share of tasks that are instances of a planted routine |
| `wk_routine_drift` | 0 | 0.3 | uniform | assumption | workweeks: weekly drift of the routine variant probabilities |
| `wk_split_p` | 0 | 0.12 | uniform | assumption | workweeks: probability a routine instance is split into two episodes by a task-detector error |
| `wk_interleave_p` | 0 | 0.15 | uniform | assumption | workweeks: probability another task is started in the middle of a routine |

## 3. What is run (public functions only; I do not copy analytic code)

* **Cog mapping:** `cogs.segment_episodes(events, pack_mapping)` with the role pack's own mapping (the benefits mapping equals the engine default). Analytics see only what the mapper makes of the noisy events, not the planted cog list.
* **Genome (benefits):** `genome.Cohort`, `Cohort.nearest`, `Cohort.novice_alignments`, `Cohort.placebo`, `genome.components`, `genome.deficit_prices`.
* **Stuck hazard:** `hazard.build_bins`, `hazard.HazardModel` (variants full, tsp, base), `hazard.events.choose_config`, `hazard.events.score_rows`, `hazard.oof_predictions`, `hazard.evaluate_hazard` (diagnostics on one dataset per family and role).
* **Routines:** `routines.finder.find_routines` with `FinderConfig`, `routines.detect.detect_routines` with the role pack (value gate and skill gate as shipped).

## 4. Pre-registered metrics

**Truth definitions (fixed here).**
* A deficit occurrence is **material** when it cost the person at least 5 s of net added time on that trace (`added_s - saved_s >= 5`, from the generator's own bookkeeping, exact by construction). A (trace, deficit) pair is **present** when the occurrence is material, **absent** when the deficit never occurred on the trace, and **indeterminate** (excluded from precision and recall, counted and reported) otherwise.
* A routine cluster is **true** when at least half its member episodes are instances of one planted routine; a planted routine is **detectable** when it has at least 3 instances (the finder's minimum support), and is **found** when a true cluster has it as its majority.
* A hazard bin's label, a stuck event, an alarm and the false-alarm budget are the shipped definitions (label 1 iff no `progress` event in the next 60 s; alarm budget 1.0 false alarms per non-stuck hour; tolerance 30 s).

**Primary metrics per analytic** (each reported with a person-level cluster bootstrap, B = 1000, over test people):

| Analytic | Primary | Secondary |
|---|---|---|
| Hazard (all roles) | **H1** gain over the time-since-progress baseline, `LL_tsp - LL_full` per bin, person-weighted mean (positive = the model helps) | H2 false alarms per non-stuck hour and detection rate at the rule chosen on the training data; log loss, Brier, ECE of full, tsp, base |
| Genome (benefits) | **G1** pooled precision and recall over material present and absent pairs | G2 bias in seconds per deficit (recovered minus true price among present); G3 false attribution seconds per absent pair; G4 placebo attribution (expert against nearest other expert); reference contamination (share of expert traces with a material deficit) |
| Routines (all roles) | **R1** cluster precision of the raw finder, **R2** recall of detectable planted routines | R3 precision over proposals after the value gate, with proposal counts |

**Fitting that the mismatch matrix moves between families** ("fit on X, test on Y"):
* hazard: the full, tsp and base models are fitted on X's bins; the alarm rule (threshold and 1 or 2 confirming bins) is chosen on X's leave-one-person-out out-of-fold predictions at the 1.0 per hour budget; both are applied unchanged to Y;
* genome: the expert reference set and the detection thresholds (`X_d = max(1 s, 95th percentile of the placebo attribution among X's experts)`) come from X; they are applied to Y's novices (so "reference from a different kind of generator");
* routines: the finder's cut height is chosen from a grid {0.20, 0.25, 0.30, 0.35, 0.40, 0.50} to maximise F1 of (R1, R2) pooled over X's people, then applied to Y's people; the fixed shipped value 0.35 is reported alongside (no fitting).

**The matrix.** Every ordered pair (X, Y) over {v1, markov, latent_skill, process_trace}. Train replicate k of X, test replicate (k + 1) mod 3 of Y (an independent draw even on the diagonal, so that a change of hyper-parameters is not attributed to a change of family). v1 as a training family uses its single dataset; v1 as a test family has its few people (4 personas, 16 novices and 8 experts) and says so. The reference for "degradation" in cell (X, Y) is the diagonal cell (Y, Y): `delta = metric(X -> Y) - metric(Y -> Y)`, paired by test people (the bootstrap resamples Y's test people and recomputes both cells on each draw; the diagonal cell uses the same test people). Cells are pooled over k with people as clusters. The replicate-to-replicate SD is reported beside every cell.

**Interpretation rules (fixed now).** A cell "**degrades**" when its `delta` interval lies entirely on the harmful side of zero (lower H1, lower G1 precision or recall, lower R1 or R2) and the point estimate exceeds the margin (H1 0.01 nats per bin; G1 0.10; R1 and R2 0.10). It "**transfers**" when the interval contains zero and the point estimate is inside the margin. Everything else is "**inconclusive**". For the hazard a cell has "**no skill**" when the interval of H1 itself includes 0 or lies below it. No margin or rule is changed after seeing a result.

**Pre-registered expectations** (written before running; reported even when wrong):
1. The hazard's gain over time-since-progress is smaller on every v2 family than the v1 personas (0.073 nats per bin in `evals/report.md`: 0.509 minus 0.436), because v2's progress events are late, missing and spurious and pauses are heavier-tailed. It stays positive on most v2 families.
2. Cross-family hazard gains are smaller than the diagonal in most cells; the false-alarm rate at the transferred alarm rule overshoots the 1.0 per hour budget in more cells than on the diagonal.
3. Genome recall for the named deficits falls well below v1's 95 percent (my guess: 0.4 to 0.8) because severities are continuous and the references include contaminated experts; precision falls because legitimate verification re-reads look like "repeated reads".
4. Routine finder cluster precision stays low (as in v1: 22 percent) and recall falls below v1's 100 percent because of drift, interleaving and split episodes.
5. The largest degradations involve `process_trace` (bottom-up operator times and a grammar-driven structure) as either side.

## 5. Marginal checks (is each family within published ranges?)

Computed from the generated data, not from any analytic; reported as "within published range" or "outside", with the status of the cited constant:
M1 effective keystroke operator K in the KLM range; M2 effective pointing time and throughput inside the Fitts and ISO ranges; M3 hesitation pauses: p99 over median in the leptokurtic range; M4 dwell body lognormal (Kolmogorov-Smirnov distance of log dwell standardised within cog and person, reported, range 0.15 or less); M5 practice: individual learning exponent estimates in 0.1 to 1.0, and the average curve better fit by a power than a line; M6 interruptions per hour in 0.5 to 6; M7 inter-event times bursty (CV above 1.1); M8 slip rate per productive step in 0.005 to 0.07; M9 between-person SD of log speed in 0.10 to 0.35; M10 person-level correlation of speed and slips negative; M11 fatigue slope in 0 to 0.15 per hour; M12 capture noise realised rates inside their ranges. Statuses (secondary, assumption) are printed beside each, and "within a range we assumed ourselves" is not called "published".

## 6. Compute and fast mode

The full run is `python -m understudy_engine.personas_v2.evaluate --full` (writes `evals/realism/REPORT.md` and `data/eval/realism.json`). `evaluate_realism(fast=True)` (under 60 s) uses 16 people per dataset, one replicate, the benefits role only, B = 200 and a 3-fold grouped hazard diagonal; it carries the same metrics and says "fast, small n" in its meta. If the full run's compute forces a smaller K or fewer people, the report states it under "Deviations" as made before looking at results.

## 7. What this cannot show

Nothing here shows the analytics work on real people. The generators are written by the same team; the label circularity (progress and stuck are defined by events we generate) is not removed; the three families share code (listed in section 1). The only evidence about real people is the live study (n = 4) and, if the owner agrees, a short labelled pilot (n = 1).
