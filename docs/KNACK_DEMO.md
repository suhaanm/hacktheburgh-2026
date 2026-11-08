# Knack: the showcase shot list (first launch, launch video, demo video, submission video)

Written by DEMO-DIRECTOR (Claude Sonnet 5.5), 7 to 8 Nov 2026, for the owner's D54 request: the first launch shows everything Knack can do, every flag on, everything linked and fed the right context, live sites open to help; the owner asks the lead to start the screen recording and edits the footage into a launch video, a demo video and the hackathon submission video (Hack the Burgh XIII; targets HRT = predictions and decisions, G-Research = make the invisible visible, Wordsmith = a complicated browser-use workflow).

**How to read this file.** Section 1 is what must be true before anybody presses record. Section 2 is the order to RECORD in (takes), which is not the order to CUT in. Sections 3 to 5 are the cuts: scene numbers, the screen, the exact actions, the spoken line, the on-screen text to hold, the length, what it proves, the data it needs and the fallback if it fails live. Section 6 is the context audit. Section 7 lists what was verified headless and what only the owner can check at the demo. Section 8 is the claims rule: every number carries its label.

**Truth rule.** Every number said or shown is copied from `evals/report.md` (generated 7 Nov 2026 21:40 UTC, mock mode), `README.md` or `docs/FEATURE_CATALOGUE.md`, and carries its label: synthetic, simulated participants (language models, not people), or language model on our sandbox. The live study with four teammates has not been run (n = 4, not run). Nothing in this file claims that novices become experts; the claim is that the system lifts a novice a little on data we generated and shows its own limits. The recording starts only when the owner says begin (`scripts/record-demo.sh`, the lead runs it).

Recording is of the main display. Close everything you do not want in the video, turn Do Not Disturb on, hide the Dock if you like. Nobody uses a real account; every site on screen is a sandbox page we wrote, every household and firm is synthetic and says so.

---

## 1. Before anybody presses record

### 1.1 Start the stack, in this order (the lead)

| Step | Command or check | Why |
|---|---|---|
| 1 | `make stop`, then `UNDERSTUDY_AGENT_HEADED=1 make live` | The agent runs the three calculators in its own Chromium, headless by default; with `UNDERSTUDY_AGENT_HEADED=1` its windows appear on screen while it works (scene M7). `make live` seeds the example content once (`data/live-home`, `data/live-data`) and prints no key. **A live home seeded before the Growth step existed has no Growth curve.** With the stack stopped, top it up (it adds only the missing Growth ledger and changes nothing else; tested): `UNDERSTUDY_HOME=$PWD/data/live-home UNDERSTUDY_DATA_DIR=$PWD/data/live-data UNDERSTUDY_MOCK=0 uv run --package understudy-agent python -m understudy_engine.demo seed`. `seed --reset` instead puts the whole story back (queue, routines, memory, Growth) |
| 2 | Launch Knack with `ALONGSIDE_OVERLAY_CAPTURABLE=1` in its environment | **Without it the ring, the ghost cursor, the corner pill, the corner cards, the Cue panel and the Hey Knack cards are excluded from screen recordings** (the app sets content protection on every one of them: `capture/overlay-window.ts`, `hud.ts`, `toast.ts`, `cue/panel-window.ts`, `wake/card-window.ts`). The video would show a calm window and no coach. Nothing sets it by default |
| 3 | `node scripts/link-audit.mjs --expect live --desktop-ext http://127.0.0.1:7720` | 48 read-only checks, PASS or FAIL per link, exit 1 on any FAIL (section 7.1). Run it again after any restart. In mock mode use `--expect mock` |
| 4 | `curl -s -X POST http://127.0.0.1:7801/__reset` (or `scripts/demo-open.sh --reset ...`) | Clears sandbox notes, submissions and counters on all three sites |
| 5 | macOS: Microphone and Speech Recognition allowed for Knack, Screen Recording and Accessibility allowed (owner only), Do Not Disturb on | Hey Knack (M3) needs the first two; the ring and the screen glance need Screen Recording; real clicks are not used in the main cut |
| 6 | A rehearsal of the worker (no desktop app needed): `cd apps/desktop && node scripts/demo-worker.mjs --private --headless --scene both --gap 20` | Proves the script and the engine decisions before the recording (about 3.5 minutes; section 7.2) |

### 1.2 What the data must show (checked by the audit; all seeded through `understudy_engine/demo.py` only)

| Scene needs | Source | Audit link | State after the seed |
|---|---|---|---|
| Home: the week's insight, an approval, "n things need you" | `/insights/worker`, `/queue` | `GET /insights/worker`, `GET /queue` | 2 pointers (the cliff check, reconciling before the note; synthetic firm), 2 pending approvals from last night's run (one irreversible: "Submit case note CN-2041") |
| Needs you: prepared actions, proposals, rule proposal, overnight line | `/briefing`, `/routines`, `/memory/proposals`, `/offhours/report` | same names | 3 briefing cards, 2 routine proposals (58 repeats = about 92 minutes a week; 35 repeats), 1 rule proposal, "1 ran, 2 queued, 1 yielded" |
| Routines: a compiled routine the agent can run | `/routines` (driver compiled) | `GET /routines` | `calc-entry-3x` with `steps.json` installed by the seed |
| Growth: a curve | `/growth` | `GET /growth` | **added by this work**: 90 occurrences of ONE simulated improving learner, labelled `synthetic_learner` (Example data badge), 4 offloaded rows listed and never scored. Before: 0 occurrences, "Your curve starts after 10 steps" |
| Firm, Roles, Onboarding (admin) | `/insights/admin/*` through the dashboard proxy (needs the per-boot token) | `GET /engine/insights/admin/firm (proxy adds the token)` | 60 synthetic people, 3 roles, names made up |
| Forecasts, Genome, Evidence | `/hazard/*`, `/genome/*`, `/eval/report` | `GET /hazard/p_nov03`, `GET /genome/t_entitlement_check`, `GET /eval/report` | 33 of 35 sections with results; 206 limits listed |
| Privacy ledger | `/privacy/ledger`, `/privacy/summary` | same | Empty in mock mode by design. In live mode rows appear as models are called (Live voice turns, glances): nothing is faked into it |

### 1.3 Windows and layout

