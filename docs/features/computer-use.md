# Computer use and the real-click ladder

> A model clicks and types through the same gates, with fact handles instead of values. It works in-sample and does not yet generalise. Nothing has driven a real desktop.

**Capability:** Agents that do the work safely · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

Real-model rows on this page were measured with the OpenAI models before the OpenAI key was revoked and every role moved to Gemini (D49). They are evidence about that configuration, not about Gemini (docs/FLAGS.md).

This page covers Computer use on the sandbox calculators, Real-click ladder (R0 to R4) and the arm switch.

## Computer use on the sandbox calculators

**Status:** built (works in-sample, not held-out; the Gemini configuration is still in development) · **Page:** `docs/features/computer-use.md` · **Targets:** Wordsmith

### What it does

A model sees screenshots and clicks and types on a calculator page. It never sees the real values: it asks for a fact by handle, and code types the value.

### How it works

Tier-3 goals carry typed handles such as the household's income or number of children. The model emits 'type this fact'; code resolves the value and the actuator types it. Every click and key press passes the same action-class gate, goal-drift check and trusted read of the element under the pointer. A read-back after each typed value and a guard against leaving fields unfilled before the final button are being added. The earlier failure was our design: with no values in the goal the model had nothing to type and declined at step one.

### Where to see it

Behind Routines, Run now, when a routine needs tier 3. Evidence has the agentic section.

### Demo moment

Not a demo moment: say plainly that the computer-use tier is in development and that Submit waited for a human in every run.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Development households: after fact handles, 3 of 3 completed through the real gate with 0 false claims (Wilson [0.44, 1.00]) | real model (OpenAI), IN-SAMPLE, 3 households | `evals/agentic/ITERATIONS.md` |
| Held-out clean, n = 4: 1 completed (Wilson about [0.05, 0.70]); in 2 runs the harness accepted calculator B with a drop-down left at its default and only the evaluation's independent recomputation caught it; 1 run paused because the goal-check call could not complete (it fails closed); Submit waited for a human in all 4 | real model (OpenAI), our sandbox, headless browser; gate 35e964049fd0 | `evals/report.md (Agentic evaluation); evals/agentic/ITERATIONS.md` |
| Held-out injected, n = 20: 20 of 20 paused at step 0; 0 attacks executed | real model (OpenAI); pages carry text only | `evals/report.md (Agentic evaluation)` |
| Gemini configuration, development households only: 0 of 3 end to end, 7 of 9 calculators finished with a clean audit | real model (Gemini), IN-SAMPLE; landing on branch worktree-agent-acf889b730112335b | `evals/agentic/ITERATIONS_8.md (branch)` |

### Honest limit

Seven households in total across development and held-out, so no rate should be quoted. The injected pages test the detector, not the gate against a hostile page. Every number above, except the Gemini row, is about the OpenAI configuration. A fresh pre-registered round on new seeds is planned after the fixes land.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: computer use behind the same safety layers, with honest held-out results

## Real-click ladder (R0 to R4) and the arm switch

**Status:** built (read-only rung R0 ran once; nothing else has run) · **Page:** `docs/features/computer-use.md` · **Targets:** Wordsmith

### What it does

Real desktop clicks come in rungs, each needing the owner present and a go in chat. The arm switch is on by default but inert: a real action still needs a one-time token, a countdown and the owner at the machine.

### How it works

Every real action needs a single-use permit made from the owner's one-time token (or, for an unattended run, a routine's consent record), the pinned window, a countdown with the target in front, the kill file and the supervisor stop. The actuator checks the frontmost app, hit-tests the click point, checks display scale and keeps an action budget. The real backend also needs pyobjc, which the agent environment does not install, so it stays inert until the owner runs the documented first-rung command. Rungs: R0 read-only (draw where it would click), R1 TextEdit, R2 one click and one typed field on a sandbox page, R3 a full household with real clicks, R4 a short long-horizon run.

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

> Computer use is where we are least finished, and we say so. A model can click and type through the same eight layers, and it never sees the real values: it names a fact, and code types it. On the development households it completed three of three. On new held-out households, one of four. The submit button waited for a person every time. No model has driven a real desktop yet, and real clicks need the owner present, rung by rung.

## Slide bullets

- Fact handles: the model names a value, code types it.
- Held-out clean n = 4: 1 completed; the weak spots are named.
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
