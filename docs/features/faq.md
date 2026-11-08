# The 25 hardest judge questions

Short, truthful answers, each with its source. Nothing here is stronger than the evidence labels in `docs/PITCH_FEATURES.md`. Numbers are synthetic or simulated unless the answer says otherwise. Grouped: privacy, safety, honesty, choices, disclosure.

## Privacy

**1. What leaves my laptop?**

Calls from our services to a model go through one choke point and each leaves a row you can read (typed payload for text; size, hash, model and latency for images; never the picture). In mock mode none left. Not covered: model calls you asked for are recorded as metadata only, an allowed frame is raw pixels, the ledger cannot see other software, and older desktop paths that could send screenshots and file text are off by default but not independently re-reviewed (docs/PITCH_FEATURES.md, privacy page; evals/report.md limitations).

**2. Is the microphone always listening, and what does it keep?**

By the owner's decision (D52) listening for 'hey knack' is on by default, on the Mac, using on-device speech. It prints only a closed 'heard' event and stores no audio and no transcript; if on-device recognition is missing it switches itself off and never uses server recognition; it is dormant on calls, meetings, screen shares, a locked screen and during Stop everything. It is built and tested offline and has not been run with a real microphone yet (docs/DECISIONS.md D52; apps/desktop/src/main/wake/guards.ts).

**3. Do you record my screen?**

No frame is written to disk or logs. A frame is held in memory for one call, sent only if you chose Yes on the consent card, never from a denylisted app or over secure input, and never in an unattended run. Capture itself stores kinds of steps and times, not page text, URLs or field values (CLAUDE.md; docs/REQ5_PLAN.md; docs/SPIKES.md S3).

**4. What can my employer see, and can I delete what Knack holds?**

In the demo the admin sees numbers and enums per person (counts, trends, intervals), never raw events, screenshots, text or memory contents, with no ranking and no single score, and groups under 5 are not compared. That was the owner's choice (D41); the lead recommended aggregates plus opt-in. A real deployment needs a lawful basis and notice to workers, which this build does not supply. You have a plain 'what your admin can see' page. You can delete what Knack holds: Your data lists what it remembers, measures and has sent, delete is three clicks at most, and 'Delete everything' asks for an exact confirmation; deleting a ledger removes you from admin comparisons at once in our tests on synthetic firms (docs/DECISIONS.md D41; docs/INSIGHTS_DESIGN.md; docs/KNACK_UX.md J5; evals/insights/results/heldout.json).

## Safety

**5. Can the agent be tricked by a web page?**

It is designed so a page cannot steer it: page text is data, a quarantined reader returns only checked fields, irreversible actions need your real click, and an injection detector pauses the run. A scripted red team of 42 attacks got through 0.0% [0.0, 8.4] with every layer on and 100.0% with all off. With a real model the intervals overlap (0 of 126 against 5 of 126), so that run shows what the layers cost, not that they prevent attacks. We wrote both the attacks and the defences (evals/report.md, red-team sections).

**6. Can it click on my real desktop?**

Not yet in practice. One supervised click and one typed line passed on TextEdit; the agent's own actuator then failed its first supervised check by clicking another app's window; the guards were rebuilt and reviewed against fake desktops. The arm switch is on by default but inert: a real action needs the owner's one-time token, a countdown and the owner present, and the reviewer's advice is no-go beyond the first rung until it is reported (docs/SPIKES.md S2; docs/DECISIONS.md D50; docs/MVP_STATUS.md).

**7. Does Knack run model-written code?**

Yes, on the open-ended task path, with the worker's per-task consent, and never in routines. Routines are a JSON step language run by a small interpreter, and generated code is not executed there. A typed or spoken task that is code, data or file work can start the owner's own Claude command as a monitored background agent, which writes and runs code on the Mac. That happens only after a consent card that says in plain words what the agent can do, answered by a real click; the child gets an environment allow-list (no Knack keys), a time cap and a spend limit (US$2 unless the worker sets another), Stop and the kill file end it, ledger rows hold metadata only, and an unattended run never gets 'allow everything'. The deny rules for Knack's own files are defence in depth, not a sandbox, and this path is on main but tested only with a fake command and two small real checks (the second showed the deny rules refuse a file write and read of Knack's safety files, which a shell command may still bypass), not run on a real task, and the box to type a task is not in yet (docs/IMPLEMENTATION_SPEC.md section 6.5 as amended; docs/DECISIONS.md D63; docs/TASKS.md).

