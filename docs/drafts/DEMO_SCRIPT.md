<!--
DEMO SCRIPT draft, rewritten 7 Nov 2026, about 19:50 GMT, by the NARRATIVE track.
- Labels, routes and button text were checked against the dashboard source at about 18:00 GMT (apps/dashboard/src). The dashboard is being restyled, so rehearse once before trusting a label.
- Numbers said aloud come from evals/report.md generated 2026-11-07T17:38:00Z (git 1bab986, mock mode). The "Check" line under each beat gives the claim ID in docs/drafts/CLAIMS.md. RE-PULL after the last `make eval` and change the spoken numbers if they moved.
- Time budget: the spoken lines total about 350 words, which is about 140 seconds at 150 words a minute, leaving about 40 seconds for clicks. Longer lines are kept apart, under "If you have time" and "If a judge asks". Do not add words to the main path.
- Nothing here claims more than the catalogue's status words allow. Beats marked CONFIRM exist only as far as the lead confirms them; each has a fallback that is true today.
- [LEAD: ...] you confirm or supply. [OWNER: ...] only the owner can supply.
-->

> **Superseded.** `docs/KNACK_DEMO.md` replaces this script: it was written for Knack's new interface (scenes M1 to M16, with spoken lines, fallbacks and a rehearsal tool). This draft predates the Knack shell, the new navigation (a worker has Home, Needs you, Routines, Growth and Your data; Where time goes and the rest are Growth sections; Evidence and Forecasts are Admin pages) and the Gemini, Hey Knack, task and HRT work, so its labels, routes and numbers are out of date. Keep it only for the beats' reasoning. Updated 8 Nov 2026, about 03:00 GMT.

# Demo script: three minutes

