# BandIt (idea only; repo not cloneable)

**Status.** The repo (`viktorinkov/cal-hacks-13`, no licence) could not be cloned, so nothing here comes from its code. Everything below is the idea as summarised in `docs/REFERENCES.md`: a model proposes, a guard clamps to a human-approved ceiling; a learned rule needs three approved precedents and a separate approval, and is versioned; a scorecard plants genuine and fake cases and reports precision, recall and cost.

**Where it lands.** MEM-3 and MEM-4, in `understudy_engine/memory/rules.py` and `shadow.py`, written from scratch.

**How we use the idea.**
- A worker correction is a *precedent*. Three consistent ones in a row (same subject, same value, none contradicting, none faded by decay) become a *proposal*, which changes nothing.
- The proposal's *ceiling* (the highest autonomy rung A0 to A3 the rule may grant) is the tightest ceiling among its precedents, so a rule is never looser than anything the worker already approved. Approval can tighten it, never loosen it. Code clamps every request to it.
- A separate approval by the worker activates the rule; the rule is a line in the memory file with a version (`v1`, `v2`). Behaviour is read from the file, so deleting the line ends the rule.
- A personal *procedure* rule is also compared in shadow with the pack's expert policy and is rejected if it does not match expert outcomes.

**What we do differently.** Precedents decay (30-day half-life); only the worker, directly or by approving, can write; we report no insurance-style cost scorecard. Our test of the guard is the injection test in `tests/handoff/test_memory.py`, not a planted-claims scorecard.
