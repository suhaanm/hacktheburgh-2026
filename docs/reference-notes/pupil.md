# Pupil: reference note

Read-only look at `references/pupil/` (no licence; ideas only, nothing copied).

**What it does well.** Every voice command becomes one *episode* record, written append-only. The user's next reaction labels the previous episode without any questionnaire: a "stop" within 4 s means corrected, the same request again within 10 s means repeated, a confirm or decline answers a pending action. Labels arrive later as separate records and are merged on read. Its gate keeps the model out of the decision: the model answers many small yes/no questions, a plain truth table in code turns the answers into an action, and the answers are logged so a changed table can be replayed offline at zero cost. Evaluation uses a labelled held-out case file.

**Where it lands here.** `policy/labels.py` (ANA-6): implicit labels for a coach prompt: followed within 10 s, dismissed within 4 s, repeated (same issue within 10 s), undone within 10 s. The logged-propensity bandit stores the context and the probability of the chosen action so a new policy can be replayed on old logs. `policy/gate.py` (PR1): the dignity gate is a pure function of signals, cooldown and confidence.

**What we do differently.**
- Labels become a reward with a stated cost model, not just a category, and the reward feeds an off-policy estimator, which Pupil does not have.
- The logging policy is randomised (epsilon 0.2) and records propensities; Pupil logs deterministic gate answers, so counterfactual evaluation of other policies is not valid there.
- Held-out evaluation is by person, not by case.
- We state plainly that an implicit label is a noisy proxy (a dismissal can mean "already knew").
