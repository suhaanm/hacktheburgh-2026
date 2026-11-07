# Benefits agent and 'code decides done'

> Three calculators worked in parallel, a case note written, and a real gate on the real submit button. A code check, not the model, decides whether it finished.

**Capability:** Agents that do the work safely · **Status:** verified · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

Real-model rows on this page were measured with the OpenAI models before the OpenAI key was revoked and every role moved to Gemini (D49). They are evidence about that configuration, not about Gemini (docs/FLAGS.md).

This page covers Benefits agent on three sandbox calculators, Code decides 'done', Independent verifier (a second model family).

## Benefits agent on three sandbox calculators

**Status:** verified (verified in mock mode: ends with an item in the approval queue and 0 false claims) · **Page:** `docs/features/benefits-agent.md` · **Targets:** Wordsmith

### What it does

An agent enters a household into three differently built calculator sites in parallel, checks for cliff edges, reconciles the three answers, writes the case note, and stops at the submit button for a person to click.

### How it works

An orchestrator turns a case into a task graph. Navigators run in parallel, each in its own browser context, with a step cap. A verifier checks a fresh observation, a critic compares the evidence with the expert policy, a recovery step tries an alternative route and then escalates, and the scribe writes the note and an evidence bundle. Tier 1 runs a compiled step script; tier 2 is a browser agent; tier 3 is computer use. It escalates only when a precondition fails and logs the tier on every step. The submit step goes to the approval queue and waits for a real click.

**What is different.** Three differently built sites are worked in parallel with a verifier, a critic against the expert policy and a recovery step, and the tiers escalate only when a precondition fails.

### Where to see it

Routines, then Run now (the window minimises and the corner pill shows what is happening); the result arrives in Needs you. More, then Background runs shows runs.

### Demo moment

Start the benefits routine from Routines. The pill says what it is doing in about five words (the window minimises if the run counts as using the real screen; rehearse, because a pure sandbox job leaves the window where it is), and the finished case note arrives in Needs you with its evidence and one irreversible step waiting for a click. Do not press Approve in front of an audience; it saves a sandbox note and nothing real.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Clean path: 20 of 20 households passed [0.84, 1.00], 0 false claims; with injected failures (layout changes, one-off 503s) 20 of 20 [0.84, 1.00], 15 of 20 needed the browser-agent tier; 7 of 20 planted calculator disagreements flagged | synthetic sandbox, mock model; the report says the clean path 'says little' | `evals/report.md (Agent runs on the sandbox)` |
| Real model, 20 households per condition: clean 18 of 20 [0.70, 0.97] with 0 false claims; after a layout change 20 of 20 [0.84, 1.00] | real model (OpenAI), our sandbox, small n | `evals/report.md (Agent runs on the sandbox)` |
| One-off error page: 0 of 20 [0.00, 0.16]; the model said it was finished in 20 of 20 runs and all 20 claims were false; the code check caught every one | real model (OpenAI), our sandbox, small n | `evals/report.md (Agent runs on the sandbox)` |
| After changing what the planner sees and re-running only that condition: 10 of 10 [0.72, 1.00] | real model, IN-SAMPLE: the fix was made after seeing the result | `evals/report.md (Agent runs on the sandbox)` |

### Honest limit

The calculators are three sandbox sites we wrote with quirks we planted, and the oracle is a simplified rule set, not law (it agrees with PolicyEngine UK within 1 pound on 8 of 20 households). One model family and one prompt; identical prompts are cached, so 20 households are fewer than 20 independent samples. No real benefits-processor data.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a complicated multi-site browser workflow with recovery, a verifier and an approval gate

## Code decides 'done'

**Status:** verified · **Page:** `docs/features/benefits-agent.md` · **Targets:** Wordsmith

### What it does

A model saying it has finished counts for nothing. After the last step, code looks at a fresh page and checks that every calculator's result fields and the case-note id are really there. A claim that fails the check is recorded as a false claim.

