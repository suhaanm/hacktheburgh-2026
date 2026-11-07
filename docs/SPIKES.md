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

- [x] Owner grants Accessibility and Screen Recording to the terminal and the app. Already granted to the Claude app (checked with `AXIsProcessTrusted` and `CGPreflightScreenCaptureAccess`, no prompt). The test is run from the Claude app's shell, so those permissions are the ones that count; the packaged Understudy desktop app will need its own grant.
- [x] Through the chosen actuator (here: Quartz `CGEvent` from Python via pyobjc, `scripts/s2_textedit_test.py`; Alongside's TS actuator not yet exercised), click once and type one line in TextEdit. Owner present and said go.
- [x] Measure: screenshot scale (Retina 2x), coordinate mapping error, latency.
- **Decides:** whether OFF-4 is a real desktop run or a simulated-clock demo plus a recorded run.
- **Result (Sat 7 Nov 2026, about 14:50 GMT): PASS.** TextEdit opened with a new document, one real left click at the window centre, the line "Understudy S2 spike OK" typed, and the document text read back through AppleScript matched exactly. Display 1728x1117 points, screenshots 3456x2234 px (scale 2.0). Pointer landed exactly where asked (mapping error 0.0 pt, target chosen in screenshot pixels and divided by the scale). Click 40 ms, typing 22 characters 664 ms, one full screenshot 292 ms, whole test 8.9 s. The script types only while TextEdit is frontmost and aborts otherwise; it closed its own document without saving and quit TextEdit (it had launched it). **So OFF-4 can be real.** Real desktop runs stay behind `UNDERSTUDY_REAL_ACTUATOR=1`, a frontmost-app check, the kill flag and an action budget, and only on harmless apps with the owner present until the owner says otherwise.

## S3: browser capture

- [ ] Launch a headed persistent Playwright context with the extension loaded.
- [ ] Capture one event and see it in the engine.
- **Decides:** the capture architecture and the test approach for the extension.
- **Result:**

## S4: PolicyEngine UK

- [x] Install in an isolated environment. Read its licence file. policyengine-uk 2.176.1 and policyengine-core 3.34.9 install in an isolated venv outside the repo; both AGPL-3.0.
- [x] Compute entitlements for one household. About 23 s first import, about 2.5 s per household.
- [x] Check what Scotland coverage exists. SCOTLAND and WALES regions are accepted.
- **Decides:** whether `oracle.py` uses PolicyEngine or the internal rule set. If PolicyEngine is AGPL, keep it out of vendored code and call it as a separate dependency.
- **Result (7 Nov 2026, agent-core):** the internal simplified rule set is the deterministic offline oracle, labelled "simplified, not law". PolicyEngine stays an optional cross-check, never imported or vendored. A single household matched to the penny (350.14 a month), but on 20 generated households the two agree within 1 pound on only 8 of 20 (PolicyEngine applies tax and NI to gross pay, regional housing caps, a two-child limit, different work-allowance groups). We say so on the Evidence page; the 20-case hand check is still owed (AGT-6).

## S5 (optional): Alongside in mock mode

- [x] Copy Alongside into `apps/desktop` as described in the implementation spec.
- [x] Run it with `ALONGSIDE_MOCK=1`. Confirm the dock and overlay start.
- **Result (7 Nov 2026 14:32 GMT, desktop agent): PASS.** `npm install` works with its own lockfile (140 packages; the Electron binary downloads lazily). Typecheck clean; `npm test` 86 files passed, 8 skipped, 1648 tests passed, 30 skipped, 0 failed (one test now skips when the excluded TTS clips are absent). `npm run build` works. `npx electron .` in mock mode: hotkeys registered, tray created, overlay 1728x1117, `/health` ok, dock shows the onboarding screen, a ring, arrow and badge posted to `/overlay` rendered at the right box. No macOS permission prompt in mock mode. **Safety finding:** Alongside shipped with the real actuator and the multi-step `act_for_me` loop **on by default** (its README also claims real Calculator and Safari runs). In `apps/desktop` the actuator is now simulated by default (real only with `UNDERSTUDY_REAL_ACTUATOR=1`) and the agency loop is off by default (only with `ALONGSIDE_AGENCY_LOOP=1`).