**8. How do I stop it?**

Option-Shift-Command-K anywhere, the Stop button on the corner pill, the sidebar Stop button, or the menu bar. It flips a flag on disk and cancels the supervisor, so it never waits for a model; in tests it reached a running helper in a median 33 ms and 8 of 8 trials were within a second. The Stopped card stays until you press Resume (evals/report.json runtime; docs/KNACK_UX.md section 9).

**9. What happens before something irreversible?**

It stops and waits in Needs you with 'Cannot be undone.' printed. An approval is only ever a real click: no keystroke and no voice approves. During an unattended run an irreversible step needs a separate per-routine opt-in, and unattended runs never write to a real account (docs/knack-ux/02-needs-you.md; CLAUDE.md).

**10. Why no allowlist of safe sites?**

Owner decision D12: the agent may go anywhere, because a list of safe sites does not stop a safe site carrying hostile text. The worker keeps an optional denylist, and the eight layers are mostly code, not model judgement (docs/SPEC_LIST.md D12; docs/IMPLEMENTATION_SPEC.md section 9).

## Honesty

**11. Did you test it with people?**

No. The live study with four teammates has not been run, and with four people the smallest possible exact p is 0.125. The simulated study used language-model participants, not people, and sat at the floor (30 of 32 post-tests scored 0). Everything else is synthetic or run on sandbox sites we wrote (evals/report.md, Live study and Study power).

**12. Why should we believe numbers from synthetic data?**

Don't, as evidence about people. They show that our methods recover what we planted, with controls (expert against expert, shuffled labels), and we then tested how much of that survives three differently built generators: the stuck model's edge falls from 0.071 to 0.008 to 0.015 nats and genome precision from 92% to 48 to 71%. Both are on the Evidence page (evals/realism/INTERPRETATION.md).

**13. What is real, and what is synthetic?**

Real: all the code, run locally; three sandbox calculators and a case-note page served locally; real-model agent and red-team runs at small n; one supervised click and one typed line on TextEdit with the owner present; one real-browser capture check; two small real runs of the owner's Claude command with the owner's approval. Synthetic or simulated: people, histories, households, calendars, commits, the firm, and the study participants (language models). The oracle is a simplified rule set, not law (README.md, What is real and what is synthetic).

**14. Does the stuck model work?**

On its own generator it beats two plain baselines (log loss 0.436 against 0.509, n = 4). On harder generators its edge over a time-since-progress rule falls to a few thousandths, a v1-trained model is worse than that rule, and under mismatch the plain rule beats it in all three roles. A small gain from a boosted version was accepted. Our claim is that a simple rule does about as well; the product decision is with the owner. A later forward-in-time check agrees: on new seeds it beats the plain baselines where it was fitted (log loss 0.445 [0.434, 0.455] against 0.525 and 0.524), is worse than the best plain predictor in three shifted worlds by +0.324 to +0.513 nats, and an online recalibration, registered afterwards on new seeds, leaves it no worse than the best plain predictor in those worlds (small margins, reported and not a registered claim) without restoring calibration after a rule change (README.md; evals/report.md Findings; docs/HRT_BRIEF.md).

**15. Does coaching help? Do novices become experts?**

We do not claim either. No person has used Knack in a study. Growth measures help needed, not expertise, and says so on the screen. The claim is that the system lifts novices on our synthetic data and shows its limits (CLAUDE.md, Honesty; docs/knack-ux/04-growth.md).

**16. What failed?**

The stuck model and the genome degrade on harder data; ML v2's ensemble and counterfactual were rejected as harmful on held-out data; transfer to simulated-participant traces failed; the simulated study sat at the floor; computer use completed 1 of 4 held-out households with OpenAI and 18 of 20 with Gemini, below its bar; Cue did not meet its faster-to-resume target; the attention router missed one of twelve criteria; the insights engine found 47 of 100 planted independence rises (target 0.8). Each is on the Evidence page (evals/report.md Findings; docs/features/what-did-not-hold-up.md).

**17. How do you know the agent actually finished?**

