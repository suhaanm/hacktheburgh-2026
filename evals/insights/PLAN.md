# Insights evaluation plan (REQ-9), pre-registered

Written by the INSIGHTS track on Sat 7 Nov 2026 before any held-out run. The lead commits this file; the held-out seeds are run once, after that commit, with no change to code or thresholds in between. Everything here is synthetic (badge `synthetic firm`; the worker worlds are badged `synthetic`). Nobody is a person.

What the evaluation can show: the selection behaves as designed under stated assumptions (it finds planted effects, stays quiet on null data at a measured rate, is deterministic and stable, and enforces the privacy rules). What it cannot show: that workers find the pointers useful, that admins decide better with them, that the planted effects look like real work, or that any of this is acceptable to real workers. The live check with the four teammates (n = 4) is not run.

## 1. Seeds and modes

* **Dev seeds 0 to 9**: anything may be inspected and tuned on them. **Held-out seeds 100 to 139**: run once, never tuned on.
* `evaluate_insights(fast=True)` uses dev seeds only and a small number of firms (about 20 to 40 s); `fast=False` uses all ten dev seeds; `evaluate_insights(fast=False, heldout=True)` uses the held-out seeds. The result carries `meta.seeds` saying which.
* The generators are `insights.firm.build_firm` (the synthetic firm and its null scenario) and the worker worlds in `insights/evaluate.py`. Both are written by the same author as the selection; the planted effects are therefore easier to recover than real ones. This is a robustness test of the code paths and the statistics, not a validation on people.

## 2. Deviations log: what was seen on dev data before this plan was written

Everything below was changed after looking at **seed 0 of the synthetic firm (and hand-built unit-test ledgers) only**. No held-out seed has been generated. No false-insight rate, no recall number and no stability number had been computed when these changes were made; I had seen the admin overview and the distribution of worker pointer kinds on seed 0.

1. **Time-lost statistics changed from means (Welch and t) to medians** with a distribution-free order-statistic interval and a sign test against the expert median (Mann-Whitney and a bootstrap for a difference of medians). Reason: the first admin run on seed 0 showed the experts' own mean seconds lost at +13 s on one skill, entirely from the 4% heavy tail (100 to 300 s) in the generator, which would make any worker at the expert reference look slow at the 10 s floor. The reference is a median, so the sign test is the matching question ("is this person tending to be slower than the expert's median"). The person-level numbers behind the admin comparisons became per-person medians for the same reason.
2. **Persistence rule strengthened**: a week counts as holding the effect only if its median reaches half the effect floor (it was "above zero"). A unit test showed one extreme week plus two flat weeks passing.
3. **A milestone now needs a gain of at least 0.15** in the share finished unaided against the reference window. On seed 0, 38 pointers across 60 people were milestones, mostly experts whose independence never changed.
4. **Generator tuning (seed 0)**: the first draw had no visible learning because forgetting between occurrences cancelled practice (stability 30 days), so it became 200 days; planted gaps were raised (benefits cliff check 55 to 90 s lost at zero mastery, reconcile 35 to 60; analyst inspect 45 to 70, reconcile 38 to 60) because the standardised gap had come out below the 8 s floor; the Simpson group's learning rate was cut (x0.3) and its task mix shift strengthened so the raw pooled share no longer rises; experts no longer forget (a bug); the holiday user moved to a person who has data before the break.
5. **Standard mix for the cohort trend** changed from the first window's skill mix to the two windows' pooled mix after the first draw showed the first window's mix gave the easy skills almost all the weight. The Kaplan-Meier interval fell back to a Wilson interval when nobody had reached the line (a zero-width interval had appeared). The onboarding design target moved from 40 to 60 occurrences once the distribution of times to independence on seed 0 had been seen (0 of 23 reached the line by 40).

The thresholds in `insights/params.py` are a priori values (floors 10 s, 8 s, 0.05, 0.10; k = 5; windows of 3 weeks) apart from the items above; any further change is made on dev seeds only and logged here before the held-out run.

## 3. Metrics, procedures and targets

Targets are design choices, not tolerances. Each metric is reported with n, its split and a person-level (or firm-level) bootstrap interval, and is badged synthetic. A target that is missed is reported as missed.

**M1. False-insight rate on null data, worker.** `build_firm(seed, scenario="null")`: 60 people, experts and juniors from one distribution, no planted gap, no trend, no absence, `lost_s` symmetric around the expert median with the 4% heavy tail. For each person, weekly cuts at weeks 6 to 12 of the 12-week window (data truncated at the cut, `now` moved), the real `worker_run` and `select` with the history of earlier cuts. A **false insight** is a selected pointer that asserts a change or a gap that the planted truth denies: `time_loss_habit`, `habit_improved`, `relapse`, `independence_milestone`, `trade_off`. (`onboarding`, `stale_data` and `retention_due` state facts about data or timing and are not counted as claims.) Rate = person-weeks with at least one false pointer over person-weeks; interval by resampling people (1000 draws). **Target: at most 0.05** (the family-wise level). Diagnostic: the same rate with family control switched off, to show what the control does.

