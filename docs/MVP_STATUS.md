# MVP status for the owner

Written 7 Nov 2026, about 21:00 GMT, for the 22:00 check. Everything below is on example data and sandbox sites in mock mode. Nothing here was tested with people.

## What works now

Seen working by the lead today, against the live stack:

- **Dashboard.** 28 screens and views load with no page errors.
- **Benefits agent in mock mode.** A run on the sandbox calculators ends with an item in the approval queue and 0 false claims. The one irreversible step waits for a click.
- **Genome, routines, queue.** The work ribbon with both controls, a routine proposal with "Watch first", and the approval queue.

Built and tested by its track, not yet seen end to end by the lead: the proactive layers (briefing, calendar, git habits, local model), the attention router, insights for workers and admins, background agents, the privacy ledger and the on-screen ring. Not working: computer use on a real desktop, Cue end to end, live voice. Status words per feature: [FEATURE_CATALOGUE.md](FEATURE_CATALOGUE.md).

## How to run

```bash
make stop && make demo        # mock mode, no network; isolated home under data/; opens http://127.0.0.1:5173
make preflight                # green, amber or red; never prints a key
make stop                     # when done
```

`make demo` sets `UNDERSTUDY_MOCK=1` and `UNDERSTUDY_X=1`. Services: engine 7700, agent 7710, sandbox sites 7801 to 7803, dashboard 5173. Logs: `data/logs/`. The Chrome extension and the desktop app are separate: see the README, "Run it". `make eval` writes the report; `make test` runs the suites.

## Test these first (about 20 minutes)

1. **Start clean.** `make stop && make demo`, wait about 30 seconds. `curl -s http://127.0.0.1:7700/health` should say mock mode.
2. **Preflight.** `make preflight` shows no red. Read any amber line.
3. **Genome** (`#/genome`). A **synthetic** badge, an expert trace above a novice's, gaps and seconds lost, and both controls (expert against expert, shuffled labels) with intervals. Look for anything that reads as a claim about real people.
4. **Routines** (`#/routines`). The routine card for entering the household into three calculators. Press "Watch first", then run it with your approval. Nothing should start before you press.
5. **Queue** (`#/queue`). The irreversible step is waiting. Reject it, then approve one. It is a sandbox site; nothing real is submitted.
6. **Privacy** (`#/privacy`). In mock mode rows are marked mock and nothing reached a model. No pictures, no text.
7. **Evidence** (`#/evidence`). Scroll to the end: the limitations register and "what this does not show". The report behind it is from 17:38 and predates the newest results (see below).
8. **Labels.** Visit `#/growth`, `#/repeats` and `#/firm`. Each should say example data or synthetic firm, and names should be made up. The word "demo" should appear nowhere visible. Check light and dark, and a narrow window.
9. **Capture** (optional, needs Chrome). `cd extension && npm run build`, load `extension/dist` unpacked, switch capture on in the popup, open `http://127.0.0.1:7801/step/1` and enter a household. Events should arrive without any page text.
10. **Stop everything.** Press the red button in the dashboard; it should say Stopped. Press Resume. `ls data/demo-data/KILL` should then report no such file (under `make demo` the data folder is `data/demo-data`).

Do not set `UNDERSTUDY_REAL_ACTUATOR=1`, do not run the desktop app with real input, and do not point anything at a real account.

## What is remaining

From [FIX_LEDGER.md](FIX_LEDGER.md). Closed means the lead saw the check pass.

| Area | Open |
|---|---|
| Real-desktop safety | Real-click ladder: R0 ran once (zero events, the test point was covered by another window). Next: owner moves the window, second R0, R1 preflight in the owner's terminal. R2 stays no-go until R1 is reported. The gate-hash confirmation run is still to do. |
| Agent reliability | Held-out confirmation not run (clean n = 4, injected n = 20). Long-horizon items open (checkpoint and working memory, carry-over across escalation, reader digest memo, frame retention and meter wiring). Spend about US$8.9 of the US$20 track (total cap US$60). |
| Dashboard | Smoke test had 4 failures at about 19:30 (Evidence map, Privacy canary wording, two Explain checks); design sync for the remaining screens and Notices; Repeats preview files to delete. |
| Desktop | 19-check rehearsal not run; Live tray badge and HUD timer cut; screen-change watcher not built (needs Screen Recording); extension `dist` rebuild after the role generation step. |
| Evaluation | `make eval` has not been re-run since 17:38: ML v2, attention, insights, Cue, hit list, realism and role-study sections are not yet wired into the report or the Evidence page. Admin display names wait for the insights run to finish, then regenerate samples. |
| Studies | Live study (n = 4) not run. Simulated study at the floor; its follow-up pilot was stopped by its own criterion. Role studies not run (first programmer pilot failed its floor check). |
| Claims | Drafts (Devpost, DEV post, README draft, CLAIMS) still quote the stuck model's first headline; each needs the sentence that its edge falls on harder generators. No claim that the gate resists hostile pages from the text-only injected condition. |
| Decision for you | Keep v1's stuck model, or make the plain "time since progress" rule the default signal. The gain from the accepted v2 variant (A4) is small. |
| Owner only | Screen Recording and Microphone permissions; Auth0 domain and client ID; the extension id from `chrome://extensions`; Devpost facts; the sentences for CLAUDE.md about frames and admin visibility; real Outlook aggregate check (approval at run time); licence; rehearsal and submission. |

## At the freeze

Re-run `make eval`, then compare the README, Devpost and DEV post against `docs/drafts/CLAIMS.md`. Run `make test` once and paste the counts. Recompute the Alongside reuse numbers (the README gives its method; the count moves while the desktop app is edited). Re-run the two independent reviews' reproducers and update the README's review lines.