Code checks a fresh page for each calculator's result fields and the case-note id; a model's 'done' counts for nothing. On a one-off error page the real model said it was finished in 20 of 20 runs and all 20 claims were false; the check caught every one. The product's own check would not catch a wrong but well-formed figure, which an independent recomputation did in two held-out computer-use runs (evals/report.md; docs/reference-notes/computer-use-comparison.md).

**18. How reliable is computer use?**

Not reliable enough to claim. With Gemini, held-out and pre-registered, 18 of 20 fresh households completed with correct inputs on all three calculators (Wilson [0.70, 0.97]); our bar was a lower bound of at least 0.80, so it was not met. Both misses paused instead of finishing, none claimed success wrongly, nothing was submitted, and all 20 injected pages paused at step 0 (text-only pages, so this tests the detector). It is one run per household of a non-deterministic model on our own sandbox sites, with the case note written at tier 2. The earlier OpenAI configuration completed 1 of 4 held-out households and 3 of 3 in-sample; the two configurations are shown apart and not pooled (docs/DECISIONS.md D65; evals/agentic/PLAN_ROUND2.md; evals/agentic/results/round2_clean_9139.json).

## Choices

**19. Why Gemini?**

The OpenAI key was revoked on 7 Nov (cause unknown) and the owner moved every role to Gemini (D49). We then measured the routes on our sandbox screens: the fast Gemini model found the right element 95% [90, 98] of the time in a median 0.93 s against 75% for the OpenAI fast model, and all models tied on the verifier set. Computer use on Gemini completed 18 of 20 held-out households, below our bar (question 18), and the earlier OpenAI numbers are not evidence about it (evals/modelbench/REPORT.md; docs/FLAGS.md).

**20. Why a local model at all?**

So private text, such as commits and calendar entries, becomes short labels on the Mac and a cloud model sees digests, not text. On held-out synthetic items the local model beat rules on category (91.8% against 77.5%) and not on risk, so rules are shipped there. The model can be steered by a planted line, so code vetoes the two most consequential claims (evals/report.md, Local model digests).

**21. Isn't this just Clicky or Sentient OS?**

No, and we read both without running them. Per our notes, the Clicky app points at things and never clicks, and its Windows fork's plugin runs single actions at screen coordinates for an outside agent; Sentient OS runs a real multi-step loop on real apps, with the loop in an external agent command line and success judged by the model's own final claim, and its repository holds no completion measurement. Knack's difference is the layer around the action: an expert comparison priced in seconds and in answers, help that fades by code, 'done' decided by code, eight layers, and held-out results (1 of 4, then 18 of 20 against a bar of 0.80 on the lower bound) that we publish. We used a little of Clicky's MIT code with notices and Sentient OS only as ideas, through a clean-room note (docs/reference-notes/computer-use-comparison.md; docs/reference-notes/clicky-reuse.md; THIRD_PARTY_NOTICES.md).

**22. Can the independence score be gamed?**

It is built against the obvious ways: dismissing a cue without finishing the step is not independence, an error is penalised, and delegated or overnight work never moves it. It is validated only on simulated learners, its composite is experimental and in no headline, and the trend has low power (docs/REQ7_PLAN.md section 5; evals/report.md limitation cue-score-composite).

## Disclosure

**23. Is Alongside new work?**

No. It is the author's earlier open-source library (first commit 31 Oct 2026, before this event, MIT) and is the base of the desktop coach. The README lists what was reused (182 of 303 source files unchanged at its last count) and the safety finding that Alongside shipped with the real actuator on by default, which Knack turns off (README.md, Reuse: Alongside).

**24. Who wrote the code?**

The draft disclosure says Claude Sonnet 5.5 agents wrote the code under the owner's direction, one agent per area, with a lead agent merging and committing; the owner chose the product, the targets and the limits and made the recorded decisions. The wording is marked for the owner to confirm, and the hackathon's rules on AI-written code are the owner's to check (docs/drafts/DEVPOST.md, Disclosure; docs/AGENTS.md).

**25. What would a real deployment need?**

A study with people (the live study and a labelled pilot), a lawful basis and notice for any admin view, a signed and notarised app (an Apple Developer ID), real traces to validate the role packs, a re-review of the older desktop paths, the real-click ladder reported rung by rung, and a decision on the stuck model's default signal (docs/MVP_STATUS.md; docs/FIX_LEDGER.md; docs/DECISIONS.md D41).
