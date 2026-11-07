# MOA: reference note

Read-only look at `references/moa/` (no licence; ideas only, nothing copied).

**What it does well.** A harness seeds a fresh environment with cases that each carry an *answer key* (expected outcome, expected amount, the rule that should authorise it). A scripted "controller" plays the human: it approves what matches the key, rejects with the key's correction when it does not, answers questions, and cases are driven in a fixed order so a rule learned on an early case can apply to later ones. Each case is scored by listing concrete problems; the report gives accuracy, a false-positive rate on cases that should not trigger an action, and a recovery rate (rejected once and still ended correct).

**Where it lands here.** `routing/` (ANA-8) and the evaluators (ANA-15, EVL-1): our case generator plants a known error probability per case (household complexity, worker retries, worker-versus-agent disagreement), so routing is judged against a truth the model never saw. The simulated human is the oracle label. `evaluate_routing()` reports auto-approved error rate, false-positive review burden and expert minutes per case.

**What we do differently.**
- Its perfect score is on cases the author wrote and tuned against. We split calibration, selection and held-out cases, and the risk bound is *checked* on the held-out split, with the failure case reported if it does not hold.
- Our generator is independent of the fitted model (a different functional form for the true error probability), so the test is not circular.
- Every number has an interval (Clopper-Pearson, bootstrap) and says it is synthetic.
- Case order matters there; we shuffle and repeat over seeds.
