<!-- DRAFT for the lead and the owner. TODO(owner) = a name or a fact only you have. Companion to DEMO_SCRIPT.md. -->

# Demo-day checklist

Judging starts 12:30 on Sun 8 Nov (submission 12:00). This page is what to do in the hour before, what to restart when something is red, and what to fall back to for each step of the three-minute demo.

## The preflight

One command checks the whole stack and prints GREEN, AMBER or RED for each item. It never prints a key, never starts or stops anything, and exits non-zero if anything is red.

```bash
uv run --package understudy-agent python scripts/preflight.py --fix-hints          # normal check
uv run --package understudy-agent python scripts/preflight.py --fix-hints --deep   # also typechecks the desktop app (about a minute, cached)
uv run --package understudy-agent python scripts/preflight.py --mode dev           # when the real home or live models are intended
```

GREEN is ready. AMBER works but read the note. RED fix before judging. `--fix-hints` prints the command for each non-green line. It checks: Python and Node; `.env` key names (never values) and that it is git-ignored; mock mode; free disk; Chromium for Playwright; the voice flag; a read-only model list in live mode; every port; engine, agent and sandbox health; which `UNDERSTUDY_HOME` the engine really uses; the kill flag; the demo seed; the coach; the Evidence report age; the extension build and zones; the desktop build; and offline readiness (no remote URL in the dashboard, golden run, synthetic data).

## T minus 60 minutes

1. **Clean start.** `make stop`, then `make demo`. Wait about 30 seconds for the engine to warm up.
2. **Preflight with `--deep`.** Zero red. Fix each amber that matters (the table below).
3. **Build and load the extension.** `cd extension && npm run build`. In Chrome, `chrome://extensions`, load `extension/dist` unpacked (reload it if already loaded). Open its popup and switch **capture on**. After a few seconds it should say the identity is "from Understudy".
4. **Start the desktop app.** TODO(lead): exact command. macOS **Accessibility** and **Screen Recording** are human-only: the owner grants them. Preflight then shows port 7720 green.
5. **Offline rehearsal.** Turn the wifi off. Run the preflight again, then the whole demo once with `DEMO_SCRIPT.md`. Anything that needs the network now will show.
6. **Check the safety net.** Press **Stop everything** in the dashboard, confirm it says Stopped, press **Resume**. Confirm `data/KILL` is absent afterwards (the preflight checks).
7. **Fallback assets exist and open:** the recorded video, the screenshots, `data/golden/benefits_golden.json` with its screenshots, `evals/report.md` for the Evidence page. TODO(owner): where the video lives.
8. **Machine hygiene.** Do Not Disturb on. Power connected. Display scaling and Chrome page zoom at 100% (the overlay ring was calibrated there only). Close mail, chat and anything with notifications. Sleep and lock timers off for the session.
9. Print the **teammate card** for CASE-1005 (in `DEMO_SCRIPT.md`).

## T minus 15 minutes

1. `curl -s -X POST http://127.0.0.1:7801/__reset` (clears the sandbox rehearsal state; one call resets all three sites).
2. Preflight (no `--deep`): zero red, and the amber list is one you recognise (typically only the desktop port if you skip the overlay).
3. Tabs ready in order: `#/onboarding`, `#/genome`, `#/today`, `#/routines`, `#/queue`, `#/presence`, `#/evidence`; Chrome on `http://127.0.0.1:7801/step/1` with the extension on.
4. The routine card is still **proposed** (the preflight says so). If it says already consented, reseed: `make stop && make demo`, then redo step 3 above.
5. Start a screen recording as insurance. Wifi off.

## T minus 2 minutes

Run only the quick preflight (`--skip models`). Open the first tab. Know the first fallback for each step (table below). Do not restart anything now unless a red appears; if one does, switch to the fallback and keep going.

## What to restart when something is red

