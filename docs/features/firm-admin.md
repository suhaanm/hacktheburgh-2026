# Firm, Roles and Onboarding for admins

> An admin sees numbers and trends by role and person, for coaching and onboarding, never as a league table.

**Capability:** Insights and admin · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Navigation note (on main since 02:05 UTC).** The lead's views rule (`docs/knack-ux/views.md`) is implemented: a worker has five sidebar rows (Home, Needs you, Routines, Growth, Your data); Growth is one page with the sections My progress, Where my time goes, My steps, How my routines connect and My commits; the Admin view has Firm, Brief, Forecasts, Roles, People, Onboarding, Automation and Risk, then More: Models and cost, Evidence, Background runs. Old addresses redirect (`apps/dashboard/src/routeRedirects.ts`). The final list is `apps/dashboard/src/components/home/navModel.ts`. Admin main navigation under the rule: Firm, Brief, Forecasts, Roles, People, Onboarding, Automation, Risk; More: Models and cost, Evidence, Background runs. Owner request 4.4 asks for the Admin view to be filled with made-up people for several users with no tag anywhere saying so; that sits against the honesty rule that synthetic data is labelled (see D57 and 'Things we do not claim'), so say aloud in any video that the firm is made up. Request 4.4 is answered by D67 (about 03:35 GMT): the blank Admin view was a data and wiring gap, and the Admin screens now read a built firm of 32 people (12 benefits processors, 10 data analysts, 10 programmers; five experienced and five or more junior in each role) in three mixed teams over 12 weeks, with nine routines and three open approvals; no tag says how the data was made (D57), so say aloud in any video that the people are made up.

This page covers Admin views: Firm, Roles, Onboarding, Monday note, firm brief and prediction scorecard.

## Admin views: Firm, Roles, Onboarding

**Status:** built (UI merged to main; the firm is synthetic; owner request 4.4 and decision D67 (about 03:35 GMT): the blank live Admin view was a data and wiring gap (the engine read this device's own history, one worker, so the minimum group of 5 withheld every comparison); the lead records that the Admin screens now read a built firm of 32 people (12 benefits processors, 10 data analysts, 10 programmers; five experienced and five or more junior in each role) in three mixed teams over 12 weeks, with nine routines and three open approvals; D43 (about 60 users, a badge) is superseded for the Admin screens and the 60-person firm stays the evaluation fixture and the mock-mode fallback; not seen by the author) · **Page:** `docs/features/firm-admin.md` · **Targets:** G-Research, HRT

### What it does

A second audience. The Admin view shows where the firm loses time, compares experts and juniors by role on one scale, and shows how fast people reach independence. Names are made up and the firm is synthetic.

### How it works

Roles are Worker and Admin; the admin switch lives in the account menu and is remembered. An admin sees summaries of numbers and enums only (counts, trend classes, intervals, per-skill independence and time-lost, automation counts): never raw events, screenshots, page or file text, memory-file contents or assist-ledger rows beyond counts. Group comparisons need at least 5 people. There is no ranking of individuals and no single performance score. Every admin text carries the line 'For coaching and onboarding, not for evaluating individuals.' A worker has a plain 'what your admin can see' page in Your data. The Firm screen shows at most three rows by default, then Show all; Roles shows one row per role as a dot-and-whisker strip; Onboarding shows one small chart per role with the median step to the target.

**What is different.** The admin sees numbers and enums only, never a ranking or a single score, groups under 5 are never compared, and the worker has a page that shows exactly what the admin can see.

### Where to see it

Account menu, View as Admin; the Admin sidebar rows Firm, Brief, Forecasts, Roles, People, Onboarding, Automation and Risk; then More: Models and cost, Evidence, Background runs.

### Demo moment

Switch to Admin (the Admin screens read the built firm of 32 people, D67; check on the build you film that people are listed): Firm lists three rows with n and interval; open Roles: experts and juniors on a shared 0 to 100% scale, one row per role (the 60-person evaluation fixture shows, for example, benefits-processor experts at 94% and juniors at 63%, n = 7 and 22; the 32-person firm has its own n); open Onboarding ('Half reach the target by step 82'); note that since D57 the Firm head draws no origin tag for generated data, so say aloud that the names are made up and the firm is made for this build.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| No group under 5 people is ever compared: 0 k-anonymity violations across 11 firms; a person's deleted ledger disappears from every comparison at once | synthetic firms | `evals/insights/results/heldout.json` |
| Words above the fold: Firm 206 to 80; Roles 313 to 35 (the spec text says 36) | design measurement of a prototype | `docs/knack-ux/after/after-measurements.json; docs/KNACK_UX.md (section 2)` |

### Honest limit

Full per-user visibility for the admin was the owner's choice (D41); the lead recommended aggregates plus opt-in individuals. Per-user visibility is workplace monitoring: a real deployment needs a lawful basis (in the UK and EU, for example a documented legitimate-interest assessment), a clear notice to workers before any data is shared, and possibly consultation. This build supplies the worker's 'what your admin can see' page but not the lawful basis or the notice. It also changes the earlier promise that logs never leave the device: these summaries are the only thing that would, and only if a deployment chooses to. The firm the Admin screens read is a built firm of 32 people (12 benefits processors, 10 data analysts, 10 programmers; five experienced and five or more junior in each role) in three mixed teams over 12 weeks, with nine routines and three open approvals, kept in a folder that the Worker view never reads, so a worker's own export and delete never touch it (services/engine/understudy_engine/insights/firmstore.py; D67); worker routes never serve it outside mock mode and `/hitlist/firm` is admin-gated. The 60-person firm remains the evaluation fixture behind the k-anonymity result.

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

Admin sidebar, Brief (a print view) and Forecasts; the command palette has Print the firm brief (and Copy my Monday note once it lands).

### Demo moment

Press Command-K, choose Print the firm brief; then open Forecasts in the Admin sidebar to show the scorecard.

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
