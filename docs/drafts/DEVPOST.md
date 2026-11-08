<!--
DEVPOST draft, rewritten 7 Nov 2026, about 18:45 GMT, by the NARRATIVE track.
- Strip every "(source: ...)" tag before pasting into Devpost. They are for the owner to check each number; C-numbers are rows in docs/drafts/CLAIMS.md.
- Numbers: evals/report.json and report.md generated 2026-11-07T17:38:00Z, git 1bab986, mock mode. RE-PULL before submitting (`make eval`).
- This replaces the earlier draft's "40 of 40 pass (mock)", which the privacy and honesty review (evals/review/privacy_honesty.md, M7) flagged: the report says the clean mock path "says little" and the real-model rows were left out.
- Devpost has no word limit, but judges read fast: sections are short and ordered problem, demo, how, evidence, limits.
- [LEAD: ...] you confirm or supply. [OWNER: ...] only the owner can supply.
-->

# Understudy

**Understudy shows where a novice loses time against an expert, coaches on the real screen with help that fades, and automates only what the worker chooses.**

*Short pitch for the summary field:* Understudy watches how people do the same task, prices each gap between a novice and an expert in seconds and in wrong answers, coaches with help that fades, and lets an agent take repetitive work only with the worker's yes. Most results are synthetic and badged as such; the live study has not been run.

## The problem

Two people do the same task. One takes longer and reaches a different answer, and nobody can say where the difference comes from: it is a check skipped, a figure copied from the wrong place, a result read three times. Tools either do the task for you or ignore you. We wanted one that shows the gap, helps less as you improve, and takes work over only when you say so.

## What you will see in the three-minute demo

Mock mode, wifi off, on synthetic data.
1. **The gap, made visible.** An expert's trace above a novice's, gaps hatched, seconds lost beneath, with two controls so it cannot be an artefact.
2. **The coach, once.** A synthetic novice skips the cliff check; a ring lands on that button; nothing nags. [LEAD: add "Cue asks one multiple-choice question, shows the step, gives one reason, then goes quiet" only if you have confirmed Cue end to end.]
3. **Growth.** How much less help a worker needs over time, with intervals. [LEAD: it shows labelled example data until the assist ledger is wired; say so here if that is still true.]
4. **An automation the worker chose.** A routine card, "Watch first", a recorded mock-mode run, and the one irreversible step waiting in a queue for a click.
5. **Privacy.** Every call from the new layers to a remote model, listed as sent. In mock mode none leave the laptop.
6. **Evidence and its limits.** The Evidence page, ending on what it does not show.

## How it works

A Chrome extension records events as roles and salted hashes: no page text, no URLs, no field values, and fields on a sensitive list are never touched. A role pack turns events into steps. We align a novice's steps with the nearest expert's and price the gap in seconds, then price skipped steps in answers, because in seconds skipping looks free. Help levels (L1 to L4) are decided by plain code, not by a model, so a chatty model cannot talk the product out of fading. The model proposes and code decides. An agent works the sandbox calculators in parallel, and a code check, not the model, decides whether it finished. Eight security layers sit between page content and actions. Every automation is opt-in, one at a time, and the irreversible step waits for a click. A Python engine and agent service, a React dashboard, an Electron coach adapted from our own earlier library (disclosure below), and sandbox calculators we built.

## What we measured

Synthetic unless stated; every row has n and a 95% interval.
- **The analysis finds planted gaps.** Precision 92% [84.5, 98.6], recall 95% [88.6, 100.0] (synthetic, 16 people; source: report.md "Deficit recovery"; C01). The real novice-to-expert gap is 229.6 s per case [192.7, 272.6]; expert against expert is 7.1 s [-2.8, 18.4]; a shuffled-label null is 46.2 s [-36.4, 116.9], permutation p = 0.001 (source: report.md "Controls"; C03). Weakest on "reads the result again and again" (precision 70%) and "copies the wrong figure" (recall 71%) (source: C02).
- **A stuck model, held-out person.** Log loss 0.436 [0.422, 0.451] against 0.509 for both baselines (synthetic, n = 4 people; source: report.md "Stuck hazard"; C04). It flags about a third of stuck events, and its false alarms (1.21 an hour [0.95, 1.48]) are over the 1.0 budget (source: C05).
- **A real model on our sandbox calculators, 20 households per condition (small n).** It passed the code check on 18 of 20 clean households [0.70, 0.97] and 20 of 20 after a layout change [0.84, 1.00], with no false claims. On a one-off error page it passed **0 of 20** and said it was finished in 20 of 20 runs; every claim was false and the code check caught all 20 (source: report.md "Agent runs on the sandbox"; C23, C24). We changed what the planner sees and re-ran only that condition: 10 of 10 [0.72, 1.00], **in-sample** (source: C25). With the mock model the clean path passes 20 of 20 and tells you little (source: C20).
- **Defences.** A scripted red team: 0.0% attack success with every layer on [0.0, 8.4], 100% with all off, 42 attacks (source: report.md "Red team with ablations"; C30). With a real model, 0 of 126 runs let an attack through with every layer on and 5 of 126 with all layers off; the intervals overlap, so this shows what the layers cost, not that they prevent attacks (source: C31). On injected pages the detector paused 20 of 20 real-model runs (source: C26).
- **Privacy canaries.** 0 of 11,336 planted tokens reached the model port across 80 runs of 10 flows; counted by run, the one-sided 95% upper bound is 3.7% (source: report.md "Privacy layer"; evals/review/privacy_honesty.md M5; C40).
- **A simulation that failed, and says so.** In the simulated study the participants are language models, not people. The pre-registered run hit a floor: most post-tests ended at the action cap with no calculation done, so scores are near zero in both arms and say nothing about the coach (source: evals/study_sim/PLAN_RUN5.md section 1; C72). The live study with four teammates has not been run (source: report.md "Live study"; C70).