One presenter, one laptop, wifi off, mock mode (`make demo`, the owner's command). Two windows side by side: the dashboard (`http://127.0.0.1:5173`) and Chrome with the capture extension on the sandbox calculators. The desktop coach overlay, if it is running, sits on top of Chrome.

## What is live, what is replayed, what is example data

| # | Time | Beat | What is on screen | Live, replayed or example |
|---|---|---|---|---|
| 1 | 0:00 to 0:20 | The problem and the one-line product | The Genome page, open | Talk only |
| 2 | 0:20 to 0:50 | See the invisible | `#/genome`: ribbon, waterfall, controls | Live from the engine on synthetic data; the page has fixtures that render offline. Badged synthetic |
| 3 | 0:50 to 1:35 | Coach, and Cue **(CONFIRM)** | Chrome on the sandbox, the ring on one button | The coach's decision is live; the overlay on a real Chrome tab is **not yet confirmed end to end**. Fallback: `#/today` |
| 4 | 1:35 to 1:52 | Growth **(standout, CONFIRM)** | `#/growth` | Example data, labelled, unless the lead confirms the Cue layer is on |
| 5 | 1:52 to 2:17 | Automate | `#/routines`, then `#/queue` | **Replayed**: a recording of a mock-mode run on household hh_0004, labelled cached. No model, no network |
| 6 | 2:17 to 2:35 | Privacy **(standout)** | `#/privacy` | Live from the engine's ledger. In mock mode rows carry a "mock" pill and nothing reached a model |
| 7 | 2:35 to 3:00 | Proof and limits | `#/evidence` | Live from `evals/report.json` |

## The standout beats, and what must be confirmed first

| Beat | What exists in the tree at about 18:00 | Catalogue status | Use the full version only if |
|---|---|---|---|
| **Cue** (the one-question rescue) | Engine package `understudy_engine/cue` (ledger, gate, question, teach, routes) and desktop code in `apps/desktop/src/main/cue` and `renderer/cue` | building; evaluation section pending in the report | The lead has seen it end to end on the demo laptop: a stall, one multiple-choice question, an answer, the ring, one reason, then silence. Otherwise use version A of beat 3 |
| **Growth** (how much less help over time) | The screen `#/growth`, with an "Example learner" selector (Improves, Levels off, Early curve, Just started) and an example-data badge | building | It always says "example data" unless the lead has confirmed the assist ledger is wired and the numbers come from simulated learners that the report labels. Never present it as a result about people |
| **Privacy** (what left the laptop) | The screen `#/privacy`: the ledger, a summary, a canary check, the local-model status | built, with a known gap | You say the gap aloud (beat 6, and the Q&A) |

## Before you go on (about 10 minutes; the full list is in DEMO_DAY_CHECKLIST.md)

1. Wifi off. `make stop`, then `make demo`. It seeds the isolated demo home (`data/demo-home`: person `p_learn01`, onboarding done, the `calc-entry-3x` routine proposed) and opens the dashboard. `make preflight` should show no red. Check `curl -s http://127.0.0.1:7700/health` says mock.
2. Reset the sandbox: `curl -s -X POST http://127.0.0.1:7801/__reset` (one call resets all three sites).
3. Chrome, a clean profile with only the demo tabs open (see the checklist for why): load `extension/dist` unpacked (`cd extension && npm run build` first), switch **capture on**, page zoom 100% (the overlay was measured at 100% only). Open `http://127.0.0.1:7801/step/1`.
4. Desktop coach app running, if beat 3 version A is used. [LEAD: exact command and permission state. `package.json` has `npm run dev` (electron-vite) in `apps/desktop`; the flags the demo needs are not known to this track.]
5. The teammate card, printed: **CASE-1005**. One adult, age 36, earns 250 a month; renting, rent 480, 1 bedroom; savings 12,000; no children, no childcare, no limited capability. Expected: GovCalc 638, Quick Estimator 742.64 (it ignores capital tariff income), EntitledTo 638.24, so the calculators disagree and the right case note says "Discrepancy" (source: evals/cases/households_20.json, hh_0005; C66).
6. Kill switch visible: the red **Stop everything** button at the bottom of the dashboard.
7. Tabs open in order: `#/genome`, `#/today`, `#/growth`, `#/routines`, `#/queue`, `#/privacy`, `#/evidence`.
8. **Rehearse the clock.** Time beat 3 with the household entry included. If entering the household takes more than 25 seconds, start beat 3 on the result page of a household you entered while the previous beat was speaking, or take the fallback. [LEAD: say which.]

## The three minutes

You play the novice in beat 3. That is a demonstration, not a study, and you say so. Speak at about 150 words a minute; the lines below are the whole budget.

### 1. The problem and the one-line product (0:00 to 0:20)

**Say:** "Two people do the same job. One is slower and gets a different answer, and nobody can see where. Understudy shows the gap, coaches with help that fades, and does repetitive work only when the worker says yes. All of this is synthetic data, and the screens say so."
**Click:** nothing. `#/genome` is open behind you.
**Mode:** talk. **If it breaks:** nothing to break.

### 2. See the invisible (0:20 to 0:50)

**Say:** "The ribbon: an expert on top, a novice beneath, gaps hatched, seconds lost in red. Two controls, expert against expert at 7.1 seconds and shuffled labels, both include zero. The real gap is 229.6 seconds a case, and its interval does not. Skipping a check looks free in seconds, so we also price it in answers: on 200 synthetic households, 107 would go without a warning."
**Click:** `#/genome`. Point at the **synthetic** badge, the ribbon, the waterfall with its intervals.
**Check:** C03 (229.6 [192.7, 272.6], 7.1 [-2.8, 18.4], null 46.2 [-36.4, 116.9]); C61 (107 of 200). [LEAD: the page's own headline ("Novices lose about ... per case") is for the data shown on the page; if it differs from 229.6 s, say that 229.6 s is the report's average over 24 people and the page shows one pair.]
**Mode:** live, synthetic. **If it breaks:** reload; the fixtures render offline. Say "synthetic" either way. If the page is blank, show the Evidence page's controls block and say the same words.

### 3. Coach, and Cue (0:50 to 1:35)

**Version A, true today.**
**Say (while you work):** "I'm playing a novice on a synthetic household. I skip the check that matters." *(the ring lands)* "The coach doesn't give the answer. It rings the skipped step once, then goes quiet. In replay it rang all 14 planted skips and never prompted an expert. The skip is planted, so that is a test, not a result."
**Click:** Chrome, `http://127.0.0.1:7801/step/1`: enter CASE-1005 from the card, press the calculate button, reach the result page. **Do not** press **Check cliff edges**. When the ring lands on that button, press it; the panel says the savings are in the tariff band. Switch to `#/today` and point at the level and the **I did that** button (it tells the coach what happened).
**Check:** C60 (14 of 14, 48 cases, 0 expert prompts).
**Mode:** the coach brain is live; **the ring on a real Chrome tab is not yet confirmed end to end**.
**If it breaks:** say "the overlay isn't drawing, so here is the coach's decision" and show `#/today` alone (the coach state and level). Then say the 14 of 14 line. [OWNER: if a short screen recording of the ring exists, name it here.]

**Version B, CONFIRM first (Cue).** Use only if the lead has seen this on the demo laptop.
**Say:** "Now I stop. Cue asks one question, not an open one. I answer; it shows the step, gives one reason, and goes quiet. Its numbers so far are from simulated learners, not people."
**Click:** [LEAD: the pause length that triggers the question, the key or click that answers, and the exact on-screen words.]
**Check:** the design is docs/REQ7_PLAN.md section 4; there is no Cue result in the report yet (cue section pending). Do not quote a Cue number unless the report has one.
**If it breaks:** switch to version A without comment and say "Cue is still in progress; here is the coach".

### 4. Growth (1:35 to 1:52) (standout, CONFIRM)

**Say:** "Growth shows how much less help a worker needs, not how expert they are. This is example data, and the screen says so. Whether real people improve is the live study, and we have not run it."
**Click:** `#/growth`. Point at the example-data badge and the interval on the curve.
**Check:** the screen's own copy ("This shows how much less help you need, not how expert you are"). No number here is a result. [LEAD: if the screen is wired to simulated learners, change "example data" to the report's label and add the figure with its n and interval.]
**Mode:** example data. **If it breaks:** skip to beat 5 and say "Growth is in progress; it shows example data".