The Knack window opens at 80 percent by 84 percent of the work area (1152 by 735 on a 1440 by 900 screen; the owner's display measured 1728 by 999 usable, which gives about 1382 by 839). The corner pill and cards sit bottom-right, 16 px in. The worker's Chromium (scene M4 and M5) is a second window; `scripts/demo-open.sh --list` shows every Chrome window and where it goes. **The ring is not drawn while the Knack window is focused** (the coach does not annotate its own app), so for M4 and M5 the Knack window is behind or minimised and the worker's window is in front.

---

## 2. The recording order (takes)

Record in takes, then cut. Each take starts from a settled screen so the editor can join them.

| Take | Scenes | Setup | Who acts |
|---|---|---|---|
| A, the app | M1, M2, M6, M9, M10, M11, M12, M13, M14 | Knack open on Home, stack seeded, Do Not Disturb on | the owner clicks; the lead watches the stack |
| B, voice | M3 | Same, microphone and speech granted, consent cards ready | the owner speaks |
| C, the worker | M4, M5 | Knack running, its window minimised or behind; `node apps/desktop/scripts/demo-worker.mjs --pace slow --position 60,60 --size 1180x760` run by the lead in a terminal that is not on screen | a script plays a teammate; nobody touches the mouse |
| D, the agent | M7, M8 | `scripts/demo-open.sh --only casenote` for the case-note window; the stack started headed; Routines open | the owner presses Run now and the approval click |
| E, stop | M15 | an agent run in progress (repeat the start of D) | the owner |
| F, optional | M16 | only if the owner has run R1 and the rung record exists | the owner, supervised |

---

## 3. Main cut: about 3 minutes 55 seconds

Scene lengths below include the pause after each spoken line. Scenes marked (optional) can go if the cut runs long; the cut never drops M13, the honesty scene.

| # | Scene | Starts | Length | Capability | Target |
|---|---|---|---|---|---|
| M1 | Launch and Home | 0:00 | 12 s | launch, Home, overnight approval, week insight | G-Research |
| M2 | Where the time goes (work genome) | 0:12 | 22 s | work ribbon, controls, intervals | G-Research |
| M3 | Hey Knack (voice guidance) | 0:34 | 18 s | wake word, Live voice, ring and ghost cursor | Wordsmith |
| M4 | The coached case | 0:52 | 28 s | coach ring on the skipped cliff check | G-Research, HRT |
| M5 | Cue, the stuck rescue | 1:20 | 18 s | Cue one cue and a reason, then silence | HRT |
| M6 | A routine, one opt-in at a time | 1:38 | 14 s | proposal, Watch first, Run with my approval | Wordsmith |
| M7 | The agent works, the pill shows | 1:52 | 22 s | background agent over three calculators, corner pill | Wordsmith |
| M8 | The irreversible step waits for me | 2:14 | 24 s | approval card, Approve and submit, case note | Wordsmith |
| M9 | Growth | 2:38 | 14 s | independence score, intervals, honest verdict | HRT |
| M10 | Repeats and Needs you (optional) | 2:52 | 8 s | repeat list, one list for decisions | Wordsmith |
| M11 | The firm view (admin) | 3:00 | 14 s | expert versus junior, onboarding speed | G-Research |
| M12 | Forecasts | 3:14 | 11 s | calibrated stuck forecast, held-out | HRT |
| M13 | Evidence: what did not hold up | 3:25 | 22 s | honest failures | all three |
| M14 | Privacy (optional) | 3:47 | 8 s | ledger of what left the Mac | all three |
| M15 | Stop, the kill hotkey, outro | 3:55 | 14 s | kill flag, supervisor stop | all three |

Start times are for the full cut with both optional scenes (4:09). Without M10 and M14 every later scene starts 8 s and then 16 s earlier and the cut ends at 3:53. The voiceover lines total about 540 words, which is about 3 minutes 35 seconds of speech at 150 words a minute; the rest of each scene is the screen doing the work. M16 (the supervised click) is outside the cut.

### M1. Launch and Home (12 s)

- **Screen.** Dock icon, then the Knack window (Home), light theme.
- **Actions.** The owner clicks the Knack icon in the Dock. The window opens at its remembered size. No other action.
- **Voiceover.** "This is Knack. It opens on one thing that needs me: an overnight run that stopped before it could not be undone. And one number about my week."
- **Hold on screen (3 s).** "Week of 9 November", the badge "Synthetic firm" (or "Example data"), the approval row "Submit case note CN-2041 ... Cannot be undone.", and the quiet row "The cliff check: about 35 seconds longer than the expert." plus "1 thing needs you". The status line in the sidebar reads "Live models" (live) or "Running with example data" (mock).
- **Proves.** The window, the Home screen with the one-sentence rule and the push versus pull rule; the sidebar of five items. Target: G-Research (a number that was invisible).
- **Data.** Seeded queue and pointers; badge origin "synthetic firm". **Order note.** An approval that blocks a job takes the Home hero by design; the week's pointer is the first quiet row until the worker approves or rejects. Do not resolve the seeded approvals before M1.
- **If it fails.** Reload the window (Command-R) or open the page in Chrome with `scripts/demo-open.sh --only home`. If the status line says "Cannot reach the engine", stop and fix the stack; never narrate over it.

### M2. Where the time goes (22 s)

- **Screen.** Knack, `Genome` (More, then "Where time goes"; or click the insight row on Home).
- **Actions.** Open it. Hover the ribbon: expert p_exp04 on top (6 min 45 s), novice p_nov13 beneath (9 min 45 s), gaps hatched, seconds lost per step. Open "Key and comparison". Optionally press Play.
- **Voiceover.** "Two people, the same task. The ribbon puts an expert above a novice and prices every gap in seconds. Two controls check that the gap is real: expert against expert comes out at 7 seconds, shuffled labels at 46, the real gap at 230. All synthetic, and the screen says so."
- **Hold on screen (4 s).** "Novices lose about 3 min 50 s per case", "Example data", the work ribbon with its legend.
- **Proves.** The work genome, the controls, intervals. Numbers (synthetic, 24 people, `evals/report.md`): real gap 229.6 s [192.7, 272.6]; expert against expert 7.1 s [-2.8, 18.4]; shuffled-label null 46.2 s [-36.4, 116.9]; permutation p = 0.001. Do not say it generalises: on three harder synthetic generators precision falls to 48 to 71 percent (M13 says so).
- **Data.** `/genome/t_entitlement_check` (default case). Audit link `GET /genome/t_entitlement_check`.
- **If it fails.** The page has fixtures that render offline: reload; say "synthetic" either way.

### M3. Hey Knack (18 s)

- **Screen.** Knack window on Home, the owner's face not needed. Take B.
- **Actions.** The owner says "Hey Knack". The pill shows "Listening", a soft chime, Knack speaks. First time only: two cards ("Talk with Knack?" then "Knack may look at your screen while we talk", each Yes, Not now, Never: the owner clicks Yes with the mouse; a key or the voice never answers). The owner asks: "Where do I see what needs me?" A ring and a ghost cursor go to "Needs you" in the sidebar. It never clicks.
- **Voiceover.** (The owner's own voice and Knack's reply are the audio. The editor adds, over the first seconds:) "You wake it by name. It listens on this Mac only. When I ask where, it shows me. It points; it does not click."
- **Hold on screen (3 s).** The pill "Listening" then "Speaking"; the ring on "Needs you".
- **Proves.** On-device wake word (macOS speech, no transcript), Live voice session with a code-built context packet, the ring and ghost cursor guidance. Target: Wordsmith (a spoken, screen-aware workflow). Honest limits to print in the video description: the matcher was measured on text only (1 false accept in 159 held-out sentences, 0 misses in 25); real-microphone behaviour is not measured.
- **Data.** Live mode (Gemini key in `.env`), `UNDERSTUDY_X_LIVE` and `UNDERSTUDY_X_WAKE` on, consent cards answered Yes once (frames only after "Yes"; never from a denylisted app; held in memory for one call). The context packet carries the screen id, pending approvals and the coach step; **it does not yet carry the top Home insight** (gap G1 in section 6), so do not ask it "what is my insight".
- **If it fails.** Hold Option-Space and talk (hold-to-talk). If the microphone prompt was refused, say nothing about it and cut M3 (the main cut works without it). Wake and talk are not in the audit's reach: they are the owner's check.

### M4. The coached case (28 s)

- **Screen.** The worker's Chromium (calculator A) at the left, the Knack ring drawn over it. Take C.
- **Actions.** The lead runs `demo-worker.mjs --scene coach --pace slow` (section 7.2). A script plays a teammate on case CASE-1005 (one adult, 36, earns 250 a month, rent 480, one bedroom, savings 12,000; GovCalc 638, Quick Estimator 742.64, EntitledTo 638.24): four question pages typed at human pace with a visible cursor, the result, then the teammate goes to the case-note tab without opening "Check cliff edges" and comes back. About 4 s later the coach rings that button once with a one-line note, the teammate reads it for 7 s and presses it; the panel lists which edges are near; the note is saved as a draft (never submitted).
- **Voiceover.** "A teammate, played by a script, skips the check that matters. The coach does not give the answer. It rings the skipped step once, at the first level of help, then goes quiet. In replay it rang all 14 planted skips and never prompted an expert. A planted skip is a test, not a result."
- **Hold on screen (3 s).** The ring on "Check cliff edges"; the one-line note. Label bottom-left: "Played by a script on our sandbox".
- **Proves.** The live coach brain (code decides, no model), the ring on the real control, fading help levels. Numbers (synthetic replay): 14 of 14 planted rings, 0 expert prompts, 48 cases (`docs/FEATURE_CATALOGUE.md`, claim C60).
- **Data.** The worker script sets the engine's study mode to the first help level on the cliff skill for the run (the demo person is past it) and clears it at the end, even after a crash; say so in the video description, not in the voiceover. Audit links `GET /coach/next?dry=1`, `GET /study/mode` (must be clear before and after).
- **If it fails.** If no ring after 20 s, the audit line `GET /coach/next?dry=1` says why (the script's own timeline prints "coach decides annotate" when the engine decided). Fallback: show Knack's Today strip ("More, Live coach") and say "the overlay isn't drawing, here is the coach's decision". Never improvise a real click.

### M5. Cue, the stuck rescue (18 s)

- **Screen.** Same worker window, case note page. Take C, straight after M4 (the script waits 125 s by default for the coach's quiet period; the editor cuts the wait).
- **Actions.** `demo-worker.mjs --scene stuck` (part of `--scene both`): a second case (CASE-1006) in the expert's order, then the teammate fills in the case note and hovers over it without saving. About 50 s into the stall Cue shows its cue, "Read the note back", with its one reason, "Reading it back catches copy slips." The teammate takes the step and saves a draft. Then silence.
- **Voiceover.** "Now they stall. Cue offers one cue and one reason, then goes quiet. It is rules and counts, not a model. On simulated workers it kept false nudges under one an hour, 0.73. It did not make them faster to resume: the median difference was zero."
- **Hold on screen (3 s).** The Cue card text; then "Cue: simulated workers" on the lower third.
- **Proves.** Cue stuck rescue (path prior, gate with hard caps, tiers, fades). Numbers (simulated workers, 40 personas, 481.5 hours): false nudges 0.73 an hour (97.5% interval 0.64 to 0.83; target at most 1.0: met); faster to resume not met (median paired difference 0.0 s, exploratory mean -34 s [-43.7, -25.2]); cues reached 28 percent [25.1, 30.1] of stuck episodes. Say the "not met".
- **Data.** Audit link `GET /cue/next?dry=1`. Cue fires only at a step where the person's own level is not 4 (the demo person is at L4 on the cliff step, so a stall there stays silent by design: that is why the stall is on the note).
- **If it fails.** Cue is a soft check in the script (it prints a WARN, exit 0). Fallback: skip M5 and say nothing; or ask Knack by voice for help (a worker who asks bypasses the gate).

### M6. A routine, one opt-in at a time (14 s)

- **Screen.** Needs you, then Routines.
- **Actions.** Needs you: the first screen already holds the approval, a prepared action "Automate: Enter the household into three calculators. It came up 58 times, about 92 minutes a week." (its "Approve and run" only creates an item for your approval: the line "Creates an item for your approval. Nothing runs until then." is printed under "Details") and two more. Press "Show all 7": the routine proposal "Enter the household into three calculators, new routine. Seen about 58 times in 3 weeks. Could save 4 to 7 hours. Touches GovCalc, Quick Estimator and 2 more. It will never: submit, submit to claimant record." with three equal buttons "Watch first", "Not now", "Never" and "More ways to say yes". Press "Watch first" (nothing runs; "Watch first: it practises beside you. Nothing is saved or sent."), then on the same row (or later) "More ways to say yes", "Run with my approval" ("it works in the background and asks before anything outward"). The routine appears under Routines, "Running 1", "Asks first", with a "Run now" button. The same list also holds "Practice run differed from yours: Calculator B gave 214 where your entry gave 241. Nothing was saved. [Accept its answer] [Keep mine] [Evidence]": that is shadow mode comparing the agent with the worker, worth one second of screen.
- **Voiceover.** "The repeat finder saw the same household typed into three calculators fifty-eight times in three weeks. Nothing runs until I say yes, one level at a time. It will never submit."
- **Hold on screen (3 s).** The proposal row with "It will never: submit"; the three equal buttons Watch first, Not now, Never.
- **Proves.** Routine finder, opt-in, trust ladder (rung A0 to A2), the consent text. Numbers (synthetic): after the gate 6 of 6 proposals were planted routines on the first generator; raw cluster precision 22 percent, and 44 to 97 percent on three harder generators (say "depends on the generator").
- **Data.** `/routines` (2 proposed, compiled bundle for `calc-entry-3x`), `/queue` (the shadow mismatch item); Audit link `GET /routines`. The skill gate passes for the seeded person (L4 on the routine's skill), so no override is needed. Verified in a headless render of the merged dashboard on the seeded home (the rows and buttons above are what it printed); pressing the buttons through the dashboard's proxy set the routine to "Asks first" and a run could be started (below).
- **If it fails.** The same choice is under Routines, "Could automate" (the peek has "Watch first"). If a skill gate card appears, read it aloud: it is a feature.

### M7. The agent works, the pill shows (22 s)

- **Screen.** Routines (Running 1), then the agent's own Chromium windows across the screen, the pill bottom-right. Take D.
- **Actions.** Press "Run now". Three navigators work calculators A, B and C in parallel and a scribe writes the case note, all from the compiled routine (tier 1, no model call on the clean path). The corner pill reads "Working on it" with Stop. **The Knack window does not move itself**: it minimises on its own only for a run on the worker's real screen (the desktop's act-for-me), not for a run in the agent's browser. For the video the owner presses Command-M right after Run now (the window goes to the Dock and the pill and the three agent windows are what is left), or leaves it open; see gap G3 in section 6.
- **Voiceover.** "Now the agent does the repetitive part: three calculators in parallel, in its own browser, through the same eight safety layers. The corner pill says what is happening, and has a Stop."
- **Hold on screen (3 s).** The pill "Working on it" and the three windows.
- **Proves.** Background agents, the corner pill, "n of m" progress, tier 1 compiled routine, the security layers. Target: Wordsmith (a multi-site browser workflow). Numbers (language model on our sandbox, headless; not a rate): clean path 20 of 20 in mock, live 18 of 20 with 0 false claims; held-out computer use clean 1 of 4 completed, injected 20 of 20 paused (M13 repeats the first). The run in this scene is the compiled routine, which is not the computer-use model.
- **Data.** Stack headed (`UNDERSTUDY_AGENT_HEADED=1`), sandbox reset, consent mode approval. Audit links `GET /routines` (driver compiled), `GET /health (sandbox sites reachable from the agent)`. A mock run finishes in a few seconds; a headed live run takes longer: time it in rehearsal.
- **If it fails.** If "Run now" answers "not started: sandbox busy", another run holds the lock (`/health` of the agent says); wait or stop it. If the agent windows do not appear, the stack was not started headed: say nothing, the pill and the next scene carry it.

### M8. The irreversible step waits for me (24 s)

- **Screen.** The pill turns to "Needs your OK", a corner card above it, then the Knack window on the item, then Chrome on the case note. Take D.
- **Actions.** The run ends at the designed gate. The corner card reads "A run is waiting for you. It needs your approval to go on." The owner clicks "Review": the window opens on Needs you. The new item is on top: "Submit case note CN-xxxx ... The agent stopped before submit. Cannot be undone. [Approve and submit] [Reject] [Evidence]". Open "Evidence": screenshots, what was extracted, what was expected, the diff. The owner clicks "Approve and submit" with the mouse. In the case-note window (`scripts/demo-open.sh --only casenote` opened it; the note id is in the item title) refresh: "Status: Submitted. This note is now part of the claimant record and cannot be withdrawn." (sandbox only). **Wiring gap G11 (found by running it): today the click only marks the queue item approved; the sandbox note stays "Draft" because nothing in the dashboard or the desktop calls `POST /agent/run/<run_id>/finalize`, the route that presses the real submit button for an item the worker approved.** Verified on a private stack: approve left the note Draft with 0 submissions; calling finalize through the dashboard's proxy then gave `{"submitted": true, "reason": "approved by the worker"}` and the note read Submitted, 1 submission. The fix belongs in the approve path of Needs you and the Home approval row (after a successful approve of an item that has a `run_id`, call finalize and tolerate a 409 for the seeded item, which has no live run). Until it is wired, either skip the "Status: Submitted" shot (end M8 on the approved item) or have the lead call finalize through the proxy (`POST http://127.0.0.1:5173/agent/run/<run_id>/finalize`) right after the owner's click, which is the designed second half of the same approval.
- **Voiceover.** "It stopped before the one step that cannot be undone. The evidence is in plain view. I approve with a click: no key and no voice can. In every held-out run the designed Submit waited for a human."
- **Hold on screen (3 s).** The card, the consequence line "Cannot be undone.", the evidence list, then "Status: Submitted" on the sandbox page.
- **Proves.** Approval queue, the gate on the real submit button, evidence, code decides done. Numbers (language model on our sandbox, headless): the designed Submit waited for a human in all 4 clean held-out runs; 0 submissions without approval; in 2 runs the harness accepted a wrong calculator B input and only an independent recomputation caught it (say so in M13).
- **Data.** A pending irreversible item (the run creates one; the seed has another with no live run behind it: approving it only marks it approved, finalize answers 409). Use the item the run created. **Do not press Approve on the seeded CN-2041 in front of the camera if you want it for the teaser.**
- **If it fails.** If the card does not show (it is content-protected unless `ALONGSIDE_OVERLAY_CAPTURABLE=1`), open Needs you by hand: the item is there. Never approve more than one item per take.

### M9. Growth (14 s)

- **Screen.** Knack, Growth.
- **Actions.** Open Growth. The curve of the share of steps finished without an accepted cue, with its band; "Latest: 75% finished with no cue accepted"; "Baseline 1 of 5". Open "About this data" if time allows.
- **Voiceover.** "Growth measures help needed, not expertise. On this simulated learner, unaided steps went from one in five to three in four, and the screen still says cannot tell yet: we would rather under-claim."
- **Hold on screen (4 s).** The title "Cannot tell yet whether you need less help", the badge "Example data", the printed limit "Measures help needed, not expertise."
- **Proves.** The independence score with Wilson intervals, offloaded work never counted, an engine that refuses to overclaim on its own demo data. Target: HRT (a decision under uncertainty, stated as such). This is simulated data labelled `synthetic_learner`; it is not a result about people. **Do not "fix" the title.**
- **Data.** The seeded Growth ledger. Audit link `GET /growth`.
- **If it fails.** If the screen shows "Your curve starts after 10 steps", the seed did not run with the new Growth step: re-run the demo seed with `--reset`.

### M10. Repeats and Needs you (optional, 8 s)

- **Screen.** Routines, "Could automate 2"; then Needs you count in the sidebar.
- **Actions.** Show the two repeats ranked by minutes saved; point at "Needs you 3".
- **Voiceover.** "Repeats you could hand over, ranked by the minutes they would save. And one list for everything waiting on me."
- **Hold on screen.** The rows. **Proves.** Repeat list (hit list), the single decisions list. **Data.** `GET /hitlist`. **If it fails.** Skip.

### M11. The firm view (admin) (14 s)

- **Screen.** Knack, account menu, "View as Admin", then Firm, Roles, Onboarding.
- **Actions.** Account menu (bottom of the sidebar), View as Admin. Firm: "60 people, 3 roles. 57 have enough data for a trend." Roles: Benefits processor experts 94% (92 to 97%), n = 7; juniors 63% (59 to 67%), n = 22; gap 32 points. Onboarding: "Half reach the target by step 82 (56 to 109)" against a dashed design target of 80%.
- **Voiceover.** "For a manager: expert against junior per role, with intervals, and how fast people reach independence. The names are made up, the firm is synthetic, and the screen says it is for coaching, not for evaluating individuals."
- **Hold on screen (4 s).** "Names are made up. This firm is synthetic." and "For coaching and onboarding, not for evaluating individuals."
- **Proves.** Admin role, insights engine (reliability gate, k-anonymity, "nothing stands out" is a valid answer), onboarding speed. Target: G-Research. Numbers (synthetic firm, 600 synthetic people in the evaluation): false worker insights 0.0037 per person-week [0.0027, 0.0047] on held-out; planted effects missed on dev and again on held-out (independence rise selected in 47 of 100 worlds against a target of 0.8). Say "a development set missed several targets; the held-out run repeated them".
- **Data.** `/insights/admin/*` via the proxy. Audit link `GET /engine/insights/admin/firm (proxy adds the token)` and `GET /insights/admin/firm` (the gate must refuse without the token).
- **If it fails.** If Firm answers 403, the dashboard is on a different data directory from the services; restart the stack. Switch back to Worker view after the take (account menu).

### M12. Forecasts (11 s)

- **Screen.** Knack, More, Forecasts.
- **Actions.** The reliability diagram of the stuck forecast: dots on a dashed line, "mean gap (ECE): 0.013 (0.011 to 0.020)", "In 6 of 7 bands with 30 or more cases, the forecast is within 5 points of what happened. From about 62% up it runs high", "not validated on real people".
- **Voiceover.** "A forecast must mean what it says. This one is calibrated on held-out synthetic people to 1.3 points, runs high above about 60 percent, and is not validated on real people."
- **Hold on screen (4 s).** The diagram, "Synthetic, not measured from real people", the ECE line.
- **Proves.** ML v2 stuck forecast, held-out single frozen run, intervals. Target: HRT (predictions and decisions). Numbers (synthetic, n = 32 held-out people): ECE 0.013 [0.011, 0.020]; accepted v2 (gradient boosting, monotone, Platt-calibrated) beats v1 by -0.0039 nats [-0.0062, -0.0017] (99.3% interval); under a different generator the plain time-since-progress rule beats v1 by -0.021 to -0.030 nats. Say that last one in the honesty cut.
- **Data.** `/hazard/*`, `/eval/report` (fixtures render offline). Audit link `GET /hazard/p_nov03`.
- **If it fails.** The screen has fixtures; reload.

### M13. Evidence: what did not hold up (22 s)

- **Screen.** Knack (or Chrome via `scripts/demo-open.sh --only evidence`), More, Evidence.
- **Actions.** Open Evidence. Scroll the map (33 of 35 sections have results, 2 not run), then the Findings. Stop on three: the agent's held-out result, the stuck model not transferring, the simulated study at the floor. End on "206 limits are listed at the end".
- **Voiceover.** "We also show what failed. On held-out households the computer-use agent finished one of four, and its own harness accepted wrong figures in two. The stuck model's edge was mostly our generator. The simulated study sat at the floor. The live study has not been run."
- **Hold on screen (5 s each, 3 cuts).** "1 of 4 passed the code check"; "advantage ... 0.071 ... 0.008 to 0.015"; "30 of 32 ... at the floor".
- **Proves.** The Evidence page and `make eval` (every number has n, split, interval, origin); honest reporting. All three targets. Numbers (all labelled in the report): held-out clean n = 4: 1 completed (Wilson 0.05 to 0.70), 2 false claims, 0 submissions, language model on our sandbox, earlier model; stuck model: synthetic, 3 generator families; simulated study: language-model participants, not people, +0.094 [-0.051, +0.239], exact p = 0.5.
- **Data.** `/eval/report` (generated 21:40 UTC, mock; if a later `make eval` ran, re-read the numbers). Audit link `GET /eval/report`.
- **If it fails.** Open `evals/report.md` in a viewer and read the same rows.

### M14. Privacy (optional, 8 s)

- **Screen.** Knack, Your data, "What it looked at or sent".
- **Actions.** Open the section: in live mode the rows of the voice session and glances (size, short hash, model, latency; never the picture); in mock mode "Nothing sent". Show "Delete everything" exists (do not press it).
- **Voiceover.** "Every call that leaves the Mac is listed: size, model, time. Never the picture, never the words."
- **Hold on screen.** The list and the scope line. **Proves.** Privacy spine, the ledger, delete beside every item. Number (synthetic canaries, offline): 0 of 11,456 planted tokens reached the model port across 88 runs, upper 95% bound on the leak rate 3.35 percent. Known gap to print: the older desktop paths are off by default and not re-reviewed.
- **Data.** `GET /privacy/summary`, `GET /privacy/ledger`. **If it fails.** Skip.

### M15. Stop, the kill hotkey, outro (14 s)

- **Screen.** The pill with a run in progress, then the "Stopped" card, then Home.
- **Actions.** During a run (take E) press Option-Shift-Command-K anywhere, or the pill's Stop. The pill says "Stopped"; the card stays until Resume. Press Resume. Cut to Home.
- **Voiceover.** "One key stops everything, from any app: Option, Shift, Command, K. Knack: it shows where a novice loses time, coaches with help that fades, and does the repetitive part only when you say yes."
- **Hold on screen (4 s).** "Stopped"; then the Knack mark and the line "Synthetic data. Simulated participants. Four teammates, not run."
- **Proves.** The kill flag (file and hotkey), supervisor stop, the first-class Stop everywhere. **Data.** None (a run in progress). Audit link `GET /kill` (must read clear before and after).
- **If it fails.** The sidebar Stop button and the menu bar do the same. Press Resume before the next take.

### M16. The supervised click (R1), optional

- **Screen.** TextEdit with one empty document, the Knack corner card "Click for you? Allow once, Cancel".
- **Actions.** Only if the owner has run the R1 command and the rung record exists: Hey Knack, "Click that for me"; the ring; the card; the owner clicks Allow once with the mouse; one click on TextEdit's ringed spot; the pill "Done". Until the record exists the model says "I will show you instead" and clicks nothing, and `POST /desktop/click` is not built (the audit lists it as expected, closed by design).
- **Voiceover.** "It can click when I say so, but only after a supervised first run, and only when I click Allow. Voice alone is never consent."
- **Proves.** The gated real-click path (D50, D52): arm switch, RunPermit, countdown, kill. **Not run by this work.** Use only if the owner asks; otherwise omit and say nothing about it.

---

## 4. Extra cuts

### 4.1 Launch teaser, 60 seconds

| # | Shot | Length | Voiceover (about 150 words in all) |
|---|---|---|---|
| T1 | M1 Home, window opening | 6 s | "Two people do the same job. One is slower, and nobody can see where." |
| T2 | M2 ribbon, one hover | 9 s | "Knack shows it: an expert above a novice, every gap priced in seconds." |
| T3 | M4 the ring landing on Check cliff edges | 9 s | "It coaches on the real screen, one ring, help that fades." |
| T4 | M5 Cue card then silence | 6 s | "It steps in when you are stuck, then it is quiet." |
| T5 | M7 three agent windows and the pill | 10 s | "It does the repetitive work, only when you say yes." |
| T6 | M8 the approval card and the click | 8 s | "And the step that cannot be undone always waits for you." |
| T7 | M13 "1 of 4 passed the code check", then the Knack mark | 12 s | "We show what failed. Knack. Synthetic data, simulated participants, four teammates: not run." |

### 4.2 Technical honesty cut, 2 minutes (Evidence first)

H1 (20 s) M13 as above. H2 (20 s) the Genome controls: placebo 7.1 s, null 46.2 s, real 229.6 s, then "on harder generators precision 48 to 71 percent, recall 49 to 68". H3 (20 s) Forecasts: ECE 0.013 and "time-since-progress beats v1 under a different generator (-0.021 to -0.030 nats)"; ML v2 held-out: expert envelope and counterfactual rejected as harmful (+3.81 s [+2.30, +5.19] and +1.17 s [+0.44, +1.87]), only learned substitution costs accepted, a marginal 5 percent gain. H4 (20 s) the attention router: 11 of 12 pre-registered criteria met, criterion 7 not met (later-day can-wait toasts 0.92 to 1.25 a day, the wrong way); against show-everything 0.150 [0.141, 0.159] versus 1.512 [1.447, 1.582] non-safety interruptions per flow hour; simulated workers. H5 (20 s) Cue: false nudges met, faster to resume not met. H6 (20 s) Privacy and gates: 0 of 11,456 canaries, 0 of 42 scripted attacks with every layer on (0.0% [0.0, 8.4]) against 100% all off, but the real-model red team intervals overlap (0 of 126 against 5 of 126), so it measures the cost of the layers, not proof. Close: "Live study: not run, n = 4. Simulated study: at the floor."

### 4.3 30-second target cuts

| Target | Shots | Voiceover |
|---|---|---|
| **HRT: predictions and decisions** (30 s) | M12 reliability diagram (8 s), M5 Cue gate with its hard caps (7 s), M9 "cannot tell yet" (8 s), M13 "the baseline beats v1 under mismatch" (7 s) | "Predictions you can check: a stuck forecast calibrated to 1.3 points on held-out synthetic people, an alarm budget that holds on its own generator and breaks on a harder one, and a growth score that says cannot tell yet. Decisions made by code with hard caps, every number with its interval." |
| **G-Research: make the invisible visible** (30 s) | M2 ribbon and controls (12 s), M11 Roles and Onboarding (10 s), M14 ledger (8 s) | "The gap between an expert and a novice, priced in seconds with its controls. The firm view with intervals. And a ledger of every call that left the machine. Invisible work made visible, and the limits printed beside it." |
| **Wordsmith: a complicated browser-use workflow** (30 s) | M6 opt-in (6 s), M7 three calculators and the pill (12 s), M8 the approval and the submitted note (12 s) | "A real multi-site workflow: the same household entered into three calculators in parallel, reconciled, a case note written, and the one irreversible step held for a human click. Eight safety layers, a hash-chained audit log, and a stop key that always wins." |

---

## 5. Capability coverage (nothing in the catalogue that can be shown safely is missing)

| Capability (docs/FEATURE_CATALOGUE.md) | Scene |
|---|---|
| Work genome, controls, gap decomposition | M2 (decomposition: Genome "Key and comparison") |
| Stuck model, fading help levels, dignity gate | M4, M5, M12 |
| Live coach, on-screen annotations | M4 |
| Cue stuck rescue; independence score and Growth | M5, M9 |
| Wake word and Live voice; ring and ghost cursor | M3 |
| Awareness (on-device cues; glances only with consent) | M3 (consent card), M14 |
| Routine finder, Watch first, approval, trust ladder | M6, M10 |
| Background agents, corner pill, security layers, approval queue | M7, M8 |
| Overnight automations, morning report | M1 (queue, "Since you were away" line in Needs you) |
| Repeat list; one decisions list | M10 |
| Firm view, roles, onboarding speed (admin) | M11 |
| Forecasts, ML v2, calibration | M12 |
| Evidence, limitations, simulated and live study status | M13 |
| Privacy ledger; delete beside every item | M14 |
| Kill hotkey, supervisor stop | M15 |
| Real clicks (R1) | M16, optional |
| Not shown on purpose | the Outlook calendar (a real account: aggregate-only check needs the owner's go at run time; the calendar layer is shown only as synthetic in Genome-side screens), Git habits and the programmer pack (mention in the voiceover of M11 if wanted: thin, not validated), computer use as the model-driven actuator (M13 states its held-out result) |

---

## 6. Context audit: what each model-facing or voice-facing surface is fed

Rules (docs/CONTEXT_ENGINEERING.md): typed first (ids, enums, counts built by code), trust by audience, stable first and volatile last, bounded, fresh or named, measured. The audit read the merged code at main `a132d54` and the branches that landed after; claims marked "unverified" were not run. Detail per surface is in `docs/knack-demo/context-audit.md`.

| Surface | Context it is fed | Built by | Bounded how | Gap |
|---|---|---|---|---|
| Home hero text | No model. A fixed template over an engine pointer (pack skill label, seconds, k of n) | engine `insights/texts.py`, dashboard `screens/Home/model.ts` | worker headline lint 40 words in tests; 16-word and one-quantity rules only in `Home/model.test.ts` over fixtures | G4: 8 of 11 pointer kinds are not matched by the hero's three shapes, so a raw 20 to 40 word headline can render (`trade_off` carries two quantities by construction). The seeded kind (`time_loss_habit`) is fine |
| Corner pill and cards | No model. Seven fixed pill words, "n of m" integers, a fixed approval card ("A run is waiting for you"), fixed attention texts | `knack/pill-state.ts`, `knack-shell.ts`, `attention-wiring.ts` | closed lists, 5-word budget test, hold rules for secure input and sharing | G6: the approval card carries no queue id or count, so Review cannot name the item (unverified how Needs you handles it) |
| Live voice session (Hey Knack and the talk key) | Static system instruction; mic audio; one frame at most every 5 s with no text beside it (only after the Yes card, never from a denylisted app); a code-built context packet; tools `point_at`, `clear`, `show_step`, `ask_choice`, `end_session`, `do_it_for_me` | `live/prompt.ts`, `live/manager.ts`, **`wake/context-packet.ts`, `wake/context-source.ts`** (new on main), `index.ts` binds them | packet is enums, ids and counts under closed grammars, 1400 characters at most, each reading carries the time it was taken and a freshness limit (screen 60 s, insight 1 h, approvals 60 s, routine 30 s, coach 60 s, cue 20 s); a stale or missing kind is named under `unknown`; frames older than 4 s are dropped; session at most 5 minutes | **G1 (real): the top Home insight is never reported.** `reportInsight` exists in `dashboard/src/lib/wakeContext.ts` but no screen calls it (Home does not), so `home_insight` is always `unknown` and the voice cannot say what the week's insight is. **G2:** the routine is reported only for a run started with Run now from Routines (`trackRoutineRun`); a run started elsewhere stays unknown. **G5:** the help level and the "run is working" state are not in the packet (the voice session ends when an agent starts acting, by design), and nothing in the packet carries the Needs-you item kinds (blocking or not) |
| Cue | No model. Rules and counts; a path prior from expert data, gate with hard caps (3 per 10 min, one question, 90 s per skill); the one model result it reads is a grounding answer | engine `cue/live.py`, `cue/context.py`, `cue/freshness.py` | window 120 cogs, snapshot 60 s, p_stuck 6 s, grounding TTL 20 s | G7: nothing outside fixtures calls `POST /cue/grounding`, so the engine's grounding input never runs live; the desktop grounds by DOM only |
| Coach brain | No model. Cogs from capture events, pack step policy, hazard p_stuck, dignity gate; wording from pack templates | engine `coach/brain.py`, `coach/messages.py`; desktop `coach-brain.ts`, `coach-poller.ts` | one poller only (polling advances the gate); ring text cut to 40 characters on screen | `CoachStateInfo` carries no timestamp (freshness cannot be applied to it) |
| Evidence explainer | One typed `EvidencePacket` plus an intent enum (question words never reach a model); local Qwen first; Gemini only if `UNDERSTUDY_EVIDENCE_CLOUD=1`, through the egress guard; template fallback | engine `evidence/explain.py`, `evidence/packet.py` | `SafePayload` cannot hold free text; prompt budget 2500 tokens, fixed trim order; every number in a reply must trace to the packet | none found. The check proves traceability, not truth |
| Agent runs, tier 1 | No model (compiled routine) | `tiers/*`, `routines/<id>/steps.json` | n/a | none |
| Agent runs, tier 2 and 3 | Planner: goal, reader fields, state, element labels capped at 48 characters and wrapped as untrusted. Reader: raw page text up to 20,000 characters, untrusted, schema-checked output. Tier 3: goal and fact handles (never values), working memory, one frame, `store=False` | `tiers/browser_agent.py` (`tier2_messages`), `tiers/computer_use.py`, `context/` library | trust by audience raises on violation; tier-3 prompt flat at about 2.76k tokens per step (n = 1, live) | docs lag the code: the reader memo and the meter manifest are built now. The memory file is in no model prompt (G8) |
| Wake word | The helper prints only `ready`, `heard` or a closed error code; any extra field stops it; no transcript, no audio to any model. On `heard` the controller calls the Live start with no arguments | `wake/helper-protocol.ts`, `wake/controller.ts` | closed enums, dormancy guards re-read every 3 s | none |
| Awareness glance and pointing | One frame plus a trigger enum plus an app-kind enum; closed answer (app kind, task phase, blocker, confidence, box). Pointing: the Live model's own 60-character description (URL, email and number filtered) becomes the one menu label | `awareness/glance.ts`, agent `models/routes.py` | four gate booleans checked on both sides; frame wiped after the call; ledger row before the send | G9 (low): the point label is model text from untrusted pixels, bounded and scanned, in a registered purpose |
| Attention router and briefing cards | Router: event enums plus worker-state booleans, wording by template. Cards: an optional reword of one display line with generalised numbers, refused if numbers differ | `attention/router.py`, `proactive/reword.py` | `worker_state` 10 s, card TTL 24 to 72 h | doc: the freshness table says 3600 s for cards, `cards.py` says 24 to 72 h |
| Spoken lines (ElevenLabs) | A fixed line id plus bounded typed slots; free text is a 422 | agent `voice/lines.py` | closed vocabulary, personal-data filter on the finished sentence | none after the four `wake.*` lines were added (a parity test reads the desktop's list); the Live model's own speech is free audio inside a bounded session (documented exception) |
| Memory file | In no model prompt. Read by rules and the coach only; `retrieve` (keyed, capped at 6 lines) is built and tested, adopted by nobody | `context/retrieval.py` | n/a | G8: the claim "adapts to the worker" rests on rules (levels, preferences, rungs), not on any prompt. Say "rules", not "the model remembers" |

### 6.1 The gaps, exactly, for the lead

1. **G1, the Live packet misses the top Home insight.** `apps/dashboard/src/lib/wakeContext.ts` has `reportInsight(id, template)`; `screens/Home/*` never calls it. One call where Home settles on its hero (id from the pointer's `id`, template from the pointer's kind) fills `home_insight`. Everything else in the packet is wired on main (`index.ts` builds the hub, passes `context` to `registerLive`; screen id comes from the focused Knack window's URL; approvals from the HUD count; coach step and zone; Cue state; consent words; rung record; data mode).
2. **G3, the window does not minimise for a sandbox run.** `knack/activity.ts` sets `realScreen` from `signals.local`, which is true only for the desktop's own act-for-me; a routine run in the agent's browser shows the pill and does not move the window. The owner's wish ("the window minimises to the corner pill while the agent works across three calculators") needs either a decision to set `realScreen` for a run the worker started from the window, or Command-M by hand in the take. This is the shell owner's call; the shot list works either way.
3. **G6, the approval card names no item.** `APPROVAL_CARD` has fixed words only; Review opens the window on Needs you (the newest item is on top, so in the demo the right item is first).
4. **G4, hero shapes.** Only three pointer shapes match the hero template; the other worker kinds would render their raw headline. Not hit by the seeded data.
5. **G7, the engine's grounding input is dead outside fixtures** (no caller of `POST /cue/grounding`).
6. **G8, the memory file is in no prompt.** Honest wording only.
7. **G10, the two doc lags** in `docs/CONTEXT_ENGINEERING.md` (reader memo and manifests are built; the freshness table has no rows for queue count, run state, help level, screen or insight).
8. **G11, approving does not submit.** See M8. `POST /run/{run_id}/finalize` exists, works (verified), and has no caller in `apps/`.
9. **Seed and wake:** `POST /desktop/click` is unbuilt by design (the audit reports it as expected, closed by design); the Ask bar has no specified model path yet.

---

## 7. What was verified, and what needs the owner

### 7.1 The tools (all in this repo, all read-only toward the stack under test)

| Tool | What it does | Verified |
|---|---|---|
| `scripts/link-audit.mjs` | `node scripts/link-audit.mjs [--engine URL] [--agent URL] [--dashboard URL] [--sites URL] [--desktop-ext URL] [--expect live\|mock\|any] [--ingest private\|off\|URL] [--explain] [--json]`. 48 links: engine health, flags (all 11 layers true), agent health (supervisor idle), models status, voice, dashboard and its proxy to both (including the admin token hop), every scene's data, the sandbox, the desktop's extension server and the extension ingest path. Prints PASS, FAIL or SKIP with the method and exact path, never a body, key or token. Exit 1 on any FAIL | against a private stack (engine 17700, agent 17710, dashboard 15173, private sandbox 17801 to 17803, mock): 46 PASS, 0 FAIL, 2 SKIP (the desktop extension server, which needs the app; `/desktop/click`, expected) |
| `scripts/demo-open.sh` | `--only voice,casenote` / `--all` / `--list` / `--dry-run` / `--reset` / `--headed`. Chrome windows placed by Chrome itself (`open -na "Google Chrome" --args --new-window --window-position=X,Y --window-size=W,H <url>`), isolated empty profile by default, no Accessibility needed, prints what it opened, opens nothing unless called | `--list`, `--dry-run`, argument errors and `--headed` tested; **no window was opened** (by design: the owner's screen) |
| `apps/desktop/scripts/demo-worker.mjs` | A Playwright Chromium with the built extension plays a teammate at human pace with no OS input and no frame analysis: coach scene, stuck scene, `--pace slow\|normal\|fast`, `--headless` for checks, `--private` for a throwaway engine, `--engine`, `--desktop-ext`, `--cue-sheet FILE`, holds the sandbox lock, clears study mode and resets the sites on exit even after Ctrl-C | headless against a throwaway engine on the shared sandbox sites: coach scene (engine decides annotate, level L1, trigger expert_policy, zone cliff_button, 3.6 to 4.5 s after the miss), stuck scene (Cue decides "Read the note back" about 47 to 49 s into a stall on the case note), 3 of 3 checks, exit 0, nothing left running |
| `understudy_engine/demo.py` | Seeds the Growth ledger (new) beside the existing home, queue, overnight story, routines, rule proposal and briefing; `make demo` and `make live` call it | 15 seed tests pass, including reset and "written only into the demo data dir" |

### 7.2 Running the worker

```
cd apps/desktop
node scripts/demo-worker.mjs --scene both --pace slow          # the demo: headed, against the live stack at 7700 and the app's extension server at 7720
node scripts/demo-worker.mjs --scene coach --pace normal        # M4 only
node scripts/demo-worker.mjs --private --headless --scene both --gap 20 --cue-sheet /tmp/cues.json    # a rehearsal, no app and no window
```

It prints one line per moment with a time since the start (the editor's cue sheet; `--cue-sheet` writes the same as JSON; a sample from the verified rehearsal is `docs/knack-demo/worker-cue-sheet.example.json`) and a summary; exit 0 when it ran to the end and the engine decided to ring. Default window 1180 by 760 at 60,60 (`--position`, `--size`); a visible teammate cursor is drawn in headed mode. It never presses "Submit to claimant record", never calls `/kill`, never reads or writes the checkout's `data/`.

### 7.3 What needs the owner at the demo (nothing else does)

1. Allow macOS Microphone and Speech Recognition (Hey Knack), Screen Recording and Accessibility (the ring, the glance).
2. Answer the two Hey Knack consent cards with the mouse (Yes).
3. Hold the real clicks: the approval in M8 and, only if wanted, Allow once in M16. No key, voice or script can answer these.
4. Press begin and stop on the recording (the lead runs `scripts/record-demo.sh`).
5. Watch that the ring, the pill, the cards and the Cue panel are visible in the recording (section 1.1 step 2), and that the agent's windows are visible (step 1).

Not verified by this work, because no desktop window or real input was allowed: the Knack app itself (window size, the pill, the ring drawn over the worker's Chromium, the Cue panel, Hey Knack, Live voice), headed Chrome placement by `demo-open.sh`, a live (non-mock) agent run, and the real-click path. The worker's engine decisions are verified; their appearance on screen is the owner's first check.

---

## 8. Claims, with their labels (copy these, not the numbers from memory)

| Say | Label | Source |
|---|---|---|
| The work genome recovers planted deficits: precision 92%, recall 95% | synthetic, first generator (16 people); **falls to 48 to 71% and 49 to 68% on three harder generators** | report, deficit recovery and realism |
| Real gap 229.6 s [192.7, 272.6]; expert against expert 7.1 s; shuffled null 46.2 s | synthetic, 24 people | report, controls |
| The coach rang 14 of 14 planted skips and prompted no expert | synthetic replay, 48 cases | catalogue, C60 |
| Cue: false nudges 0.73 an hour; not faster to resume | simulated workers, 40 personas | report, Cue analysis |
| Attention router: 11 of 12 criteria met, criterion 7 not met | simulated workers, 200 | report, attention routing |
| Forecast mean calibration gap 0.013 [0.011, 0.020] | synthetic, 32 held-out people | report, Models v2 |
| ML v2 candidates E4 and Q1 rejected as harmful; time-since-progress beats v1 under mismatch | synthetic, held-out | report, findings |
| The agent finished clean 20 of 20 in mock and 18 of 20 live with 0 false claims | language model on our sandbox, tier 1 off for the live rows | README agent table |
| Computer use on held-out households: 1 of 4 completed, 20 of 20 injected pages paused | language model on our sandbox, earlier model, Wilson 0.05 to 0.70 | report, agentic evaluation |
| 0 of 11,456 planted canary tokens reached the model port | synthetic, offline, 88 runs, upper bound 3.35% | report, privacy layer |
| The simulated study sat at the floor (30 of 32 post-tests scored 0) | language-model participants, not people | report, findings |
| The live study has not been run | n = 4, not run | report, evidence map |

**Lines we do not say.** "Novices become experts." "Coaching improves performance." "Validated", "proven", "works on real users." "Nothing leaves your laptop" (say: every call from our services is listed; in mock mode none left). "The agent works" without its conditions (our sandbox, small n, code decides done). "Real clicks on the desktop" (one supervised click passed on TextEdit; the agent's own actuator failed its first check; real clicks are off until the owner's R1 run). Any Gemini speed or accuracy number (not in the report). That the model remembers the worker (the memory file is read by rules only).
