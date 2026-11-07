# Drigil: reference note

Read-only look at `references/drigil/` (no licence; ideas only, nothing copied).

**What it does well.** Two small rule sets, both pure code. (1) *Fading ladder*: per person and per step, an outcome is clean, error or assisted. Three clean runs in a row promote one rung (less help); two or more errors within the last five outcomes demote one rung; assisted runs change nothing; a level change resets the streak and the window so the new rung gets a fair trial. (2) *Dignity gate*: the coach speaks only after several consecutive mistake calls, then holds for a cooldown, and treats low-confidence readings as "unclear" so silence wins over a wrong correction. A senior's recorded session can seed the step list.

**Where it lands here.** `skills/levels.py` (COA-3): the deterministic level engine L1 to L4 is the authority; a separate tiny reference implementation in tests agrees on shared cases. `skills/tracing.py` (ANA-13) adds per-cog mastery with forgetting, which feeds, but never overrides, the engine. `policy/gate.py` (COA-4): act after 2 consecutive signals, then cooldown, silent when unsure.

**What we do differently.**
- Mastery is a continuous [0,1] estimate that decays with absence; the integer level is the contract, the mastery is evidence and a decay clock.
- Level decay on long absence is explicit and tested; Drigil has none.
- The gate's false nudges per hour are measured against synthetic stuck episodes, not eyeballed.
- Its evaluation is 30 frames from one task; ours reports n and intervals and says what it does not show.
