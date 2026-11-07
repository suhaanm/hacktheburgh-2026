# Stride: reference note

Read-only look at `references/stride/` (no licence; ideas only, nothing copied).

**What it does well.** It scores a detector at the *event* level, not the window level: an episode is detected if any alarm overlaps it (with a small slack at the edges), and a false alarm is an alarm that overlaps nothing. The headline is false alarms per hour of ordinary activity, because window accuracy hides how often a user is wrongly interrupted. Evaluation is nested leave-one-subject-out: the outer loop holds a subject out; the inner loop, on the others only, produces out-of-fold probabilities and chooses thresholds for each false-alarm budget; the held-out subject never touches the model or the thresholds. It ships a limitations document and says plainly what the public data cannot measure.

**Where it lands here.** `hazard/events.py` and `hazard/lopo.py` (ANA-5): stuck episodes are the events; an alert is a threshold crossing with a refractory period; we report detection rate, latency and **false alarms per hour**, with the threshold picked on out-of-fold predictions from the training people only, under a stated budget. `evaluate_hazard()` also carries a `caveats` list that feeds the limitations register (EVL-4).

**What we do differently.**
- We compare with two baselines (base rate, time since progress) at the same alarm budget.
- Intervals come from a bootstrap across held-out people, and n is printed (synthetic personas: 4).
- The model is a hand-written logistic regression with hashed n-grams, because the signal is discrete cog sequences, not accelerometer windows.
- We claim "recovers planted structure on synthetic personas", not real-world accuracy.
