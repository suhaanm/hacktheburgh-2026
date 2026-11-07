# Spikes (milestone M0)

Fill in each result with a date, a one-line outcome, and what it decides. Do not start the work a spike gates until it has a result.

## S1: OpenAI access

- [x] List the models the key can use (do not print the key). 7 Nov 14:30 GMT: HTTP 200, 107 models incl. gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.4-nano, gpt-6-sol, gpt-realtime-*, gpt-4o-transcribe, tts. No `computer-use-*` ID is listed or needed.
- [x] One chat call with a structured output. Responses API, `text.format` json_schema strict: works on gpt-5.5, gpt-5.4-mini, gpt-5.4-nano.
- [ ] One vision call on a screenshot. (agent-safety track will run this as a `live` test.)
- [x] One computer-tool probe in the Responses API: `tools=[{"type":"computer"}]` is accepted by gpt-5.5, gpt-5.4, gpt-5.4-mini and gpt-6-sol. The response contains a `computer_call` item whose `actions` is a list (first action on "take a screenshot" was `[{"type":"screenshot"}]`). No `pending_safety_checks` appeared on this trivial call (field absent); the provider must still treat any that appear as a stop.
- **Decides:** the values of `OPENAI_MODEL_PLANNER`, `OPENAI_MODEL_FAST`, `OPENAI_MODEL_COMPUTER_USE`; whether tier 3 is real.
- **Result (7 Nov 2026, lead):** `OPENAI_MODEL_PLANNER=gpt-5.5`, `OPENAI_MODEL_FAST=gpt-5.4-mini`, `OPENAI_MODEL_COMPUTER_USE=gpt-5.5` (set in the local `.env`, never committed). Tier 3 is real at the API level. Whether it is real on the desktop depends on S2. Vision call still to confirm.

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