| Red item | Do this |
|---|---|
| Engine, agent, sandbox site or dashboard port free | `make stop && make demo` |
| A port is held by something that is not ours | `lsof -nP -iTCP:<port> -sTCP:LISTEN` to see what; stop it only if you are sure, then `make demo` |
| Engine uses the owner's real `~/.understudy` | `make stop && make demo` (it points the engine at `data/demo-home`). Never onboard on the real home before judging |
| Kill flag present | The **Resume** button, or `rm data/KILL`, or `curl -s -X POST http://127.0.0.1:7700/kill/clear` |
| Demo seed missing, or the routine is already consented | `make stop && make demo` (reseeds with `--reset`) |
| Evidence report missing or old | `make eval FAST=1` (or `make eval`), then reload the Evidence page. TODO(lead): how long it takes |
| Extension build stale or zones differ | `cd extension && npm run gen && npm run build`, reload it in `chrome://extensions`, toggle capture off and on |
| Desktop app not running | Start it (TODO(lead): command); recheck port 7720 |
| Chromium missing for Playwright | `uv run --package understudy-agent playwright install chromium` (needs the network: do this before the wifi goes off) |
| Sandbox state not clean | `curl -s -X POST http://127.0.0.1:7801/__reset` |
| Model boot check red (live mode only) | Fix the IDs in `.env`, or run in mock mode: the demo does not need a model |
| `.env` not git-ignored or readable by others | Fix now; never commit it |

Never restart in the middle of the demo. Press **Stop everything**, say one sentence, take the fallback.

## Fallback ladder per demo step

Each step has four rungs. Go down one rung at a time and say what you are showing.

| Step | 1 Live | 2 Cached or offline | 3 Recording | 4 Talk over the slide |
|---|---|---|---|---|
| Set up | Walk the real onboarding on `#/onboarding` | Show the already onboarded demo home on `#/memory` | The recorded onboarding clip | The two memory files side by side as screenshots |
| See the invisible | `#/genome` from the engine | The page's fixtures (they render offline) | The recorded ribbon and waterfall | The README figures. Always say "synthetic" |
| Coach | Work CASE-1005 in Chrome, ring on the cliff button | `#/today` coach state with the chip lightening | The 20-second recording of the ring landing | The Evidence page numbers on the dignity gate |
| Automate | Proposal, **Watch first**, **Run with my approval** | Cached golden run (`data/golden/`, mode cached) | The recording of the queue card | The routine card and the trust ladder explained |
| Away | Real away run (only if the owner has re-approved real runs) | Simulated-clock sequence (`GET /offhours/demo`) and the heatmap | The recorded real run from the S2 spike | The start-or-wait rule on the Evidence page |
| Proof | `#/evidence` from `evals/report.json` | `evals/report.md` open in a viewer | A scrolled screenshot of the page | The README results table |

## If something goes wrong in front of judges

Say what happened in one plain sentence. Do not apologise at length and do not improvise a real action. The honest framing is part of the product: synthetic data is labelled, the study is **PENDING** (n = 4), the oracle is a simplified rule set, not law, and we do not claim novices become experts.

## Who to ask

| For | Ask | Where to look |
|---|---|---|
| Permissions, the real-click go-ahead, final calls | The owner | TODO(owner): name and number |
| Driving the demo | The presenter and the operator | TODO(owner): who is who |
| Engine, analytics, memory, packs | Whoever owns `services/engine` | `docs/AGENTS.md` ownership table; `data/logs/engine.log` |
| Agent, sandbox sites, security layers, queue | Whoever owns `services/agent` | `data/logs/agent.log`, `data/logs/sites.log` |
| Desktop overlay and coach | Whoever owns `apps/desktop` | the desktop app's own log in its user data folder |
| Dashboard screens | Whoever owns `apps/dashboard` | `data/logs/dashboard.log` |
| Extension, pack files, evals and the preflight | Platform (`extension/`, `packages/`, `evals/`) | this page; `evals/README.fragment.md` |
| Questions from judges about HRT, G-Research, Wordsmith | TODO(owner): one named answerer per track | the Tracks section of the README |

## Quick reference

| Thing | Where |
|---|---|
| Engine, agent | `http://127.0.0.1:7700`, `http://127.0.0.1:7710` |
| Sandbox calculators | `http://127.0.0.1:7801` (also `/casenote`), `7802`, `7803` |
| Dashboard | `http://127.0.0.1:5173` |
| Desktop coach channel | `http://127.0.0.1:7720` |
| Start, stop | `make demo`, `make stop` (logs in `data/logs/`) |
| Demo home | `data/demo-home` (person `p_learn01`) |
