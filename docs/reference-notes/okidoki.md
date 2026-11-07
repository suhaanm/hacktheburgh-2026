# Okidoki (idea only; repo unavailable)

**Status.** `github.com/jayamitkatariya/okidoki` returned 404 on 7 Nov 2026, so nothing was read or copied. This note rests on the one-line description in `docs/REFERENCES.md` (taken from the Devpost text): record a run once, replay it deterministically, and call the model only when a precondition fails. Okidoki's author's other repo, clickyyy, is covered in `clickyyy.md`.

**What the idea gives us.** A routine the worker did by hand becomes a script with checks. The expensive part (a model) is used only at a step whose precondition no longer holds. Divergence during replay is data, not just a failure.

**Where it lands.** HND-3, HND-4 (agent track: DSL bundle, shadow mode) and, on the engine side, how the routine finder hands over a candidate: the proposal card names what the routine touches and what it never does, and the Wilson lower bound on shadow matches decides promotion. A replay that diverges counts as a non-match in shadow mode and demotes a promoted routine (`/routines/{id}/shadow`).

**What we do differently.**
- Bundles are a JSON step DSL with a precondition and postcondition per step, never generated code.
- Nothing replays on a real account; sandbox sites and synthetic data only.
- The worker opts in per routine, and irreversible steps stay behind a click unless that routine was opted in for them.
- We do not claim Okidoki's behaviour; we only took the idea as described.