## Limitations we state up front

From the limitations register (124 entries at 17:38 GMT: 34 high, 69 medium, 21 low; source: C17). The high-severity ones that matter most:
1. **Almost every number is from synthetic data we generated.** Each result carries a badge. They show our methods recover what we planted, not that real workers behave this way.
2. **Nobody has used it in a study.** The live study (four teammates, none a benefits processor) has not been run; with n = 4 the smallest exact p is 0.125. The simulated study uses language-model participants, not people, and its pre-registered run hit a floor.
3. **There is no real benefits-processor data.** The only real signal is our own machine timestamps.
4. **The agent is scored against a simplified rule set, not the law.** It agrees with PolicyEngine UK within 1 pound on 8 of 20 households. The calculators are sandbox sites with quirks we planted.
5. **A real model declared success on an error page in 20 of 20 runs and was wrong every time.** Code caught all 20. Our fix was tested only on the same condition (10 runs, in-sample).
6. **Computer use does not yet work on the benefits task** (3 runs, 0 pointer actions). One supervised real click on TextEdit passed; the agent's own actuator then failed its first supervised check by clicking another app's window, and real clicks stay off until it is retested with the owner present.
7. **The red-team attacks were written by the team that wrote the defences.** In the real-model run the intervals overlap.
8. **Two results are weak or circular.** The stuck model flags about a third of stuck events on four synthetic personas, with false alarms over budget; review routing finds the quirks we planted.
9. **The privacy ledger does not cover everything.** It lists calls from the Python services and the new layers. Model calls the worker asked for are recorded as metadata only, an allowed screen frame is raw, and an independent reviewer found older desktop code that could still send screenshots and file text to OpenAI and Gemini; decision D38 turns those off by default. [LEAD: confirm D38 has landed.]

10. **The stuck model's edge was mostly our generator.** Scored forward in time on new seeds it beats the best naive predictor where it was fitted and is worse than it on three other generator families, with a negative calibration slope; under mismatch a one-feature rule does about as well. Two of ten registered prospective claims did not pass (source: docs/HRT_BRIEF.md; C90, C93).

Two independent review passes by separate Claude agents found, as of 17:55 on 7 Nov, one critical and fourteen high findings between them; most are fixed, and three safety findings and some privacy findings were still open (source: evals/review/privacy_honesty.md, safety_actuator.md; C42, C43). [LEAD: update this line after the re-run.]

## Why this fits the tracks