### How it works

The check compares named result fields with the values the page schema expects, on a fresh observation taken after the final step, never relaxed for goals that sound like navigation. It returns ok, what is missing and whether a model claimed success while the check failed. A separate small classifier can flag which claimed successes are risky, but a low risk score never replaces the check.

**What is different.** 'Done' is checked by code on a fresh observation against named fields, and the false-claim count is a first-class output, not a footnote.

### Where to see it

Needs you (the evidence opens in place: found against expected); Evidence page, section on agent runs.

### Demo moment

Show the one-off error page result: the model said done in 20 of 20 runs; the check caught all 20. This is the line to read aloud.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| 20 of 20 false claims caught by the code check on the one-off error page | real model (OpenAI), our sandbox, small n | `evals/report.md (Agent runs on the sandbox)` |
| A classifier for risky claims: Brier 0.077 [0.066, 0.090] against 0.183 for the base rate; reviewing the top 20% by predicted risk catches 70% of false claims | synthetic, 600 runs, grouped 5-fold by household | `evals/report.md (Agent-claim calibration)` |

### Honest limit

The check proves the fields are present and well formed on the page the agent reached. The product's own check would not catch a wrong but well-formed figure; the evaluation's independent recomputation did (docs/reference-notes/computer-use-comparison.md). The real-model false claims are one family of failure (finishing on an error page).

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: success decided by code, not by the model's word

## Independent verifier (a second model family)

**Status:** built (routed by default to Gemini flash-lite; its evaluation set is small and easy) · **Page:** `docs/features/benefits-agent.md` · **Targets:** Wordsmith

### What it does

A second model family looks at the screen after an agent step and says whether the page shows a completed result, so the actor does not grade itself. Code still decides; the verifier is another check.

### How it works

A closed question with yes, no or unsure; unsure is never accepted; code requires yes with confidence of at least 0.7. It runs through the egress guard like every other call.

**What is different.** A different model family checks the actor, and code requires 'yes' with a confidence floor; an 'unsure' is never an accept.

### Where to see it

Behind the scenes: More, then Models and cost lists the route; agent runs show a verified chip per step where wired.

### Demo moment

Not a visual moment. Mention it when showing a run's evidence: a second model checked the final page, and code made the decision.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| All three models were right on all 30 images (15 to accept, 15 to reject); false-accept 0 of 15 with an upper bound of 20%; the set is too small and too easy to choose a verifier | synthetic sandbox screenshots | `evals/modelbench/REPORT.md (section 3)` |

### Honest limit

The evaluation cannot tell the three models apart. Treat this as a design with a first check, not a measured advantage.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a verifier of a different family from the actor

## 30-second spoken script

> Three calculator sites, built differently, with quirks we planted. Knack's agent enters the household into all three in parallel, compares them, writes the case note, and stops at the submit button. It will not submit. Whether it finished is decided by code looking at the page, not by the model. On a one-off error page the real model said it was finished in twenty of twenty runs, and was wrong every time. The check caught all twenty.

## Slide bullets

- Three sandbox calculators in parallel; verifier, critic, recovery, approval gate.
- Submit waits for a real click; nothing was ever submitted.
- Code, not the model, decides done: 20 of 20 false claims caught.
- Real model: clean 18 of 20, layout change 20 of 20, error page 0 of 20 (small n, our sandbox).
- OpenAI-era numbers; the Gemini configuration is not re-measured.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (7.2)`
- `docs/reference-notes/rouge.md`
- `evals/report.md (Agent runs on the sandbox, Agent-claim calibration)`
- `evals/modelbench/REPORT.md`
- `docs/reference-notes/computer-use-comparison.md`
- `docs/FLAGS.md (Provider)`
- `docs/drafts/DEMO_SCRIPT.md (beat 5)`

## Related pages

`security-layers.md`, `computer-use.md`, `needs-you.md`
