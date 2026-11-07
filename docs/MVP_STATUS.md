# MVP status for the owner

Written 7 Nov 2026, about 21:20 GMT, for the 22:00 check. Everything below is on example data and sandbox sites we wrote, in mock mode. Nothing here was tested with people.

## What works now

Seen working by the lead today, against the live stack (restarted on the final code at about 20:57 and reseeded):

- **Dashboard.** 28 screens and views load with no page errors and none falling back to example data (`node apps/dashboard/scripts/live-sweep.mjs` repeats the check). Worker Home shows two example pointers (an example week from the synthetic firm stands in for the seeded profile). Admin views show made-up names and say so. The word "demo" appears in no visible string.
- **Benefits agent in mock mode.** A run on the sandbox calculators ends with an item in the approval queue and 0 false claims. The irreversible step waits for a click.
- **Genome, routines, queue, Repeats, Firm, Evidence, Privacy.** All load live. The routine card opts in with "Run with my approval".
- **Tests, run today at the final code:** engine and packs 3,889 passed (1 skipped); agent service 1,726 passed (6 skipped); dashboard type-check clean and 541 tests passed; desktop type-check clean and 2,684 tests passed (4 skipped); the reviewer's safety reproducers 183 of 183.
- **`make eval`** ran in full at 21:05 (32 sections ok, 1 pending, 2 not run). A quick merge step adds the computer-use and role-study sections and re-words two limitation strings; see "What is remaining".

Built and tested by its track, not seen end to end by the lead on a real desktop: the on-screen ring and Cue panel, the attention router on the desktop, the Chrome extension capture, the desktop app. They need you at the machine.

## Results you should know before you test

All numbers are synthetic, simulated, or language-model-on-our-sandbox. Details in the README and `docs/FEATURE_CATALOGUE.md`.

| Area | Result |
|---|---|
| Computer use, held-out (gate 35e964049fd0) | **Clean n = 4: 1 completed** (descriptive, Wilson about [0.05, 0.70]); 2 false claims caught by the code check; 1 benign drop-down stopped by the gate. The Submit waited for a human every time; nothing was submitted. Injected n = 20: all paused at step 0 (text-only evidence, not proof the gate resists hostile pages). 3 of 3 on development households did not generalise. |
| Stuck model and work genome | Strong on their own generator; the edge falls to a few thousandths of a nat (stuck) and precision 48 to 71% (genome) on three harder synthetic generators. |
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
3. **Your week** (`#/home`). Two pointers, one sentence each, a plain line that an example week stands in for this profile. Press "Why am I seeing this?".
4. **Genome** (`#/genome`). A synthetic badge, an expert trace above a novice's, gaps and seconds lost, both controls with intervals.
5. **Routines** (`#/routines`). Press "Watch first", then run with your approval. Nothing should start before you press.
6. **Queue** (`#/queue`). The irreversible step is waiting. Reject one, approve one. Sandbox only; nothing real is submitted.
7. **Firm** (switch "View as" to Admin). Made-up names, aggregate bands, a note that the firm is synthetic.
8. **Privacy and Evidence** (`#/privacy`, `#/evidence`). Rows marked mock; the limitations list and the findings (stuck model, genome, simulated study, computer use). Check light and dark and a narrow window.
9. **Capture** (optional, needs Chrome). `cd extension && npm run build`, load `extension/dist` unpacked, switch capture on in the popup, open `http://127.0.0.1:7801/step/1`. After you have the extension id, restart with `UNDERSTUDY_EXTENSION_ID=<id> make demo` so the engine accepts it.
10. **Stop everything.** Press the red button; it should say Stopped; press Resume. `ls data/demo-data/KILL` should report no such file.

Do not set `UNDERSTUDY_REAL_ACTUATOR=1`, do not run the desktop app with real input, and do not point anything at a real account. Real-click rung R0 ran once (read-only); R1 needs you present and the preflight in your own terminal.

## What is remaining

From [FIX_LEDGER.md](FIX_LEDGER.md).

| Area | Open |
|---|---|
| Computer use reliability | Diagnose the calculator B failures and the benign drop-down false stop, then a new pre-registered round on new seeds. Real-click ladder: second R0 (move the Claude window off TextEdit), then the R1 preflight; R2 stays no-go until R1 is reported. Focus reads use a single mechanism. |
| Evaluation | Quick merge (`python -m understudy_engine.eval --only agentic,study_roles --merge`) pending from the eval agent; then the Evidence page shows the computer-use and pilot sections. Realism blocks live under `data/eval/` (not in git): copy them to a committed folder. |
| Studies | Live study (n = 4) not run. Role study: programmer needs the go-ahead command; analyst unrun. Optional labelled n = 1 pilot of the realism question. |
| Desktop | 19-check rehearsal not run (it captures your real screen: needs Screen Recording and your approval); Live tray badge and HUD timer cut; screen-change watcher not built. |
| Claims | Devpost, DEV post, README draft and CLAIMS still quote the stuck model's first headline; each needs the sentence that its edge falls on harder generators, and the computer-use held-out result. |
| Decisions for you | Keep v1's stuck model or make "time since progress" the default signal (the A4 gain is small). Admin names in a real deployment (consent, D41). |
| Owner only | Screen Recording and Microphone permissions; Auth0 domain and client ID; the extension id; Devpost facts; sentences for CLAUDE.md about frames and admin visibility; real Outlook aggregate check (approval at run time); the live study with four teammates; rehearsal and submission. |

## At the freeze

Re-run `make eval`, then compare the README, Devpost and DEV post against `docs/drafts/CLAIMS.md`. Run `make test` once and paste the counts. Recompute the Alongside reuse numbers (the README gives its method).
