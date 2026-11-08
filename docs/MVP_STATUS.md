# MVP status for the owner

First written 7 Nov 2026, about 21:20 GMT, for the 22:00 check; brought up to date on 8 Nov 2026, about 03:00 GMT, from the repository (the feature-docs track). Everything below is on example data and sandbox sites we wrote, in mock mode, except where a row says a real model or the owner's own Claude command was used. Nothing here was tested with people.

## What works now

On `main`, built and tested by their tracks. What the lead has seen end to end is in `docs/FEATURE_CATALOGUE.md` (status words: verified, built, building); the author of this update ran nothing.

- **One app.** Knack: a window, a menu-bar item and a corner pill. First run asks a role, three consent cards (capture, screen glances, voice) and a "Check it works" screen; every screen has a Skip. A worker has five destinations (Home, Needs you, Routines, Growth, Your data); Growth is one page with five sections; an Admin view has Firm, Brief, Forecasts, Roles, People, Onboarding, Automation and Risk, then Models and cost, Evidence and Background runs. Old addresses redirect. The earlier sweep of 28 screens with no page errors (`node apps/dashboard/scripts/live-sweep.mjs`) predates this navigation and should be re-run.
- **Benefits agent in mock mode.** A run on the sandbox calculators ends with an item in the approval queue and 0 false claims. The irreversible step waits for a click.
- **Home task box and Claude background agents (D63, D64).** On main, tested with a fake command and two small real runs of the owner's own Claude command (about US$0.125 in all, both approved in chat); no real task has been run. Full computer access is the owner's choice; the deny rules were verified once for file tools only.
- **Connections, role depth, Hey Knack, the admin firm, the HRT evidence blocks.** On main. Nothing real was connected; Hey Knack has not been run with a microphone; the admin firm of 32 made-up people is seeded by `python -m understudy_engine.demo seed-firm` and owner request 4.4 stays open until that has run on the live data.
- **Tests.** The report's static count is 8,126 test functions (`evals/report.facts.json`, 8 Nov 02:22 GMT; parametrised cases are not expanded). The last full pass counts I have are from 7 Nov about 20:57 (engine and packs 3,889 passed; agent service 1,726; dashboard 541; desktop 2,684; the reviewer's safety reproducers 183 of 183) and are out of date: a final `make test` is owed.
- **`make eval`** was regenerated 8 Nov 02:22 GMT (37 sections in the evidence map: 35 with numbers, 2 not run, 0 failed). The lead's next full run replaces it; re-read numbers from the file.

Built and tested by its track, not seen end to end by the lead on a real desktop: the on-screen ring and Cue panel, the attention router on the desktop, the Chrome extension capture, the desktop app, Hey Knack. They need you at the machine.

## Results you should know before you test

Numbers come from generated data, language-model participants, or a language model on our sandbox. Details in the README and `docs/FEATURE_CATALOGUE.md`; the HRT numbers are in `docs/HRT_BRIEF.md`.

| Area | Result |
|---|---|
| Computer use, Gemini, held-out round 2 (`evals/agentic/PLAN_ROUND2.md`, D65) | **Clean n = 20: 18 completed with correct inputs (Wilson 0.70 to 0.97). The bar registered before the run, a lower bound of at least 0.80, was not met.** The 2 misses paused, 0 false claims, nothing submitted. Injected n = 20: all paused at step 0 (text-only evidence, not proof the gate resists hostile pages). One run per household of a non-deterministic model on our sandbox, the case note at tier 2. |
| Computer use, OpenAI, held-out (gate 35e964049fd0) | Clean n = 4: 1 completed (descriptive, Wilson about [0.05, 0.70]); 2 runs had wrong calculator B inputs that only the evaluation's recomputation caught; 1 run paused because the goal-check call could not complete. A different configuration from round 2, not pooled with it. |
| Stuck model and work genome | Strong on their own generator; the edge falls to a few thousandths of a nat (stuck) and precision 48 to 71% (genome) on three harder generated worlds. Scored forward in time on new seeds (HRT): better than the plain baselines where fitted, worse than the best plain predictor in three shifted worlds; the guard flagged 8 of 8 in each. |
| HRT ranges, decision value, recalibration | Ranges calibrated to cover 90% do so only where calibrated (73.7%, 70.4%, 70.8% in the shifted worlds); the decision followed the score down under shift; online recalibration passed 5 of 7 registered claims and did not restore calibration. `docs/HRT_BRIEF.md`. |
| ML v2, held-out | Mostly negative: genome ensemble and counterfactual rejected; boosting plus Platt (A4) accepted as a small gain for benefits-processor and programmer; under mismatch the one-feature time-since-progress rule beats v1. |
| Attention, held-out (simulated workers) | 11 of 12 criteria met; criterion 7 not met. |
| Insights | Targets met on null data (false insights 0.4% worker, 0 admin); several recall targets missed and reported. |
| Simulated study | At the floor (30 of 32 post-tests scored 0); run 5 pilot stopped by its own criterion. |
| Role studies | Programmer pilot: `fast` failed cap-binding, `fast-low` passed all three by-code criteria. The study is not run (needs about 1 to 1.5 hours; command in `evals/study_roles/PLAN.md`, Amendment 3). Analyst not run. |

