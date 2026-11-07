<!--
DEMO-DAY CHECKLIST draft, rewritten 7 Nov 2026, about 19:15 GMT, by the NARRATIVE track. Companion to DEMO_SCRIPT.md.
- [OWNER: ...] = a name, a decision or a fact only you have. [LEAD: ...] = the lead confirms or supplies.
- Times for Sunday are PROPOSED (the freeze at 08:00, submission at 12:00 and judging at 12:30 are from CLAUDE.md; the times between are suggestions).
- Commands were read from the Makefile and scripts at about 18:00 GMT. Nothing here was run by this track.
-->

# Demo-day checklist

Submission is Sun 8 Nov 12:00 GMT; judging starts 12:30. This page is what to do in the hours before, what to restart when something is red, what to fall back to for each beat of the three-minute demo, and what a person must do themselves.

## What only a person can do

From CLAUDE.md: grant macOS Accessibility and Screen Recording; put the API key in `.env`; run the live study with the four teammates (not run, and this page assumes it will not be); approve any real-click run, with the owner present; rehearse and give the demo; submit. Nobody else does these.

## Proposed timeline for Sunday

| When (GMT) | What |
|---|---|
| 08:00 | Feature freeze (CLAUDE.md). After this, fix only what breaks the demo |
| 08:00 to 09:00 | [LEAD] Full `make eval` (not FAST). Compare every number in README, Devpost, DEV post and DEMO_SCRIPT with `docs/drafts/CLAIMS.md` and change the text, not the report. The 17:38 report on 7 Nov is known to be stale in places (see "Submission" below) |
| 09:00 to 09:30 | [LEAD] Recount the Alongside reuse numbers (snippet in CLAIMS.md), paste the test counts, update `THIRD_PARTY_NOTICES.md`, re-run the two independent reviews' reproducers and update the "Independent review" lines |
| 09:30 to 10:30 | [OWNER] Two full rehearsals with wifi off, from `make stop` to the Evidence page. Time each one |
| 10:30 to 11:00 | [OWNER] Record the fallback video, with sound; check it plays on a second machine |
| 11:00 | [OWNER] Submit (see the Submission list). Aim for 30 minutes before the deadline |
| 11:30 | T minus 60 before judging: the preflight below |
| 12:00 | Deadline |
| 12:30 | Judging |

## The preflight

One command checks the stack and prints GREEN, AMBER or RED for each item. It never prints a key, never starts or stops anything, and exits non-zero if anything is red.

```bash
make preflight                  # the demo check (mode demo)
make preflight MODE=dev         # when a real home or live models are intended
```

GREEN is ready. AMBER works but read the note. RED: fix before judging. The script is `scripts/preflight.py` (`--fix-hints` is already on in the Makefile target; add `--deep` by running the script directly if you want the desktop typecheck). It checks Python and Node; `.env` key names (never values) and that it is git-ignored; mock mode; free disk; Chromium for Playwright; ports; engine, agent and sandbox health; which `UNDERSTUDY_HOME` the engine really uses; the kill flag; the demo seed; the coach; the Evidence report age; the extension build and zones; the desktop build; and offline readiness.

## T minus 60 minutes

1. **Clean start.** `make stop`, then `make demo`. Wait about 30 seconds for the engine to warm up.
2. **`make preflight`.** Zero red. Fix each amber that matters.
3. **Chrome, a clean profile.** Only the demo tabs; no mail, no chat, no other sites. Why: at the end of the safety review (17:56 on 7 Nov) the agent service had no authentication on its kill and approval routes, so any page open in the same browser could have cleared the kill flag; the privacy review found the same for foreign Host headers. Wifi off removes the network route, but a page already loaded can still call `127.0.0.1`. [LEAD: say whether this is now fixed; if it is, drop this line.]
4. **Build and load the extension.** `cd extension && npm run build`. In Chrome, `chrome://extensions`, load `extension/dist` unpacked (reload it if already loaded). Open its popup and switch **capture on**. After a few seconds it should say the identity is "from Understudy".
5. **Desktop coach.** Only if beat 3 version A or Cue is used. [LEAD: exact command (`npm run dev` in `apps/desktop` starts electron-vite) and flags.] macOS **Accessibility** and **Screen Recording** are human-only; the owner grants them. Preflight then shows port 7720 green.
6. **Offline rehearsal.** Wifi off. Run `make preflight` again, then the whole demo once with `DEMO_SCRIPT.md`. Anything that needs the network will show now.
7. **Safety net.** Press **Stop everything** in the dashboard, confirm it says Stopped, press **Resume**. Confirm `data/KILL` is absent afterwards (the preflight checks). If `data/KILL` appears when nobody pressed anything, find out why before going on; during the review a test client wrote it twice.
8. **Fallback assets exist and open:** the recorded video, screenshots, `data/golden/benefits_golden.json` with its screenshots, `evals/report.md`. [OWNER: where the video lives. None is known to this track.]
9. **The three standout beats, looked at once, rendered:** Cue (only if used), `#/growth`, `#/privacy`. For each: say what it shows on this laptop right now (example data or live), and make sure the script's words match.
10. **Machine hygiene.** Do Not Disturb on. Power connected. Display scaling and Chrome page zoom at 100% (the overlay ring was measured at 100% on one Retina display only). Close everything with notifications. Sleep and lock timers off.
11. Print the **teammate card** for CASE-1005 (in `DEMO_SCRIPT.md`).
12. **No real-click run before judging**, and none during the demo. The real-click ladder (R0 to R4) is not part of this demo.