**M2. False-insight rate on null data, admin.** The null firm, cut at 4 weekly times per seed. A false insight is a selected `role_gap`, `cohort_trend`, `bottleneck_skill` or `unit_attention` (`onboarding_speed` compares with a design target, not with zero, and is excluded). Rate = admin-weeks with at least one over admin-weeks; interval by resampling firms. **Target: at most 0.10** (the Benjamini-Hochberg level).

**M3. Recall of planted effects, worker worlds.** One person per replicate, rows built to a plan: a time-loss habit of 15, 30 and 60 s from 5 weeks before the cut; an improvement from 40 s to 5 s with the change 24.5 days before the cut; an independence rise from about 0.4 to 0.9; a relapse (25 unaided occurrences, then 10 with a 0.4 share, no absence); retention due (a mastered skill unseen for 30 days); trade-off (faster, with an error share rising from 0.1 to 0.4). Recall = share of replicates in which the matching pointer is selected (and, separately, passes the gate before the cap). Wilson intervals. **Target: at least 0.8 at 30 s, 60 s and for the improvement, the rise, the relapse, retention and the trade-off**; 15 s is reported as the size at which the layer is expected to stay quiet (the floor is 10 s and n is 12). Also reported: the false relapse rate when a 20-day absence precedes the lower independence (**target 0**) and the false celebration rate when errors rise (**target 0**).

**M4. Recall of planted situations, admin (the synthetic firm, every seed).** Each planted situation of `Firm.truth` is checked against the candidates (passed the gate) and the selection (in the top 7): role gaps in benefits and data-analyst with the planted habits named; no expert comparison for programmer; the plateau unit flagged and the improving unit not; the improving benefits trend; the Simpson role's standardised trend improving while the raw pooled change is below it; the bottleneck skill; the automation win; the risk signals; the small team never compared; the user with no data counted in coverage and absent from every comparison. **Target: every situation recovered at the gate on at least 9 of 10 dev seeds; reported honestly on the held-out seeds.**

**M5. The "nothing stands out" audit (requested by the lead).** On the planted firm, for every person whose pointer list is empty (status `nothing_stands_out`), count how many had **no planted effect** (genuinely null) and how many had at least one (a miss), using the latent truth the generator records per person and skill (a true time loss of at least 12 s over at least 8 occurrences in the last three weeks; a true improvement of at least 12 s against the earlier window; a true rise in independence of at least 0.25). Also: effect-level recall over all planted worker effects on the firm, at the gate and in the selection, and the reasons the missed effects were suppressed (counts by reason code). **Target: report, no threshold; a miss is a finding.**

**M6. Stability.** The planted firm with 5% of each person's rows dropped at random (seeded), 10 perturbations per seed. For each person, the Jaccard similarity of the top-3 sets before and after (people with an empty set in both count as 1, and are also reported separately), and top-1 agreement; for the admin the Jaccard of the top-7 sets. Mean with a person-level interval. **Target: mean Jaccard of at least 0.8 for the worker top 3 among people with a non-empty set, and at least 0.8 for the admin top 7.**

**M7. Determinism.** The whole worker and admin pipeline run twice, and once more with rows and people in shuffled order: the JSON must be byte-identical (compared by hash). **Target: identical.**

**M8. Suppression.** The share of worker-weeks that end as "nothing stands out" (people with data), on the null firm and on the planted firm, and the share of admin candidates suppressed, by reason code.

**M9. k-anonymity.** Every table of every admin payload (roles tenure bands, units, onboarding groups, the merged role group) is scanned for a comparison cell below 5 people. **Target: 0 violations**, on every seed and on the edge scenarios below.

**M10. Edge-case matrix.** Each edge case of `docs/INSIGHTS_DESIGN.md` section 3 has a scenario, an expected output and a pass or fail computed by running the real code: a new user, no expert reference, a stale user, partial data, a role change, an absence, an outlier week, ties, conflicting metrics, Simpson, tiny cohorts, a deleted ledger, delegated and automation streams, a repeated insight, time zones, origin badges, accessibility labels, no individual ranking, the admin gate. **Target: all pass.**

## 4. Outputs

`evaluate_insights()` returns `{meta, null_worker, null_admin, recall_worker, recall_admin, nothing_stands_out, stability, determinism, suppression, k_anonymity, edge_cases, claims, limitations}`; `claims` are generated from the measured numbers (never typed). `meta` carries the seeds, n, the origin badge `synthetic` and the date.

## 5. What the evaluation does not show

* Whether workers find the pointers useful or act on them, or whether admins decide better: no human has used the layer.
* That the planted effects resemble real work: the generator was written by the same author as the selection.
* That the thresholds are right for any real firm: they are a priori values checked on synthetic data.
* The false-insight rates are for the null worlds above (stable, independent weeks); real people have autocorrelation, seasonality and shared events, which will raise them.
* A real deployment needs a lawful basis and a notice to workers; nothing here supplies one.
