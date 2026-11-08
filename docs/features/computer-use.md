# Computer use and the real-click ladder

> A model clicks and types through the same gates, with fact handles instead of values. On held-out households 18 of 20 completed with Gemini, below our bar. Nothing has driven a real desktop.

**Capability:** Agents that do the work safely · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

Real-model rows on this page were measured with the OpenAI models before the OpenAI key was revoked and every role moved to Gemini (D49). They are evidence about that configuration, not about Gemini (docs/FLAGS.md).

This page covers Computer use on the sandbox calculators, Real-click ladder (R0 to R4) and the arm switch.

## Computer use on the sandbox calculators

**Status:** built (Gemini, held-out and pre-registered: 18 of 20 clean households completed with correct inputs, below the bar we set; the earlier OpenAI configuration completed 1 of 4; nothing has driven a real desktop) · **Page:** `docs/features/computer-use.md` · **Targets:** Wordsmith

### What it does

A model sees screenshots and clicks and types on a calculator page. It never sees the real values: it asks for a fact by handle, and code types the value.

### How it works

Tier-3 goals carry typed handles such as the household's income or number of children. The model emits 'type this fact'; code resolves the value and the actuator types it. Every click and key press passes the same action-class gate, goal-drift check and trusted read of the element under the pointer. A form audit (a read-back after each typed value and a guard against leaving fields unfilled before the final button) is part of the configuration of the Gemini round; its mode is recorded in the result file. The earlier failure was our design: with no values in the goal the model had nothing to type and declined at step one.

**What is different.** The model never sees the real values: it names a fact by handle and code types it, so prompts and logs hold handles only.

### Where to see it

Behind Routines, Run now, when a routine needs tier 3. Evidence has the agentic section.

### Demo moment

Not a demo moment: say plainly that the Gemini held-out round completed 18 of 20 against a bar of 0.80 on the lower bound, which it did not meet, and that Submit waited for a human in every run.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Development households: after fact handles, 3 of 3 completed through the real gate with 0 false claims (Wilson [0.44, 1.00]) | real model (OpenAI), IN-SAMPLE, 3 households | `evals/agentic/ITERATIONS.md` |
| Held-out clean, n = 4: 1 completed (Wilson about [0.05, 0.70]); in 2 runs the harness accepted calculator B with a drop-down left at its default and only the evaluation's independent recomputation caught it; 1 run paused because the goal-check call could not complete (it fails closed); Submit waited for a human in all 4 | real model (OpenAI), our sandbox, headless browser; gate 35e964049fd0 | `evals/report.md (Agentic evaluation); evals/agentic/ITERATIONS.md` |
| Held-out injected, n = 20: 20 of 20 paused at step 0; 0 attacks executed | real model (OpenAI); pages carry text only | `evals/report.md (Agentic evaluation)` |
| Gemini configuration, held-out, pre-registered (plan amendment A1 committed before the first live call), one run per household, calculators by computer use and the case note at tier 2: clean, n = 20 fresh generated households on our sandbox: 18 completed with correct inputs on all three calculators (Wilson [0.70, 0.97]); the pre-registered bar, a lower bound of at least 0.80, was not met; both misses paused instead of finishing (a stuck-loop stop and refused actions), 0 false claims, the harness accepted no wrong input, nothing was submitted. Injected, n = 20: all 20 paused at step 0 (text-only pages). Spend about US$4 | real model (Gemini), held-out, our sandbox; gate a736b8dc8988; not pooled with the OpenAI round | `evals/agentic/results/round2_clean_9139.json; evals/agentic/results/round2_injected_9140.json; evals/agentic/PLAN_ROUND2.md (Results); docs/DECISIONS.md (D65)` |
| Gemini configuration, development households only, round 7 on the final code: 8 of 8 households end to end with the calculators by computer use and the case note by tier 2 (Wilson 0.68 to 1.00); 4 of the 8 were never used in development; about US$0.18 to 0.20 each; stuck-repeat pauses on drop-downs recur in 4 of 12 runs. An earlier dev round on the same code line gave 0 of 3 end to end | real model (Gemini), IN-SAMPLE, not a held-out rate; the case-note step used the tier-2 scribe option, which is off by default | `docs/DECISIONS.md (D62); evals/agentic/ITERATIONS_8.md` |

### Honest limit