## T minus 15 minutes

1. `curl -s -X POST http://127.0.0.1:7801/__reset` (clears the sandbox state; one call resets all three sites).
2. `make preflight`: zero red, and an amber list you recognise (typically only the desktop port if you skip the overlay).
3. Tabs in order: `#/genome`, `#/today`, `#/growth`, `#/routines`, `#/queue`, `#/privacy`, `#/evidence`. Chrome on `http://127.0.0.1:7801/step/1` with the extension on.
4. The routine card is still **proposed** (the preflight says so). If it says already consented, reseed: `make stop && make demo`, then redo step 4 above.
5. Start a screen recording as insurance. Wifi off.

## T minus 2 minutes

Open the first tab. Know the first fallback for each beat (table below). Do not restart anything now unless a red appears; if one does, take the fallback and keep going.

## What to restart when something is red

| Red item | Do this |
|---|---|
| Engine, agent, sandbox site or dashboard port free | `make stop && make demo` |
| A port is held by something that is not ours | `lsof -nP -iTCP:<port> -sTCP:LISTEN` to see what; stop it only if you are sure, then `make demo` |
| Engine uses the owner's real `~/.understudy` | `make stop && make demo` (it points the engine at `data/demo-home`). Never onboard on the real home before judging |
| Kill flag present | The **Resume** button, or `rm data/KILL`, or `curl -s -X POST http://127.0.0.1:7700/kill/clear` |
| Demo seed missing, or the routine is already consented | `make stop && make demo` (reseeds with `--reset`) |
| Evidence report missing or old | `make eval FAST=1` (or `make eval`), then reload the Evidence page. [LEAD: how long each takes; the 7 Nov full run took about 212 s of section time] |
| Extension build stale or zones differ | `cd extension && npm run gen && npm run build`, reload it in `chrome://extensions`, toggle capture off and on |
| Desktop app not running | Start it ([LEAD]: command); recheck port 7720 |
| Chromium missing for Playwright | `uv run --package understudy-agent playwright install chromium` (needs the network: do this before the wifi goes off) |
| Sandbox state not clean | `curl -s -X POST http://127.0.0.1:7801/__reset` |
| Model boot check red (live mode only) | Fix the IDs in `.env`, or run in mock mode: the demo does not need a model |
| `.env` not git-ignored or readable by others | Fix now; never commit it |

Never restart in the middle of the demo. Press **Stop everything**, say one sentence, take the fallback.

## Fallback ladder per demo beat

Each beat has four rungs. Go down one at a time and say what you are showing.

| Beat | 1 Live | 2 Cached or offline | 3 Recording | 4 Talk over the page |
|---|---|---|---|---|
| 2 See the invisible | `#/genome` from the engine | The page's fixtures (they render offline) | [OWNER: a recorded ribbon, if you make one] | The README table row for the controls. Always say "synthetic" |
| 3 Coach (and Cue, if confirmed) | Work CASE-1005 in Chrome, ring on the cliff button | `#/today`: coach state and level | [OWNER: a short clip of the ring, if you make one] | The coach-replay line: 14 of 14 planted skips ringed, 0 experts prompted |
| 4 Growth | `#/growth` with example data | The same, a different example learner | [OWNER] | The screen's one sentence: how much less help, not how expert |
| 5 Automate | Proposal, **Watch first**, **Run with my approval** (a replay) | The cached golden run (`data/golden/`, labelled cached) | [OWNER: a clip of the queue card] | The routine card and the trust ladder explained |
| 6 Privacy | `#/privacy` from the engine | The Evidence page's privacy block | A scrolled screenshot | The canary result and its limits, in words |
| 7 Proof | `#/evidence` from `evals/report.json` | `evals/report.md` open in a viewer | A scrolled screenshot of the page | The README results table |

