# Insights layer design (REQ-9)

Owner's ask: improve the performance tracker with more insights, but highlight only the top, relevant ones, picked deterministically, covering the edge cases. Workers see a few pointers and no detailed statistics. A new Admin audience sees granular detail, can compare experts with juniors and sees a whole firm's users grouped by role and how their performance and other statistics improve over time.

Status: PROPOSED by the INSIGHTS track, 7 Nov 2026 (design first, then built). Flag `UNDERSTUDY_X_INSIGHTS` (or the master `UNDERSTUDY_X`), off by default, never on the P0 demo path. Decisions D41 to D44 (owner, 7 Nov) are applied: the admin has full per-user visibility of numbers and enums, roles are Worker and Admin, the firm in the demo is synthetic.

Files: package `services/engine/understudy_engine/insights/**`, tests `services/engine/tests/insights/**`, schema `packages/schema/insight.schema.json`, evaluation plan `evals/insights/PLAN.md`.

**One sentence that every admin text carries:** *For coaching and onboarding, not for evaluating individuals.* There is no league table, no ranking of people and no single performance score for a person, anywhere.

**Limitation that must stay in view:** per-user visibility for an employer is workplace monitoring. A real deployment needs a lawful basis (in the UK and EU, for example, a documented legitimate-interest assessment or other basis under data-protection law), a clear notice to workers before any data is shared, and possibly consultation. This build gives the worker a plain "what your admin can see" page; it does not supply the lawful basis or the notice. It also changes the earlier promise that logs stay on the device: the summaries described here are the only thing that leaves it, and only in a deployment that chooses to.

## 0. Principles

1. **Code decides, templates word it.** Candidates, gates, scores, order and caps are deterministic code. Text comes from a fixed template table filled with numbers and enums. An optional reword hook goes through the EVIDENCE layer's provenance check and can only reword, never choose, add or change a number (section 8).
2. **Silence is a valid result.** "Nothing stands out this week" is a normal answer. A weak insight is suppressed, never shown as a weak insight.
3. **Honest about what is shown.** Every insight carries its origin badge (`live`, `synthetic`, `synthetic firm`, `simulated`), its source, and (for admin) n, a split and an interval. Workers see none of those numbers.
4. **Metadata only.** The layer reads ledger-shaped rows and summaries the product already computes. Nothing it returns to an admin contains a raw row, an event, a screenshot, page or file text, memory-file text, or a row id: only counts, trend classes, intervals, per-skill independence and time-lost figures, and automation counts (D41). A test scans every admin response for the ledger row fields and ids.
5. **Learning can only quiet.** Feedback can lower an insight's loudness or hide a kind. Nothing learned raises a score or revives a suppressed candidate.
6. **No claim of expertise.** Wording is "needs less help", "takes longer than the expert's median", never "is an expert" or "will become one".

## 1. Data the layer reads (all existing, none new)

