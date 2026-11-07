# Context library: proposed live check (NOT approved, NOT run)

Status: a proposal for the lead. No live call has been made by the CONTEXT track. Per the lead's rule, this file is committed by the lead before any live call, and nothing changes in it afterwards except dated amendments that cannot loosen a criterion.

## 1. What a live run can and cannot show for US$3 or less

Prices (assumptions, read from the environment by `models/prices.py`; defaults used here): computer-use tier US$5.00 per million input tokens, US$30.00 per million output tokens, cached input at 25 percent of the input price. A 40-step tier-3 navigator on one calculator costs about US$0.75 under either prompt policy (about 2k to 3k input tokens per step, about 300 output tokens per step including reasoning, my estimate). So US$3 buys **about 4 runs**: two per arm.

Two runs per arm cannot compare success rates, and I will not report one. A claim that the library improves completion, steps or false claims needs at least 20 runs per arm (about US$30), which is outside this proposal and outside what I would ask the owner for before the freeze.

What 4 runs can do honestly is **check the token model and smoke-test the live loop**: do the provider's usage fields agree with what the offline model says each policy puts in the prompt, and does a real computer-use model still finish a calculator when the prompt is the library's.

## 2. Design, declared before any call

- **Arms** (same two households, paired; fresh synthetic households, seed 9137, indices 0 and 1; sandbox site a only; real model through the model port, mock mode off; the SafetyPipeline unchanged):
  - **A, current default**: `ComputerUse` as shipped (chained, restarted every 4 steps from the code-built task state).
  - **B, library**: the same loop with the prompt from `computer_use_text` (`WorkingMemory`, `FrameRetention(passthrough=True)`, the original screenshot passed, `history=[]` so the provider runs stateless). Requires AGENT-CORE to put the library behind a flag (`UNDERSTUDY_CTX=1`); until then this run cannot happen.
- **n**: 2 per arm, 4 runs, run in the order A0, B0, A1, B1.
- **Judge**: code only (`code_check`, the orchestrator's completion check). A false claim is a claimed success the code check rejects.
- **Recorded per step, metadata only**: the provider's input and output tokens and cached tokens (from the meter), the manifest from the library (arm B), the estimate-versus-actual token error, step count, wall time, outcome, refusals. No screenshot, no page text, no value.
- **Hard stop**: cumulative estimated cost US$2.50, checked before each run; the ledger counts against the lead's US$60 total (D32).

## 3. Criteria (descriptive, no rate claim)

1. **Token model.** Arm B: the provider's input tokens per step are at most 3,000 on every step, and within plus or minus 30 percent of the manifest's estimate on at least 90 percent of steps. Arm A: the maximum provider input tokens per step is within plus or minus 30 percent of the modelled 5.3k. If either fails, the estimator constants (`context/tokens.py`) are recalibrated from the usage fields and the offline numbers in `docs/CONTEXT_ENGINEERING.md` section 5 are re-derived, labelled as recalibrated.
2. **No regression, no false claim.** In both arms every run either reaches the code-verified result page of calculator a or ends with the model saying it cannot finish; **0 false claims in all four runs** and 0 gate bypasses. A false claim in any run is reported as a failure of that arm, not averaged away.
3. **Reported, not judged**: steps, input tokens in total, estimated cost, refusals, resets, the number of steps whose prompt named a handle the page had not yet received. With n = 2 per arm, the table is the result; there is no comparison statistic.

## 4. What this will not tell us

Whether the library completes more households than the shipped loop; whether stateless beats chained on a real model; how a model behaves over 150 steps (each navigator is 25 to 60 steps); anything about the desktop actuator (real clicks stay behind the ladder and the owner's go); anything about people. The provider's truncation behaviour is not exercised by a 40-step run.