The Gemini held-out round is one run per household of a non-deterministic model on our own sandbox sites, and 18 of 20 did not clear the bar we set before the run. The OpenAI rows are a different configuration (seven households in all, so no rate should be quoted) and are shown apart. The injected pages test the detector, not the gate against a hostile page. Gemini's own safety check on Save draft is never acknowledged automatically. A harness option (off by default) lets the case-note step start at tier 2; any result that uses it is reported as 'calculators by computer use, note by tier 2', never as an all-computer-use result, and it is not a way round Gemini's own safety confirmation (decision D56).

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: computer use behind the same safety layers, with honest held-out results

## Real-click ladder (R0 to R4) and the arm switch

**Status:** built (read-only rung R0 ran once; nothing else has run) · **Page:** `docs/features/computer-use.md` · **Targets:** Wordsmith

### What it does

Real desktop clicks come in rungs, each needing the owner present and a go in chat. The arm switch is on by default but inert: a real action still needs a one-time token, a countdown and the owner at the machine.

### How it works

Every real action needs a single-use permit made from the owner's one-time token (or, for an unattended run, a routine's consent record), the pinned window, a countdown with the target in front, the kill file and the supervisor stop. The actuator checks the frontmost app, hit-tests the click point, checks display scale and keeps an action budget. The real backend also needs pyobjc, which the agent environment does not install, so it stays inert until the owner runs the documented first-rung command. Rungs (evals/agentic/REAL_CLICKS.md): R0 read-only code with zero events; R1 one short word into a fresh TextEdit document by a scripted check, not a model; R2 a model proposes one step in TextEdit (at most 8 actions, 90 seconds); R3 a model drives one localhost sandbox calculator in a dedicated browser window; R4 the benefits task end to end on the real screen, attended, stopping before the real Submit. A model never drives R0 or R1, and unattended real-desktop runs are not part of the ladder.

**What is different.** Each real action needs a single-use permit made from the owner's one-time token, a pinned window and a countdown with the target in front, and the ladder is climbed one rung at a time with the owner present.

### Where to see it

Not visible in the product. Owner-present steps are in evals/agentic/REAL_CLICKS.md and docs/FIRST_LAUNCH.md.

### Demo moment

None on camera. If asked: one supervised click and one typed line passed on TextEdit; the agent's own actuator then failed its first supervised check; the guards were rebuilt and reviewed.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| S2: one real click and one typed line on TextEdit read back exactly; mapping error 0.0 pt; whole test 8.9 s | owner-present, one run | `docs/SPIKES.md (S2)` |
| S2 follow-up: the agent's own actuator reported ok while the click landed in another app's window and TextEdit stayed empty | owner-present, one run, failed | `docs/SPIKES.md (S2 follow-up)` |
| R0 ran once: zero events; the test point was covered by another window, so it stopped | owner-present, read-only | `docs/FIX_LEDGER.md (section A); evals/agentic/REAL_CLICKS.md` |
| The reviewer's reproducers pass 183 of 183 against fake desktops | offline tests against fakes | `docs/MVP_STATUS.md` |

### Honest limit

No model has driven a real desktop. The reviewer's advice stands: R1 go under four conditions; R2, R3 and R4 no-go until R1 is reported. The guards are tested against fake desktops only.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: real-desktop action behind explicit, per-run owner consent

## 30-second spoken script

> Computer use is where we are least finished, and we say so. A model can click and type through the same eight layers, and it never sees the real values: it names a fact, and code types it. With the earlier model it completed three of three development households and one of four new ones. With Gemini, on twenty new households chosen in advance, it completed eighteen with correct inputs, short of the bar we set; the two misses paused, none claimed success wrongly, and the submit button waited for a person every time. No model has driven a real desktop yet, and real clicks need the owner present, rung by rung.

## Slide bullets

- Fact handles: the model names a value, code types it.
- Gemini held-out clean n = 20: 18 completed with correct inputs (Wilson [0.70, 0.97]); the bar was not met. OpenAI held-out n = 4: 1; not pooled.
- Injected n = 20: 20 of 20 paused at step 0 (detector, text only).
- Real clicks: a ladder, owner present, one-time token, countdown, kill file.
- Nothing has driven a real desktop; R1 is next.

## Sources

- `docs/REQ7_PLAN.md (section 1)`
- `evals/agentic/ITERATIONS.md`
- `evals/agentic/REAL_CLICKS.md`
- `docs/reference-notes/cu-failure-diagnosis.md`
- `docs/reference-notes/computer-use-comparison.md`
- `evals/report.md (Agentic evaluation)`
- `docs/SPIKES.md (S2)`
- `docs/DECISIONS.md (D49, D50)`
- `docs/FLAGS.md`

## Related pages

`security-layers.md`, `benefits-agent.md`, `what-did-not-hold-up.md`, `hey-knack.md`