## If something goes wrong in front of judges

Say what happened in one plain sentence. Do not apologise at length and do not improvise a real action. The honest framing is part of the product: synthetic data is labelled, the live study has not been run (n = 4), the simulated study uses language models and hit a floor, the oracle is a simplified rule set, not law, and we do not claim novices become experts.

## Submission (a person does these)

Items marked [LEAD] are for the lead to prepare first.

- [ ] **The form.** Open the submission page and confirm every field and the format it wants (repository link, Devpost, video, track choices). [OWNER: this track does not know the form's fields.]
- [ ] **The repository is public**, and opens in a private window, logged out. [OWNER]
- [ ] **README renders**, including the mermaid diagram. If the diagram does not draw, the text above it still stands.
- [ ] **`.env` is not committed and is ignored:** `git ls-files .env` prints nothing; `git check-ignore -v .env` prints a rule. `.env.example` holds placeholders only. [LEAD: run the secret scan over the tree and history and say the result; the privacy review found no key-shaped string in tracked files or the commits it checked at 17:55, and could not check what is inside `.env`.]
- [ ] **`THIRD_PARTY_NOTICES.md` is current.** Every file with an `Adapted from` header appears once in its tables. [LEAD]
- [ ] **The report is regenerated** after the freeze and the drafts match it. Known problems in the 17:38 report, to be gone or not quoted: a failing static-guard count shown inside a section marked ok ("27 violations in 172 files"; the code now gives 0 per the review, so the report is stale); two cost lines that read "about None USD"; and a section count and limitations count that differ from the hand-typed ones in the feature catalogue. [LEAD]
- [ ] **No claim outruns its row.** Read README, Devpost, DEV post and the script against `docs/drafts/CLAIMS.md`: nothing in the "left out" list is back in.
- [ ] **Test counts** pasted into the README. [LEAD]
- [ ] **Alongside disclosure** present, with current counts. [LEAD recounts; OWNER decides whether to ask an organiser.]
- [ ] **Licence chosen**, and a licence file added. [OWNER]
- [ ] **Team names and roles** in the Devpost and README. [OWNER]
- [ ] **AI-assisted build disclosed** in the wording the owner approves, after checking the hackathon's rules. [OWNER]
- [ ] **Demo video** recorded and linked, if the form allows. [OWNER]
- [ ] **DEV post** published (not left as a draft) and its link placed in the Devpost. [OWNER]
- [ ] **MLH categories**: enter only those whose status the Devpost states truthfully (Gemini, ElevenLabs and Auth0 are in progress or flagged off). [OWNER]
- [ ] **Submit**, screenshot the confirmation and note the commit hash you submitted: `git rev-parse HEAD`. [OWNER]

## Who to ask

| For | Ask | Where to look |
|---|---|---|
| Permissions, the real-click go-ahead, final calls | The owner | [OWNER: name and number] |
| Driving the demo | The presenter and the operator | [OWNER: who is who] |
| Engine, analytics, memory, packs | Whoever owns `services/engine` | `docs/AGENTS.md` ownership table; `data/logs/engine.log` |
| Agent, sandbox sites, security layers, queue | Whoever owns `services/agent` | `data/logs/agent.log`, `data/logs/sites.log` |
| Desktop overlay and coach | Whoever owns `apps/desktop` | the desktop app's own log in its user data folder |
| Dashboard screens | Whoever owns `apps/dashboard` | `data/logs/dashboard.log` |
| Extension, pack files, evals and the preflight | Platform (`extension/`, `packages/`, `evals/`) | this page; `evals/README.fragment.md` |
| Judges' questions about HRT, G-Research, Wordsmith | [OWNER: one named answerer per track] | the Tracks sections of the README and Devpost |

## Quick reference

| Thing | Where |
|---|---|
| Engine, agent | `http://127.0.0.1:7700`, `http://127.0.0.1:7710` |
| Sandbox calculators | `http://127.0.0.1:7801` (also `/casenote`), `7802`, `7803` |
| Dashboard | `http://127.0.0.1:5173` |
| Desktop coach channel | `http://127.0.0.1:7720` |
| Start, stop, check | `make demo`, `make stop`, `make preflight` (logs in `data/logs/`) |
| Demo home | `data/demo-home` (person `p_learn01`) |
| Where each number comes from | `docs/drafts/CLAIMS.md`, then `evals/report.md` |