### 5. Automate (1:52 to 2:17)

**Say:** "In this synthetic history, the same household was typed into three calculators three times, so Understudy proposes a routine. I choose; nothing runs without my yes. This is a recording of a mock-mode run, labelled cached. The last step waits for a click, and this button stops everything."
**Click:** `#/routines`: the card **Enter the household into three calculators**. Press **Watch first**, then **Run with my approval**. Open `#/queue`: the card for the irreversible step shows its evidence. Press **Stop everything**, say "Stopped", press **Resume**.
**Check:** the replay is `data/golden/benefits_golden.json` (mock: true, recorded 7 Nov 15:18); C66.
**Mode:** replayed. **If it breaks:** the queue card is seeded in the demo home; if it is missing, say "the queue holds the card", show `#/queue`, and move on. Do not press **Approve and submit** in front of the audience; if asked, it saves a sandbox case note and nothing real.

### 6. Privacy (2:17 to 2:35) (standout)

**Say, if the ledger is empty:** "Mock mode, so nothing was sent. When the new layers call a model, a line appears here first, exactly as sent. It covers our services, not other software on this laptop, and it does not cover everything; the limits say so."
**Say, if rows with a "mock" pill show:** "These are mock calls and reached no model." Then the same last sentence.
**Click:** `#/privacy`. Point at the title, one row's **Payload, exactly as sent**, the **Canary check** box.
**Check:** C40, C42. The full scope statement is in the Q&A (question 5).
**Mode:** live. **If it breaks:** say the same words over the Evidence page's privacy block, or skip.

### 7. Proof and limits (2:35 to 3:00)

**Say:** "Every number has its n and interval; synthetic results carry a badge. One real-model result: on a one-off error page the agent said it was done in 20 of 20 runs and was wrong every time. The code check caught all twenty, so code decides. The live study has not been run, and we don't claim novices become experts. This is what it doesn't show."
**Click:** `#/evidence`. Scroll to **Does the agent finish the work, and survive a changed page?** and its **Real model, small n** facts, then to **What this does not show**. Stop on the limitations. [LEAD: check that the one-off-error-page row (0 of 20, 20 false claims) is readable in that block; if it is not, read it from `evals/report.md`, section "Agent runs on the sandbox"; see the presentation hazard in CLAIMS.md section 4.]
**Check:** C24, C70.
**Mode:** live from `evals/report.json`. **If it breaks:** open `evals/report.md` in a viewer and read the same row; `make eval FAST=1` rebuilds the report if it is missing.

## If you have time (each about 10 seconds; only if you are ahead)