- **HRT, best use of data for predictions and decisions. Predict first, score later.** Every forecast of the stuck model is written to a hash-chained ledger before its outcome exists, with the naive predictors' forecasts beside it, and scored only from that record on seeds nobody had used; the plan, with every claim and pass rule, was committed before any number existed. Of 10 registered claims, 8 passed and 2 did not, and the two are printed (C90). In the world the model was fitted for its log loss is 0.445 [0.434, 0.455] against 0.525 for the online base rate and 0.524 for frozen time since progress, a paired difference of -0.079 nats [-0.085, -0.074] (C91), with a calibration intercept of +0.075 [0.002, 0.162] that excludes zero (C92). **When the generator changes, the model is worse than the best naive predictor** by +0.324, +0.331 and +0.513 nats on three generator families, and its calibration slope turns negative (-0.20, -0.25 and -0.21); a guard that watches the ledger flagged 8 of 8 deployments in each family and 0 of 8 where nothing changed, and falling back changed log loss by -0.309, -0.262 and -0.438 nats against always trusting the model (C93). So the stuck model's edge over a one-line baseline was mostly our generator (C04 and C05 carry that sentence: C93). Decisions are scored against naive and oracle policies in generated worlds, four registered contrasts at the Bonferroni-adjusted level (98.75%): all four won (C96), and building at once beats our build-timing rule at the pack's own build costs (3.77 against 4.93 at b = 4, C97). We then asked whether recalibrating the frozen model online from resolved outcomes would rescue it, registered that follow-up after seeing the first result and ran it on new seeds: it did, by -0.487, -0.528 and -0.542 nats against the frozen model in the three shifted worlds and -0.032 nats after a rule change, but it did not restore the calibration intercept in the cases available (+0.61, claims R4 and R6 did not pass; C100). On the real-model agent runs a one-bit indicator predicts false claims better than our predictor (Brier 0.0003 against 0.0038, C98). All generated by us and labelled; the live study has not run (C70).
- **Also for HRT.** Review routing with a risk bound, stated as circular (C09); build timing by ski rental, including where building at once wins (C10); a start-or-wait rule for background runs (2.1% interruptions against 24.8% for running whenever idle, C11); off-policy evaluation checked against a simulator with known truth (C08), where overlap is poor and the doubly robust interval covers the truth in 87.5% of replications against a nominal 95%. The full judge-facing account, with the attacks a quantitative judge will make and our answers, is `docs/HRT_BRIEF.md`.
- **G-Research, make the invisible visible.** The expert's hidden policy shown as aligned traces priced in seconds, with a placebo and a null (C01, C03); the cost of skipping a step in answers: on 200 synthetic households, skipping the cliff check leaves a nearby edge unwarned on 107 and moves the award by more than 50 pounds a month on 42 (C61); routines and weekly rhythm with intervals (C11, C12); and our own failures as a published limitations register.
- **Wordsmith, most complicated end-to-end browser-use workflow.** Three calculators worked in parallel, a verifier, critic and approval gate, recovery, shadow mode and background runs, completion checked by code, and an injection defence measured with ablations (C20 to C31). The real-model results are small and include a failure we publish. The computer-use tier is not yet working on this task.

## MLH categories

[OWNER: confirm which of these you are entering, and the text each category asks for.]
- **OpenAI.** Planner, fast and computer-use calls sit behind one model port and produced the real-model rows above; model IDs are read from the environment. (C23 to C27, C31)
- **Gemini API.** Screen-glance and pointing routes and a bake-off against OpenAI and a local model are in progress; we claim no Gemini speed or accuracy figure until the bake-off lands in the report. [LEAD: update when it does.]
- **ElevenLabs.** Spoken coach lines and a morning briefing, by line id only (no free text leaves), ledgered, off by default, with cached audio for the offline demo. [LEAD: confirm built and whether it is in the demo.]
- **Auth0.** A thin sign-in behind an interface with a local fallback, never on the demo's critical path. [OWNER: whether the tenant exists; LEAD: confirm built.]
- **DEV Writing Challenge.** Our write-up of what failed and what we measured: [OWNER: link when published].

## What we learned

Skipping a step looks free in seconds and is costly in answers, so we price both. Code, not the model, must decide "done": a real model was confidently wrong on an error page in 20 of 20 runs. A model's edge is a property of the world it was tested in: scored forward in time it reverses when the generator changes, so we built a guard that notices and falls back, and scored the guard too (C93). Honest framing is a product feature: we publish the weak results (skill tracing saturates, mean Spearman 0.18; review routing is circular; hazard false alarms overshoot) and a simulation that hit a floor.

## What's next

Run the live study (n = 4, plan committed before data). Finish Cue (stuck rescue) and the independence score, and measure them on simulated learners, labelled as such. Get computer use working on the benefits task through fact handles (the model names a value handle; code types the value) and run the supervised real-click ladder with the owner present. Run the red team against more than one model. Get real traces from a pilot team.

## Disclosure

- **Alongside.** Understudy's coach is built on Alongside, the author's own earlier open-source library (github.com/suhaanm/deepmind-hackathon, first commit 31 Oct 2026, before this event, MIT). On 7 Nov, of Alongside's 303 source files 205 are byte-identical in our desktop app, 70 are modified, 28 are not carried over, and 313 are new (source: C65; recompute at the freeze). The full list and the safety finding about Alongside's real actuator being on by default are in the README. Third-party notices travel with the code.
- **How it was built.** [OWNER: confirm this wording.] The code was written by Claude Sonnet 5.5 agents working under the owner's direction, one agent per area, with a lead agent merging and committing (source: docs/DECISIONS.md, 7 Nov 14:19 entry; docs/AGENTS.md). The owner chose the product, the targets and the limits, and made the decisions recorded in docs/DECISIONS.md. [OWNER: check the hackathon's rules on AI-written code and say what the team did by hand.]
- **Team.** [OWNER: names and roles. Not known to this track.]

**Built with:** Python, FastAPI, React, TypeScript, Electron, Chrome MV3, Playwright, a JSONL event store, llama.cpp with a local Qwen2.5-7B model for private digests, OpenAI (primary model provider), Gemini API and ElevenLabs (flagged, in progress). [LEAD: trim to what is actually used in the shipped build.]
**Tracks:** HRT, G-Research, Wordsmith.
**Try it:** `make demo` (macOS, mock mode, offline); README has the steps. [OWNER: repo URL and demo video URL.]
