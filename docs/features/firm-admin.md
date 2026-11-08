# Firm, Roles and Onboarding for admins

> An admin sees numbers and trends by role and person, for coaching and onboarding, never as a league table.

**Capability:** Insights and admin · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Admin views: Firm, Roles, Onboarding, Monday note, firm brief and prediction scorecard.

## Admin views: Firm, Roles, Onboarding

**Status:** built (UI merged to main; the firm is synthetic) · **Page:** `docs/features/firm-admin.md` · **Targets:** G-Research, HRT

### What it does

A second audience. The Admin view shows where the firm loses time, compares experts and juniors by role on one scale, and shows how fast people reach independence. Names are made up and the firm is synthetic.

### How it works

Roles are Worker and Admin; the admin switch lives in the account menu and is remembered. An admin sees summaries of numbers and enums only (counts, trend classes, intervals, per-skill independence and time-lost, automation counts): never raw events, screenshots, page or file text, memory-file contents or assist-ledger rows beyond counts. Group comparisons need at least 5 people. There is no ranking of individuals and no single performance score. Every admin text carries the line 'For coaching and onboarding, not for evaluating individuals.' A worker has a plain 'what your admin can see' page in Your data. The Firm screen shows at most three rows by default, then Show all; Roles shows one row per role as a dot-and-whisker strip; Onboarding shows one small chart per role with the median step to the target.

**What is different.** The admin sees numbers and enums only, never a ranking or a single score, groups under 5 are never compared, and the worker has a page that shows exactly what the admin can see.

### Where to see it

Account menu, View as Admin; sidebar Firm, Roles, Onboarding; More, Firm rows (People, Automation, Risk and coverage, Forecasts, Firm brief).

### Demo moment

Switch to Admin: Firm lists three rows with n and interval; open Roles: experts and juniors on a shared 0 to 100% scale, one row per role (the seeded firm shows, for example, benefits-processor experts at 94% and juniors at 63%, n = 7 and 22, synthetic); open Onboarding ('Half reach the target by step 82'); show the provenance badge (its Admin wording is being changed by D57) and say the names are made up and the firm is made for this build.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| No group under 5 people is ever compared: 0 k-anonymity violations across 11 firms; a person's deleted ledger disappears from every comparison at once | synthetic firms | `evals/insights/results/heldout.json` |
| Words above the fold: Firm 206 to 80; Roles 313 to 35 (the spec text says 36) | design measurement of a prototype | `docs/knack-ux/after/after-measurements.json; docs/KNACK_UX.md (section 2)` |

### Honest limit

Full per-user visibility for the admin was the owner's choice (D41); the lead recommended aggregates plus opt-in individuals. Per-user visibility is workplace monitoring: a real deployment needs a lawful basis (in the UK and EU, for example a documented legitimate-interest assessment), a clear notice to workers before any data is shared, and possibly consultation. This build supplies the worker's 'what your admin can see' page but not the lawful basis or the notice. It also changes the earlier promise that logs never leave the device: these summaries are the only thing that would, and only if a deployment chooses to.

### Hackathon target

- **G-Research (make the invisible visible)**: the firm's hidden bottlenecks made visible
- **HRT (best use of data for predictions and decisions)**: comparisons with a minimum group size and intervals

## Monday note, firm brief and prediction scorecard

**Status:** built · **Page:** `docs/features/firm-admin.md` · **Targets:** HRT

### What it does

Extras for the admin: a short Monday note, a one-page firm brief that prints, and the stuck-prediction scorecard.

### How it works

The Monday note is a few plain sentences built from the same deterministic insights (the engine sends ready text when it has it; otherwise it is composed from the pointers). The spec puts 'Copy my Monday note' in the command palette; that row was not on main when this was written. The firm brief is a print view of the top rows. The scorecard is the Forecasts screen (reliability diagram and baselines) read from the evaluation report.

**What is different.** Nothing new is claimed: it reuses the insights engine and the evaluation report.

### Where to see it

Command palette, Print the firm brief (and Copy my Monday note once it lands); More, Forecasts.

### Demo moment

Press Command-K, choose Print the firm brief; then open More, Forecasts to show the scorecard.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| No separate measurement: these reuse the insights engine and the report | see the home-insights and stuck-model pages | `docs/DECISIONS.md (D44)` |

### Honest limit

Same synthetic firm and the same caveats as the insights engine.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a prediction scorecard beside every forecast

## 30-second spoken script

> The admin view is a second audience. It shows where the firm loses time, compares experts and juniors by role on one scale, and shows how fast new people reach independence. It shows numbers and trends, never a league table, and every admin screen says it is for coaching and onboarding, not for evaluating individuals. The names in our demo are made up and the firm is synthetic. A real deployment would need a lawful basis and notice to workers.

## Slide bullets

- Admin: Firm, Roles, Onboarding; names made up; synthetic firm.
- Numbers and enums only; no raw events, screenshots or text.
- No group under 5 compared; no ranking, no single score.
- Worker gets a plain 'what your admin can see' page.
- Real use needs a lawful basis and notice to workers.

## Sources

- `docs/DECISIONS.md (D41 to D44)`
- `docs/INSIGHTS_DESIGN.md`
- `docs/knack-ux/05-admin-firm.md`
- `docs/KNACK_UX.md (section 3)`
- `evals/insights/results/heldout.json`
- `docs/knack-ux/after/after-measurements.json`

## Related pages

`home-insights.md`, `your-data.md`, `role-packs.md`