- Beat 2: press **Transition graph** (the edges the novice never takes are highlighted), then the ribbon toggle. Add: "On 42 of those 107, a small change moves the award by more than 50 pounds a month." (C61)
- Beat 4: press **Levels off** in the Example learner selector. "The screen is built to show a curve that stops falling, too."
- Beat 6: "In our canary test, 0 of 11,336 planted strings reached the model port across 80 runs. Counted by run, that bounds a leak at 3.7%, not at zero." (C40)
- Beat 7: "The simulated study uses language models, not people. It hit a floor, so it says nothing about the coach." (C72)
- Extra beat, `#/presence` (30 s): "A background run may start only when the chance the person stays away for its whole length beats a threshold. On four synthetic personas it interrupted 2.1% of started runs against 24.8% for running whenever idle, and used 74.2% of idle time against 90.2%. The weekly map is worse than a plain baseline for the shift worker." (source: report.md "Presence and window forecast"; C11)

## If you are behind

- At 1:00: skip the household entry (take the `#/today` fallback in beat 3).
- At 2:00: say beat 5 in one sentence ("a routine card, chosen by the worker; the last step waits for a click") and press only **Stop everything**.
- Never cut: the synthetic badge, the glitch result and the limitations.

## Lines we do not say

- "Novices become experts." Not claimed, not measured.
- "Coaching improves performance", "validated", "proven", "works on real users". The live study has not been run; the simulated study hit a floor.
- "Nothing leaves your laptop." Say: every call from the new layers is listed; in mock mode none left.
- "The agent works" without its conditions. Say: on our sandbox sites, small n, and code decides done.
- "Real clicks on the desktop." One supervised click passed; the agent's own actuator failed its first supervised check; real clicks are off.
- Any Gemini speed or accuracy number. The bake-off has not landed in the report.

## If a judge asks

1. **Did you test it with people?** "No. The live study with four teammates has not been run, and with four people the smallest possible exact p-value is 0.125. We ran a simulated study with language-model participants, which are not people, and it hit a floor. Everything else is synthetic." (C70, C72, C16)
2. **Does it click on the real desktop?** "One supervised click and one typed line on TextEdit passed. Our agent's own actuator then failed its first supervised check by clicking another app's window. The guards were rebuilt and an independent review found more; real clicks stay off until it is retested with the owner present. The demo does not use them." (C63, C43)
3. **Why believe synthetic numbers?** "Don't, as evidence about people. They show our methods recover what we planted, with controls: expert against expert, shuffled labels. The next step is the live study." (C01, C03, C17)
4. **What if the model says it is done and is not?** "That happened in 20 of 20 runs on a one-off error page, with a real model. The code check caught all of them. That is why code decides." (C24)
5. **What leaves the laptop?** "In mock mode, nothing. Otherwise every call from our services and the new layers is in the ledger as sent. It does not cover model calls the worker asked for, which are logged as metadata only, and it cannot see other software. A screen frame that is allowed to leave is raw. An independent reviewer found older desktop code that sent screenshots and file text to OpenAI and Gemini; it is off by default [LEAD: confirm]." (C40, C42)
6. **Is Alongside new?** "No. It is the author's earlier open-source library, first commit 31 October, before this event. The README lists what we reused and what we changed, and the safety finding about its real actuator being on by default." (C65)
7. **Who is it for?** "Several jobs through role packs: one deep, a UK benefits processor, and two thin, a data analyst and a programmer. The thin ones are starting points and have not been validated."
8. **What did the independent reviewers find?** "One critical and fourteen high findings between two reviews, by separate Claude agents, not human researchers. Most are fixed; at the time of the review three safety findings were still open [LEAD: update]." (C42, C43)

## After a failure

Press **Stop everything**, say what happened in one sentence, and take the fallback for that beat. Never improvise a real action. Every fallback above is either fixtures that render offline, a replay, or talking over the page.

## Not verified by the author of this script

The ring on a real Chrome tab end to end; the exact desktop launch command and permissions; Cue end to end; what the Growth and Privacy screens show on the demo home at the moment of the demo (rehearse both); whether a screen recording exists; how long the household entry takes; ElevenLabs spoken lines (not in this script); a real away run (not in this script). Rehearse the whole path twice, with wifi off, before the freeze at 08:00.
