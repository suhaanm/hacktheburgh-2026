# Views: what a worker sees, what an admin sees, and where everything lives

Decided by the lead on the owner's request (chat, 8 Nov 2026, about 00:50; `docs/OWNER_REQUESTS.md` items 4.1, 4.2, 4.11, 4.12, 4.17). The test for every screen: would this worker, at this moment, miss it if it were gone? If not, it is not on the screen.

## The rule

- **A worker sees only their own work.** Their own week, their own steps, their own progress, their own approvals, their own data. The one comparison allowed is against ONE experienced worker's way of doing the task, never against other learners, never an average of colleagues, never a count of people. No firm-wide insight, risk, forecast or name ever reaches a worker view, even in a closed disclosure.
- **A worker does not see system internals.** No model names, no call logs, no costs, no routing, no evidence tables, no limitations register, no hash, no run id, no ledger rows. The one trust line a worker gets: "Nothing leaves this Mac without your say. Every call Knack makes is listed under Settings, Advanced." (the list exists, closed, one click deeper, and is the only place the ledger appears for a worker).
- **An admin sees the firm in aggregate.** Bands and counts, never a worker's screen contents, never a single person's raw habits unless the worker consented. Admin has its own pages, each with a headline insight first and the numbers behind one disclosure.
- **View as** (Worker or Admin) changes what is shown; it is not a permission (it says so once, in the Account menu).

## Navigation

Worker, five rows in the sidebar (plus the account menu and the palette):

| Row | What it holds (clusters, one page, no extra navigation) |
|---|---|
| Home | The one thing that matters now (an approval, a run, or the week's insight), the task box ("What should Knack do?", type or speak), background tasks as a short list |
| Needs you | Approvals, practice runs that differed, routine proposals, prepared actions |
| Routines | Running, could automate, and the worker's background tasks and their results |
| Growth | My progress, plus "Where my time goes" as sections on the same page: my week, my steps against an experienced worker's (the old Genome), my working hours (the old Presence), my routines map (the old How work connects), my commits for programmers (the old Git) |
| Your data | What Knack remembers, what it measures, what it sent, capture and screen glances, delete |

Account menu (name and role shown): View as, Settings (live models, interruptions, coaching, Hey Knack, move aside, open at login, appearance, connections, Advanced), Set up again, Change role.

Retired as worker destinations (their content is a section above or admin-only): Today, Week, Presence, Graph, Git, Genome, Models, Evidence, Agents, Forecasts. The old routes redirect.

Admin, rows in the sidebar: Firm (overview) · Brief · Forecasts · Roles · People · Onboarding · Automation · Risk, then More: Models and cost, Evidence, Background runs. "Brief" is the firm brief and sits on the main nav, as the owner asked.

## Per screen

| Screen | Worker | Admin |
|---|---|---|
| Home | own insight, own approval, task box | n/a (admin lands on Firm) |
| Growth and its sections | own data only; baseline is one experienced worker, unnamed | n/a |
| Forecasts | not shown | headline: what to expect and what to do about it, then the numbers behind a disclosure |
| Models and cost, Evidence, call ledger | not shown (ledger one click inside Settings, Advanced) | More row; Evidence for reviewers |
| Firm, Roles, People, Onboarding, Automation, Risk, Brief | not shown | main nav |

## Data separation checklist for each screen owner

1. List every field the screen draws. 2. Mark each: own, one-expert baseline, firm aggregate, system internal. 3. A worker view draws only the first two. 4. A shared component that can draw firm data must take a `view` prop and refuse in the worker view (and a test proves it). 5. Direct URLs to admin screens in the worker view show the Admin gate sentence ("Switch to Admin to see this") and nothing else.
