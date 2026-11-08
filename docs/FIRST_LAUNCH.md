# First launch together (about 15 minutes)

Written 7 Nov 2026 for the midnight session; the state and the steps were brought up to date on 8 Nov at about 03:00 GMT. The lead does the technical steps; you do the three things only you can do: grant macOS permissions, speak, and watch the screen. Nothing here touches a real account or a real purchase.

## State at about 03:00 GMT on 8 Nov (rewritten from the repository; the lead confirms the items marked "lead")

- **Code.** `main` holds every checkpoint branch that was ready: the Knack shell and first run, Growth as the one worker page, the admin firm (32 made-up people; run `python -m understudy_engine.demo seed-firm` on the live data folder to fill the Admin view), the graph on the design system, connections, role depth for the programmer and data analyst, open-ended tasks with the Home task box and the Claude background agents (D63, D64), the HRT work (`docs/HRT_BRIEF.md`) and computer use on Gemini (round 2, `evals/agentic/PLAN_ROUND2.md`: clean 18 of 20, the registered bar was not met).
- **The app was rebuilt.** `apps/desktop/dist-app/mac-arm64/Knack.app` and `Knack-0.1.0-arm64.dmg` (about 127 MB) have file times of 8 Nov 02:08 and 02:09; it is unsigned and the Hey Knack listener is inside it. The app attaches to the running stack and starts nothing of its own while one answers. Whether it was built from the final `main` is not checked here (lead).
- **The stack.** The lead runs it live (`make live`: `mock: false`, `provider: gemini`, keys present, isolated data under `data/live-*`, example content only). Not checked by the author (lead).
- **Tests.** The report's static count is 8,193 test functions (`evals/report.facts.json`, 8 Nov 02:58 GMT; parametrised cases are not expanded); a final `make test` with its pass counts is still owed.
- **On screen, with no `synthetic` tag (D57).** Where numbers come from is said in the closed "About this data" line and on the Evidence page's "Measured on" column; "Example data" marks a built-in sample that stands in.
- **Not done.** The macOS permissions and the first speaking are yours; the second R0 and the supervised R1 test have not run; no real task has been run through the Claude agent path; the full rehearsal on a visible desktop has not been run.

## Your part, in order

| Step | What you do | What should happen |
|---|---|---|
| 1 | Open Knack (`apps/desktop/dist-app/mac-arm64/Knack.app`; right-click, Open the first time because it is unsigned) | First run opens with no sidebar: a role card (or "Not sure yet"), one card each for capture, screen glances and voice with Yes, Not now and Never, then "Check it works" (the macOS permissions as they are, Hey Knack's listening state, and Show me, which draws the ring on a sample), then "Show my week". Every screen has a Skip, and skipping picks nothing. Then a window about 80% of the screen, the Knack logo in the sidebar and the Dock, five items on the left, one sentence on Home and the task box "What should Knack do?" |
| 2 | macOS asks for Microphone, then Speech Recognition, when the listener first starts: Allow both. Speech Recognition on this Mac needs a Dictation language installed (System Settings, Keyboard, Dictation) | A small listening dot in the menu bar. If macOS says on-device recognition is not available for your language, Knack prints one line and stays off: it never uses server recognition |
| 3 | Say "Hey Knack" | The pill shows "Listening", a soft cue, Knack speaks (Gemini voice) |
| 4 | The first time, two cards: "Talk with Knack?" (voice), then "Knack may look at your screen while we talk". Choose Yes, Not now or Never on each | Equal buttons, answered only by a real click; the answers are remembered; "Not now" and "Never" send no frame |
| 5 | Ask it where to click for something on Home ("where do I see what needs me") | A ring and a ghost cursor show the place; it never clicks |
| 6 | Start any routine run from Routines | The window minimises, the corner pill shows what is happening in about five words and Stop; the window does not pop back unless something needs you |
| 7 | Press Stop on the pill, or Option-Shift-Command-K | Everything stops; the pill says so, and the Stopped card stays until you press Resume. Press Resume, and check that `data/KILL` is gone |
| 8 | Optional: on Home type a task in "What should Knack do?" and press Enter. Do not press Allow unless you mean a real task: an allowed task starts your own Claude command and spends your Claude account (US$2 limit by default) | A plain line, then a consent card that says what the agent can do, with two buttons of one size; nothing starts before you press |

## The supervised click test (R1), only if you want to do it tonight

It is the first real-click rung and the gate for "click when I say so". The lead runs the commands; you press the keys it asks for. Full steps and stop rules: `evals/agentic/REAL_CLICKS.md`.

1. Open TextEdit with one new empty document, nothing else of TextEdit's on screen. Turn on Do Not Disturb.
2. In your own Terminal (not the lead's): `uv run python scripts/real_click_preflight.py --press-hotkey --attest-dnd --attest-clipboard-manager-off`. It asks you to type YES and to press Option-Shift-Command-K once.
3. The lead gives you the dry-run command and a one-time token; you run the real command with the token; click TextEdit's window once during the countdown, then keep your hands off.
4. If anything surprises you, press Option-Shift-Command-K, or `touch data/KILL` from a second terminal.

Only after a passing R1 does Knack's voice "do it for me" turn on (and even then it needs a real click on an Allow card each time).

## If something is wrong

- The app does not open: say so; the lead runs it from the terminal to read the error.
- No voice: check the Gemini key line in `.env` is present (never paste it into chat); the status line in the sidebar says "Live models" or "Running with example data".
- A permission prompt did not appear: System Settings, Privacy and Security, Microphone or Speech Recognition, switch Knack on. Revoke the same way.