| Source | What | Used for | Freshness limit |
|---|---|---|---|
| Assist ledger (`cue.ledger` rows, assist stream only) | per occurrence: person, role, skill, hour bucket, outcome (clean, assisted, error, abandoned), `lost_s` (seconds beyond the pack's expert median: this is the genome price per occurrence), tier, `seconds_to_progress`, taught, retrieval | every independence, time-lost, relapse, retention, milestone, trend and bottleneck insight | newest row within 21 days, else the person is `stale` |
| Ledger offloaded rows (delegated, automation streams) | routine slug, minutes, outcome | automation value only. **Never** any independence-based insight | 30 days |
| Routine store and finder value | proposal value interval, shadow runs, shadow matches, rung | automation opportunity and pending proposals | 30 days |
| Hit list (`understudy_engine.hitlist`, when it exists) | top repeated, automatable actions | the worker's automation pointer reads its top row | 14 days |
| Calendar and git layers (when on) | their own flagged suggestions with interval and floor | calendar and git pointers (worker) | 14 and 21 days |
| Person profile | role, role-since time, pack revision, level (`expert` or `junior`), tenure band, unit, time zone | grouping, baseline resets, week boundaries | none, but must exist |
| Firm feeds (approval queue ages, injection pauses, false-claim events, kill events) | counts and ages | risk signals | 2 days (a down feed is itself reported) |

The ledger's `lost_s` already is "seconds lost against the expert's median for the step". So a per-skill (per-habit) decomposition of the novice-expert gap is available from rows alone: the gap on a skill is the mean `lost_s` of juniors minus experts, within that skill, and its contribution to a role's gap is that difference weighted by the expert skill mix. When the genome service has an alignment-based waterfall for a role it may be supplied (`waterfall_by_role`) and is then shown beside it; it is not required and not implemented in the first cut.

Freshness follows `docs/CONTEXT_ENGINEERING.md`: a reading carries the time its producer took it, an input older than its limit is dropped and named (`stale_sources`), a missing input is named, neither is silently defaulted. The table lives in `insights/freshness.py` with the same shape as the shared one; the keys above are additions.

## 2. The insight catalogue

`kind` is a closed enum (`packages/schema/insight.schema.json`). The candidate list is **fixed** (a tuple of generator functions per audience); which candidates are generated never depends on an effect value, only on n, freshness and flags. That is what makes the multiple-comparison family well defined (section 4.7).

Every candidate: `{id, kind, audience, subject, group, polarity, effect (value, unit), interval (lo, hi), p_value, n, n_unit, split, origin, badge, evidence_ref, recency_t, action_id, guard_metrics, impact_raw, family, slots}`. The id is a stable hash of audience, scope, kind and subject, so the same insight has the same id from week to week and `why` and `drill` can find it.

### 2.1 Worker kinds

Worker subject is a skill id (or a routine slug). Polarity: `positive`, `attention`, `tradeoff`, `note`.

| Kind | Meaning | Reliability gate (before any family control) | Action |
|---|---|---|---|
| `time_loss_habit` | on a skill you take longer than the expert's median | 3-week window, at least 6 occurrences; the **median** `lost_s` with a distribution-free interval (exact binomial order statistics) excluding 0 and a sign test against the expert median; median at least 10 s; the week's median reaches 5 s in at least 2 of the last 3 weeks that have data | `open_growth` |
| `habit_improved` | you now take less time on a skill than 4 to 6 weeks ago | last 3 weeks versus the 3 weeks ending 4 weeks ago, at least 5 occurrences each, difference of medians with a seeded bootstrap interval excluding 0 and a Mann-Whitney test, drop at least 8 s, persists in 2 of 3 weeks | none (celebration) |
| `independence_milestone` | you needed less help on a skill: the share finished without help over your last 20 occurrences, against your first 20 | 40 occurrences (two blocks that can be compared fairly), a gain of at least 0.10, and at the family-adjusted multiplier the Newcombe interval of the gain excludes 0 and the Wilson lower bound of the last 20 has newly reached 0.5, 0.65 or 0.8. Stable independence (an expert) is never a milestone | none |
| `retention_due` | a skill you had mastered has not come up for a while, so a short practice is due | at least 8 occurrences of the skill, earlier independence at least 0.7, 14 to 120 days since the last occurrence (time-aware: this is the pointer a break produces, never a relapse) | `open_practice` |
| `relapse` | a previously mastered skill needed help more often | baseline: the 15 occurrences before the last 10 had independence at least 0.8; recent: at least 6 of the last 10 (within 28 days, after the absence grace, section 3.5); drop at least 0.25, Newcombe interval excluding 0 | `open_growth` |
| `automation_opportunity` | repeated work worth handing over | finder value lower bound at least 0.5 hours over the horizon, support at least 3, shadow runs and matches shown when they exist; or the hit list's top row | `open_routines` |
| `calendar_pointer`, `git_pointer` | the calendar or git layer's own flagged suggestion | the layer's interval excludes 0 in the bad direction and the delta is at least its floor, n at least its minimum, only when that layer is on | its own |
| `onboarding` | too little history to say anything: how many more steps are needed | fewer than 10 assist occurrences in total, or role or pack changed recently (section 3.4) | none |
| `trade_off` | an improvement that comes with a worse guard metric (section 4.2) | the improvement passed its own gate | `open_growth` |
| `stale_data` | no recent work seen | newest row older than the limit | none |

### 2.2 Admin kinds

Admin subject is a role, a unit, a role and skill, or `firm`. **No admin insight has a person as its subject.** Per-user rows appear only in the firm view and in a drill-down, in id order.

| Kind | Meaning | Reliability gate | Notes |
|---|---|---|---|
| `role_gap` | the gap between experts and juniors in a role, and the habits that explain most of it | at least 5 experts and 5 juniors with data (comparison table rule), within-skill comparison standardised to the expert skill mix, gap at least 10 s per occurrence, interval from a person-level bootstrap excluding 0 | top two habits go in `split`; the whole table is the drill-down |
| `cohort_trend` | independence rising or falling in a role | panel of people with at least 8 occurrences in both windows (within-person change, so joiners do not distort it), at least 5 people, 3-week smoothing, change at least 0.05, interval excluding 0 | `cannot tell yet` is shown in the firm table, never selected as an insight |
| `bottleneck_skill` | the skill in a role with the highest assisted share | assisted share minus the role's mean of the other skills, person-level interval excluding 0 and at least 0.10 | one per role at most |
| `onboarding_speed` | how many occurrences juniors need to reach independence, against a target | at least 5 followed juniors; Kaplan-Meier with censoring; share reached by the target with a Wilson interval that excludes the target | the target is a design target the firm sets (default 60% within 40 occurrences, an assumption) |
| `unit_attention` | a unit where juniors need more help than the same role elsewhere | unit of at least 5 people, task-mix standardised, difference at least 0.10 with interval excluding 0 | framed as "where onboarding support may help" |
| `automation_value` | work handled by approved routines, with measured shadow matches | at least 3 approved routines with shadow Wilson lower bound at least 0.8, at least 20 completed runs | positive; becomes a trade-off if a false-claim event is in the window |
| `automation_pending` | proposals not yet decided that would pay | at least 3 proposals with value lower bound at least 0.5 h | informational: only the worker can approve |
| `risk_signal` | approval backlog age, injection pauses, false-claim events, kill events | any count above 0 (backlog: oldest above 24 h) | reserved slot (section 4.5); never decays |
| `coverage` | how many people have enough data to say anything | emitted when fewer than 60% have enough data; the overview header always shows the coverage | explains weak output |
| `data_stale` | a feed or a group is stale | any feed past its limit | stale marker, not silence |

## 3. Edge cases, each decided

1. **New user, too few occurrences** (fewer than 10 assist occurrences in total). Only the `onboarding` pointer is produced, with how many steps are still needed. No comparison of any kind is made. A skill with fewer than 6 occurrences in the window produces nothing for that skill (reason `not_enough_data`); other skills are unaffected.
2. **No expert reference.** Rows without `lost_s` (more than half of a skill's window) give no time comparison for that person and skill (`no_expert_reference`); independence-based insights, which reference only the person's own history, still run. For a role with fewer than 5 experts in the data, `role_gap` is not produced and the roles table says why in words. `cohort_trend`, `bottleneck_skill` and `onboarding_speed` need no experts.
3. **Missing, stale or partial data.** A stale person gets the `stale_data` pointer, not silence and not old insights. A stale feed gives a `data_stale` card. Partial data (some skills missing, rows with no `lost_s`) is computed for what exists and the response lists `stale_sources` and a `partial` flag. A risk feed that is down produces `data_stale` for risk: silence about risk is never the output of a broken feed.
4. **Role or pack change.** Baselines reset: only rows with the person's current role and a time at or after `role_since_t` (and the current pack revision) are used. The person gets one `onboarding` pointer with reason `role_changed` ("comparisons start fresh"), and in admin views is counted in the new role's onboarding group. Rows from the old role are never mixed into the new role's trend.
5. **Absence or holiday gap, time-aware.** A gap of 10 days or more with no occurrence at all is an absence. After an absence, the first 3 occurrences of each skill are an absence grace: excluded from `relapse`, `time_loss_habit` and `habit_improved` evidence (settling back in is not a habit). A skill whose independence fell only inside the grace gives `retention_due`, never `relapse`. Weekly series skip weeks with no occurrences; missing weeks are missing, not zero, so a holiday cannot look like decline in a cohort trend.
6. **Outlier weeks and regression to the mean.** Windows are 3 weeks pooled (**3-week smoothing, stated in every drill-down**). Time-lost figures are medians (the expert reference is a median, and task times have a heavy tail), and `lost_s` is clipped to [-120, 600] s. Time-based insights also need the week's median to reach half the effect floor in at least 2 of the last 3 weeks that have data, so one extreme week cannot create an insight. The reference window for an improvement is a separate earlier window, never the window the candidate was picked from.
7. **Ties.** Score ties break by insight id ascending. Floors are `>=`, interval and test comparisons are strict, documented per gate. Scores are rounded to 9 decimals before ordering so platforms agree.
8. **Conflicting metrics.** An improvement is never shown while a guard metric worsened; it is shown as a `trade_off` ("faster, but errors rose") (section 4.2).
9. **Simpson's paradox.** Comparisons are within skill (task type) and standardised: a role-level gap uses the expert skill mix as fixed weights; a cohort trend is a within-person panel change per skill combined with the pooled mix of the two windows as fixed weights; unit comparisons use the role's skill mix. A raw pooled rate is never compared across groups or over time. The drill-down names the standard used. The synthetic firm plants a Simpson trap (the data-analyst juniors' task mix shifts toward the harder skills while every skill improves, so the raw pooled change understates the improvement) and the evaluation checks that the standardised change is above the raw one.
10. **Tiny cohorts.** Role comparison tables, cohort trends, unit comparisons, tenure-band and "Other" cells need at least 5 people; a group below 5 is merged into "Other" (never shown alone in a comparison table). If "Other" is itself below 5 it is merged into the smallest remaining cell, or the table is suppressed with a reason. A single place enforces it (`AdminView.cohort`), so no admin comparison can be computed on fewer than 5 by accident. Per-user rows are allowed in the firm view (D41), as numbers and enums only.
11. **Sharing.** There is no opt-in toggle (D41). The worker's "what your admin can see" page is read-only and built by the same function as the admin's per-user row, so it shows exactly what an admin sees. Revoked sharing becomes the "user with no data" data-quality case: the person has no rows, appears as `no_data`, is counted in coverage, and no insight uses them. A worker deleting their ledger (their right, unchanged) removes their data from every admin view at once, because nothing derived is cached across calls without the row count in its key.
12. **Delegated and automation streams** are never read by an independence-based insight: those insights call `cue.score.assist_only` first, and a test feeds ledgers full of delegated and automation rows and expects nothing.
13. **The same insight repeated.** Novelty decays by half for each time the same insight key was shown in the last 28 days, and the candidate is suppressed (`repeat_recently`) at novelty 0.25 or below, unless it is materially changed: effect changed by at least 25% relative, sign flipped, or a new milestone level.
14. **Time zones.** The worker's week runs Monday 00:00 to Sunday in the person's own IANA zone (UTC if missing or invalid); ledger hour buckets are UTC and are assigned by their start time (at most 30 minutes of error in half-hour zones, stated). Admin windows are UTC ISO weeks, and say so.
15. **Deleted ledgers.** Weekly pins record the row count and newest hour of the evidence; fewer rows than pinned means the ledger was deleted or reset and the pin is dropped and recomputed. Feedback for a person is removed with their ledger.
16. **Origin badges.** Every candidate has `origin` (`real`, `synthetic`, `mixed`) and a `badge`; the text names the source and says "synthetic data" or "synthetic firm" when it applies.
17. **Accessibility.** Polarity is a word (`polarity_label`: "Going well", "Worth a look", "Trade-off", "Note"), a glyph name from a closed set and an `a11y_label`; colour is never the only carrier.

## 4. Selection (deterministic and stable)

Input: candidates from the fixed list, the time `now`, the person or firm snapshot, history (what was shown, feedback), the `Params`. Pure function. No clock, no randomness (any resampling is seeded from the ids).

### 4.1 Reliability gate
A candidate must (a) have n at least its minimum; (b) be fresh (`recency_t` within the source's limit); (c) for an effect: an interval that excludes 0 in the stated direction, a size at least its floor, and, after family control (4.7), a significant test; (d) for a state: its threshold. Failing candidates are **suppressed with a fixed reason code**, never shown weakly.

### 4.2 Guard metrics
Improvement kinds (`habit_improved`, `cohort_trend` rising, `onboarding_speed` on track, `automation_value`) carry guards: error share, abandoned share, median seconds to progress after a cue, rework share (when the source has it), and, firm-wide, false-claim events. A share guard (errors, unfinished cases) is `worse` when it rose by at least 0.10, by at least two cases, and credibly: the one-sided two-proportion p of the rise is at most 0.25, so a rise inside the noise neither turns a celebration into a trade-off nor hides one. A seconds guard (time to progress after a cue) is worse at 25% and 3 s more with at least 4 cases each side. If any guard is worse, the polarity becomes `tradeoff`, the kind becomes `trade_off`, and the template names both: "faster on X, but errors rose from 3 to 7 of 20".

### 4.3 Score
`score = impact × actionability × novelty × recency`, each in (0, 1].
* **impact** = `1 - exp(-impact_raw / scale)`, a saturating map so scores do not depend on the other candidates (stable). `impact_raw` is person-minutes per week at stake: seconds effects use `|effect_s| × occurrences per week / 60` (times people affected for admin); proportion effects use `|Δshare| × occurrences per week × assist cost (45 s, an assumption in `Params`, stated as a ranking proxy and not a measured saving)`; risk signals use fixed constants. Scale: worker 15, admin 120 (tuned on dev seeds only).
* **actionability**: 1.0 with a template action, 0.7 without.
* **novelty**: 0.5 to the power of the number of times the same key was shown in 28 days; reset to 1 on a material change. Feedback `not_useful` sets it to 0 for 28 days.
* **recency**: `exp(-age_days / 21)` where age is the age of the newest evidence.

### 4.4 Diversity
At most one candidate per `(subject, kind)` (the highest score wins; the rest are `same_kind_lower_score`). For workers, stricter: at most one pointer per subject and sort (`same_subject_lower_score`): one about a skill that is going well and one about a skill that is not may both be shown ("faster than a month ago, and still slower than the expert" is two true things), but two of the same sort are one message told twice. For admin at most 3 per role or group. **At least one positive insight** is included when one passes the gate: if none of the top picks is positive, the best positive replaces the lowest non-reserved pick.

### 4.5 Caps
Worker: at most 3 pointers per week. The week's picks are pinned on the first call of the week (so repeated calls are identical and nothing reshuffles mid-week) and invalidated only by a deleted ledger (3.15). If nothing passes: `nothing_stands_out`. Admin: at most 7; **one slot is reserved** for the best `risk_signal` or `data_stale` card when one passes the gate (a backlog or a broken feed is never pushed out by a nicer story); the rest by score.

### 4.6 Order
Score descending, ties by id ascending. Same inputs give the same output, byte for byte (tested).

### 4.7 Multiple comparisons
The family is the set of admissible effect tests for the audience and scope in this run (n, freshness and expert reference satisfied; effect values play no part in what is admissible).
* **Worker: Bonferroni, family-wise error 0.05 over the person's admissible tests** (typically 4 to 12). The level is `0.05 / m`, applied through the interval multiplier (the same adjusted z is used for the Wilson bound of a milestone). Why: a worker gets a few pointers a week and a false one costs trust; the family is small so Bonferroni's cost in power is small; it controls the chance of any false pointer per worker-week at 5% under the global null.
* **Admin: Benjamini-Hochberg at q = 0.10 over the admissible tests** (roles, units, skills, kinds: 15 to 40). Why: the admin sees up to 7 insights and several real effects are expected, so false discoveries among the selected is the right quantity, and BH is less conservative than Bonferroni at that size. Under the global null BH gives a 10% chance of any false insight per admin-week before the floors and the interval rule remove more of them.
* The displayed interval is the nominal 95%; the gate uses the adjusted decision. p-values: a sign test against the expert median and a Mann-Whitney test for worker time (medians, distribution-free intervals), Welch and one-sample t on person-level values for admin, a two-proportion z with Newcombe intervals for shares. The false-insight rate per worker-week and per admin-week is **measured** on synthetic null data (`evals/insights/PLAN.md`) and reported with person-level bootstrap intervals, not assumed.

### 4.8 Suppression reasons (closed enum)
`not_enough_data`, `no_expert_reference`, `stale`, `interval_spans_zero`, `below_effect_floor`, `not_significant_after_family_control`, `group_too_small`, `short_absence`, `role_changed`, `onboarding`, `repeat_recently`, `same_kind_lower_score`, `same_subject_lower_score`, `over_cap`, `hidden_by_feedback`, `guard_metric_worse` (converted to a trade-off, not hidden), plus `selected_top_score`, `selected_positive_slot`, `selected_reserved_risk`. Each has a fixed plain sentence for `why`.

## 5. Privacy model (D41)

* Workers: nothing about another person. A worker pointer carries no number beyond one plain count or duration in the sentence; no interval, n, p-value, or distribution; the worker route has a separate response type that has no such fields (a test asserts the key set).
* Admin: role `admin` only, enforced by `x-understudy-role: admin` **accepted only with the per-boot token** (`x-understudy-token`, the same token the release routes use); an admin header without a valid token is refused (403 `admin_token_required`), an explicit non-worker actor (agent, model, system, tool) is refused even with the token (403 `admin_actor_refused`; no actor header is allowed, the dashboard's reads send none), and a worker never receives admin-granularity data from any route. `GET /insights/sharing` (which holds the exact per-user row) is likewise refused to a non-worker actor (403 `worker_actor_required`). Auth0 roles replace the header later.
* Per-user rows in the firm view: numbers and enums only (occurrence counts, independence share and Wilson lower bound over the last 20, trend class, per-skill independence and time-lost with intervals, automation counts, data status, last-seen age in whole days). Order is by person id; there is no sort-by-performance, no rank field, no composite score.
* Comparison tables (role, cohort, unit, tenure band): at least 5 people per cell, small cells merged into "Other".
* Never in any admin response: ledger rows or row ids, hour buckets, event data, screenshots, text from pages or files, memory-file text, names.
* The worker's transparency page (`GET /insights/sharing`) shows exactly the admin's per-user row for that worker, what is visible, what never is, since when, and to whom (the Admin role). It is read-only; there is no toggle. A worker can still delete their own ledger.
* Feedback is stored locally; it never reaches a model. The package imports no model client, no network, no process (the static guard; `insights` is added to the guarded pure-compute directories).

## 6. Synthetic firm (`insights/firm.py`)

`build_firm(seed, n_users=60, weeks=12)`: deterministic, badge `synthetic firm`. About 60 users across three role packs: benefits-processor (deep, about 30), data-analyst (about 18) and programmer (about 12), with tenure bands (new, early, established), experts and juniors, units, skill trajectories, assist ledgers (from my own light generator that follows `cue.simlearn`'s learner dynamics and uses its presets and constants when importable, and v1 persona speeds as the fallback; `personas_v2.generate_cohort` roles supply skill and deficit ids) and offloaded rows. Everything the dashboard shows is computed from those rows; nothing is typed in. A `truth` block records the planted situations for the evaluation only; no product code reads it:

* a role whose juniors improve (benefits unit A), and one that plateaus (benefits unit B);
* a bottleneck skill (benefits `check-the-cliff`); a real role gap concentrated in two habits;
* a Simpson trap (data-analyst: skill mix shifts toward the harder skill while each skill improves);
* a role with fewer than 5 experts (programmer: `no_expert_reference`) and a small team below the privacy threshold (4 people);
* an automation that saves hours with measured shadow matches, and pending proposals;
* a user with no data (a deleted ledger), a stale user, a user who changed role mid-window, a user back from a 3-week holiday, a new joiner;
* risk feed: one approval 3 days old, two injection pauses, no false claims, one kill event.

## 7. API (behind the flag; JSON errors `{"error": {"code", "message"}}`; writes through the shared guard)

Envelope `{"meta": {origin, badge, n, n_unit, interval_level, note, generated_at, as_of, source}, "data": ...}`. `source` is `firm` (synthetic firm; default when `UNDERSTUDY_MOCK=1` or `?source=firm`) or `local` (this device's own ledger, one person; admin routes then answer with coverage only, since no firm data exists here).

| Route | Role | Returns |
|---|---|---|
| `GET /insights/worker?person=` | worker | up to 3 pointers (`id, kind, polarity, polarity_label, glyph, title, text, source, badge, action, details_available, a11y_label`), `status`, `message`, `week`, `stale_sources`. No statistics |
| `GET /insights/admin/overview` | admin | up to 7 cards with effect, interval, n, split, drill link; coverage; role comparison summary; statement |
| `GET /insights/admin/roles` | admin | per role: experts versus juniors with intervals, per-habit decomposition, tenure bands (small cells merged), reasons when not comparable |
| `GET /insights/admin/firm` | admin | users grouped by role: group counts, trend classes, aggregate intervals above the threshold, and per-user rows (numbers and enums, id order) |
| `GET /insights/admin/onboarding` | admin | time to independence by role: Kaplan-Meier curve with intervals and n, share reached by the target, target line labelled a design target |
| `GET /insights/admin/drill?insight=` | admin | granular tables and series for one insight, the method, the parameters and the standard used |
| `GET /insights/why?insight=` | either (own audience) | selected or suppressed, fixed reason code and sentence; admin also gets the score parts and the family-control summary |
| `POST /insights/feedback` | either | `useful`, `not_useful`, `hide_kind`, `show_kind`: only makes things quieter (`useful` has no ranking effect; `show_kind` only reverses a hide the same person made) |
| `GET /insights/sharing?person=` | worker | read-only: what an admin can see, never sees, since when, to whom, and the exact row |

The admin role also accepts `?source=`. Route handlers check the flag first (404 `extension_off`). One line for ENGINE-DATA: `"insights": "insights.routes"` in `EXTENSIONS` in `api/flags.py`.

## 8. Wording

Fixed templates in `insights/texts.py`, filled only with numbers and enums. Lint (a test over every template and sample): plain and short (worker title at most 8 words, body at most 30; admin body at most 45), names its source from a fixed set, names the badge when synthetic, no exclamation marks, no emoji, none of the banned phrases ("just", "simply", "urgent", "hurry", "obviously", "unfortunately", "great job", "poor", "worst", "underperform", "league", "rank", guilt words), no "%" or the words "interval", "confidence", "significant", "p-value" in worker texts, sentence case, a full stop, and every admin text ends with the coaching sentence. Optional reword: `Rewriter(text_id, slots, text) -> str | None` is a hook the service calls only when the evidence layer supplies one; the result is accepted only if it keeps exactly the digits of the template and passes the evidence provenance check, else the template stands. The layer never calls a model itself.

## 9. Evaluation (plan in `evals/insights/PLAN.md`, pre-registered before any held-out run)

Planted-truth worlds on synthetic data: recall of each planted effect; false-insight rate on null data per worker-week and per admin-week with person-level bootstrap intervals; stability (same input same output; small perturbations versus the top-3); an edge-case matrix (each case, its test, its expected output); the suppression rate; determinism (byte-identical output). Thresholds are tuned on dev seeds only. It does **not** show that workers find the pointers useful, that admins decide better, or that any of this is acceptable to real workers; the live check with the four teammates is not run. `evaluate_insights(fast=True)` is exported for the harness.

## 10. Not covered

Which window an insight appears in (the dashboard's), the admin UI, the repeat list itself (HITLIST owns it; the worker pointer reads its top row), real Auth0 roles, a server that aggregates real workers' summaries (the demo's firm is synthetic and the local source has one person), and any lawful-basis or notice machinery for a real deployment.

## 11. Built, measured and amended (7 Nov 2026)

* The routes, shapes and tests are as built: `GET /insights/worker`, `/insights/admin/{overview,roles,firm,onboarding,drill}`, `/insights/why`, `POST /insights/feedback`, `GET /insights/sharing` (read-only; a POST is 405). The JSON shapes were agreed with ADMIN-UI and are in `evals/insights/samples/`. `GET /insights/admin/onboarding` is a Kaplan-Meier time to independence (the share of the last 20 occurrences finished without help reaches the design target 0.8) with censoring, plus an independence learning curve in blocks of 10; the target of 60 occurrences and 60% of new juniors is a design target the firm sets, not a measured standard.
* Changes made after looking at dev data are logged in `evals/insights/PLAN.md` (section 2 and the dated amendment); the measured numbers are in the evaluation output (`evaluate_insights`), never typed here.
* The evaluation's held-out seeds (100 to 139) refuse to run unless `UNDERSTUDY_INSIGHTS_HELDOUT=1`, so they are run once, deliberately.
* Not built: an alignment-based genome waterfall as the habit source (the ledger's per-skill `lost_s` is used); calendar and git pointers only when those layers register a pointer source; the optional reword hook is wired (`texts.accept_reword`) but no rewriter is registered.
