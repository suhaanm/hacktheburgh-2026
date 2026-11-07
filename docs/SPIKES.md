# Spikes (milestone M0)

Fill in each result with a date, a one-line outcome, and what it decides. Do not start the work a spike gates until it has a result.

## S1: OpenAI access

- [ ] List the models the key can use (do not print the key).
- [ ] One chat call with a structured output.
- [ ] One vision call on a screenshot.
- [ ] One computer-tool probe in the Responses API: request and response shape, how pending safety checks appear.
- **Decides:** the values of `OPENAI_MODEL_PLANNER`, `OPENAI_MODEL_FAST`, `OPENAI_MODEL_COMPUTER_USE`; whether tier 3 is real.
- **Result:**

## S2: real click on a harmless app (owner present)

- [ ] Owner grants Accessibility and Screen Recording to the terminal and the app.
- [ ] Through the chosen actuator (Alongside's actuator, or `cliclick`, or AppleScript), click once and type one line in TextEdit or Calculator.
- [ ] Measure: screenshot scale (Retina 2x), coordinate mapping error, latency.
- **Decides:** whether OFF-4 is a real desktop run or a simulated-clock demo plus a recorded run.
- **Result:**

## S3: browser capture

- [ ] Launch a headed persistent Playwright context with the extension loaded.
- [ ] Capture one event and see it in the engine.
- **Decides:** the capture architecture and the test approach for the extension.
- **Result:**

## S4: PolicyEngine UK

- [ ] Install in an isolated environment. Read its licence file.
- [ ] Compute entitlements for one household.
- [ ] Check what Scotland coverage exists.
- **Decides:** whether `oracle.py` uses PolicyEngine or the internal rule set. If PolicyEngine is AGPL, keep it out of vendored code and call it as a separate dependency.
- **Result:**

## S5 (optional): Alongside in mock mode

- [ ] Copy Alongside into `apps/desktop` as described in the implementation spec.
- [ ] Run it with `ALONGSIDE_MOCK=1`. Confirm the dock and overlay start.
- **Result:**
