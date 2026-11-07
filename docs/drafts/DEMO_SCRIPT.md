<!-- DRAFT. Labels and URLs are from the dashboard source on 7 Nov 2026 (15:50 GMT). Anything marked TODO(verify) must be rehearsed once before it is trusted. Say what is synthetic as you go. Never say novices become experts. -->

# Demo script: three minutes

One presenter, one laptop, wifi off, mock mode. Two browser windows side by side: the dashboard (`http://127.0.0.1:5173`) and Chrome with the capture extension on the sandbox calculators. The desktop coach overlay runs on top of Chrome.

## Before you go on (10 minutes)

1. Wifi off. `make demo`. It seeds the isolated demo home (`data/demo-home`: person `p_learn01` at case 24, onboarding done, the `calc-entry-3x` routine proposed, three corrections recorded) and opens the dashboard. Check `curl -s http://127.0.0.1:7700/health` says `"mock":true` and that the engine is the demo one (isolated home).
2. Sandbox state clean: `curl -s -X POST http://127.0.0.1:7801/__reset` (one call resets all three sites).
3. Chrome: open `chrome://extensions`, load `extension/dist` unpacked (after `cd extension && npm run build`), click the Understudy icon and switch **capture on**. Page zoom 100% (the overlay is calibrated at 100% only). Open `http://127.0.0.1:7801/step/1` in one tab. The extension adopts the demo person within about 30 seconds (its popup says "from Understudy").
4. Desktop coach app running. TODO(lead): exact command and the permission state.
5. Teammate card (printed): **CASE-1005**. One adult, age 36, earns 250 a month; renting, rent 480, 1 bedroom; savings 12,000; no children, no childcare, no limited capability. Expected: GovCalc 638, Quick Estimator 742.64 (it ignores capital tariff income), EntitledTo 638.24. The calculators disagree, so the right case note says "Discrepancy".
6. Kill switch visible: the red **Stop everything** button at the bottom of the dashboard.
7. Open tabs in order: `#/onboarding`, `#/genome`, `#/today`, `#/routines`, `#/queue`, `#/presence`, `#/evidence`.

## The three minutes

| Time | Say | Do and show | If it breaks |
|---|---|---|---|
| **0:00 to 0:25 Set up** | "Understudy learns a job from how people do it. Pick a role and answer five questions. It writes a memory file you own." | On `#/onboarding` choose **UK benefits processor**, press **Next** through the five questions (the preview of the memory file on the right fills in), accept the defaults, answer **Yes, record times**, press **Write my memory file**. When "Your memory file is written" shows, press **Try another role**, choose **Data analyst**, and point at the different tools, never-list and tone in the preview. | The demo home is already onboarded: open `#/memory` and show the file. Skip the second role and say it is in the README. |
| **0:25 to 0:55 See the invisible** | "This is the work ribbon: an expert's trace on top, a novice's beneath, the gaps hatched, seconds lost in red. It is synthetic and says so. The placebo, expert against expert, comes out near zero, so this is not an artefact." | `#/genome`: point at the **synthetic** badge, the ribbon, the waterfall with its intervals, the placebo line. Press **Transition graph**: the edges the novice never takes are highlighted. | The page has fixtures behind it: if the engine is slow, reload; the fixtures render offline. Say "synthetic" either way. |
| **0:55 to 1:35 Coach** | "A teammate works a household. They skip the check that matters. The coach does not tell them the answer; it asks a question, and it fades as they improve." | In Chrome work CASE-1005 on GovCalc (`/step/1`). After the result page, **do not** press Check cliff edges: the ring lands on that button with a short question. Press it; the panel says savings are in the tariff band. Cut to `#/today` and show the level chip: next case, lighter help (**I did that** tells the coach what happened). | Show the 20-second recording made before the freeze. Or `#/today` alone: the coach state with the chip lightening. TODO(verify): the ring on a real Chrome tab (task markers emit task_start on the first calculator page; the coach needs it). |
| **1:35 to 2:10 Automate** | "Understudy spotted this person entering the same household into three calculators. It proposes; they choose. Nothing runs without their yes." | `#/routines`: the **Enter the household into three calculators** card: what it does, how often, hours saved with an interval, what it touches, what it never does (submit). Press **Watch first** (shadow mode: practises, compares, saves nothing). Then **Run with my approval**. Switch to `#/queue`: the card for the irreversible step shows the evidence and the tier that ran each step. Do **not** approve in front of the audience unless asked; if asked press **Approve and submit** on the sandbox note. | Cached golden run: the run comes from `data/golden/benefits_golden.json` (mode cached), no model, no network. Queue card is seeded in demo data. |
| **2:10 to 2:40 Away** | "A background run may start only when the chance the person stays away for its whole length beats a threshold. If they come back, it stops within a second." | `#/presence`: the week heatmap with intervals and the free hours; the run-length choices and the window forecast. Press the red **Stop everything**: the dashboard shows Stopped; press **Resume**. Open `#/queue` and show **What ran while you were away**. | The real desktop run is frozen after the S2 follow-up (TODO(lead): retest result). Use the simulated-clock sequence (`GET /offhours/demo`) and the recorded real run. Say so. |
| **2:40 to 3:00 Proof** | "Here is what we can and cannot show. Every number has its n, split and interval; synthetic results carry a badge; the live study is n equals four and not yet run." | `#/evidence`: calibration, risk-coverage, off-policy recovery, the red-team table (attack success with each layer off in turn, false pauses on clean pages), the limitations register, the study marked **PENDING**. Close on the limitations. | Evidence reads `evals/report.json`; if missing, run `make eval FAST=1` before the demo. |

## Lines to keep honest

- Say "synthetic" for the ribbon, the heatmap, the hazard and the red team. Say "n equals four, and not yet run" for the study.
- The calculators are sandbox sites we wrote, and the reference answer is a simplified rule set, not the law.
- "Lifts novices on the skills it coaches" is the most we say. We do not say novices become experts.
- If asked about the real desktop run: one supervised real click passed; the agent's own actuator failed its first supervised check and was fixed behind guards. TODO(lead): current status.
- If asked about data: capture stores no page text, no URLs, no field values; sensitive fields are never touched; everything stays on the laptop.

## After a failure

Press **Stop everything**, say what happened in one sentence, and move to the next row. Never improvise a real action. The fallback for every row is a recording or fixtures that work offline.

## Things not verified by the author of this script

The ring landing on the real Chrome tab end to end; the exact desktop launch command; the real away run; the live study. Rehearse these twice before the freeze.