## How to run

```bash
make stop && make demo        # mock mode, no network; isolated home under data/; opens http://127.0.0.1:5173
make preflight                # green, amber or red; never prints a key
make stop                     # when done
```

`make demo` sets `UNDERSTUDY_MOCK=1` and `UNDERSTUDY_X=1` (seed and services). Services: engine 7700, agent 7710, sandbox sites 7801 to 7803, dashboard 5173. Logs: `data/logs/`. The Chrome extension and the desktop app are separate: see the README, "Run it". If a stack is already running, `make stop` first.

## Test these first (about 20 minutes)

1. **Start clean.** `make stop && make demo`, wait about 30 seconds. `curl -s http://127.0.0.1:7700/health` should say mock mode.
2. **Preflight.** `make preflight` shows no red. Read any amber line.
3. **Home** (`#/home`). One sentence about your week with its action, a short list of background tasks, and the task box "What should Knack do?". Type a task and press Enter: nothing starts before you press a button on a consent card. Do not press Allow unless you mean a real task (it uses your Claude account).
4. **Growth** (`#/growth`). My progress first, then Where my time goes, My steps against an experienced worker's, How my routines connect (and, for a programmer, My commits). The closed "About this data" says where the numbers come from.
5. **Routines** (`#/routines`). Press "Watch first", then run with your approval. Nothing should start before you press.
6. **Needs you** (`#/needs-you`). The irreversible step is waiting. Reject one, approve one. Sandbox only; nothing real is submitted.
7. **Admin** (account menu, View as Admin). Firm, Roles, People, Onboarding, Automation, Risk and Brief; the made-up firm needs the seed (`python -m understudy_engine.demo seed-firm`) on a live data folder.
8. **Your data** (`#/your-data`) and, in the Admin view, **Evidence** (More). Rows marked mock; the limitations list and the findings (stuck model, genome, simulated study, computer use). Check light and dark and a narrow window.
9. **Capture** (optional, needs Chrome). `cd extension && npm run build`, load `extension/dist` unpacked, switch capture on in the popup, open `http://127.0.0.1:7801/step/1`. After you have the extension id, restart with `UNDERSTUDY_EXTENSION_ID=<id> make demo` so the engine accepts it.
10. **Stop everything.** Press the red button; it should say Stopped and keep its card until you press Resume; press Resume. `ls data/demo-data/KILL` should report no such file.

The real-actuator arm switch is on by default in the agent service (D50) but inert: a real click needs your one-time token, the countdown and you present. Do not run the desktop app with real input except in an R1 session with the lead, and do not point anything at a real account. Real-click rung R0 ran once (read-only); R1 needs you present and the preflight in your own terminal.

## What is remaining

From [FIX_LEDGER.md](FIX_LEDGER.md) and the decisions up to D66.

| Area | Open |
|---|---|
| Computer use reliability | Round 2 ran (D65): 18 of 20 clean, the 0.80 bar not met; the real-click ladder is unchanged: second R0 (move the Claude window off TextEdit), then the R1 preflight; R2 stays no-go until R1 is reported. |
| Task path | No real task has been run through the Claude agent path; the budget stop, "Allow everything", the skill deny rule and a shell bypass of the deny rules are untested against the real command (D64); each check needs another approved real run. |
| Evaluation | The lead's full `make eval` is being re-run; re-pull every number from `evals/report.json` and `evals/report.facts.json` after it lands. Realism blocks live under `data/eval/` (not in git): copy them to a committed folder. |
| Studies | Live study (n = 4) not run. Role study: programmer needs the go-ahead command; analyst unrun. Optional labelled n = 1 pilot of the realism question. |
| Desktop | The full rehearsal on a visible desktop (it captures your real screen: needs Screen Recording and your approval) has not been run; Hey Knack has not been run with a microphone; the Try it screen for the first conversation is specified but is not a screen; screen-change watcher not built. |
| Admin data | Owner request 4.4: the made-up firm seed is on main; it has to run on the live data before the Admin view shows people. |
| Claims | README, Devpost and CLAIMS were brought up to date on 8 Nov about 03:00 GMT; after the lead's final `make eval` they need one more number check, and the Alongside reuse counts one recompute. |
| Decisions for you | Keep v1's stuck model or make "time since progress" the default signal (the A4 gain is small). Admin names in a real deployment (consent, D41). Whether the task path's full computer access stays on for the demo (D63). |
| Owner only | Screen Recording and Microphone permissions; Auth0 domain and client ID; the extension id; Devpost facts; sentences for CLAUDE.md about frames and admin visibility; real Outlook aggregate check (approval at run time); approvals for any real Claude-agent run; the live study with four teammates; rehearsal and submission. |

## At the freeze

Re-run `make eval`, then compare the README, Devpost and DEV post against `docs/drafts/CLAIMS.md`. Run `make test` once and paste the counts. Recompute the Alongside reuse numbers (the README gives its method).
