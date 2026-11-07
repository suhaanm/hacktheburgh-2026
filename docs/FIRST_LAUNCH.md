# First launch together (about 15 minutes)

Written 7 Nov 2026 for the midnight session. The lead does the technical steps; you do the three things only you can do: grant macOS permissions, speak, and watch the screen. Nothing here touches a real account or a real purchase.

## Before you start (the lead)

1. Merge and test the checkpoint branches, rebuild the dashboard and Knack.app, restart the stack in live mode (`make live`).
2. Confirm: `curl -s http://127.0.0.1:7700/health` shows `mock: false` and `provider: gemini`.
3. Tell you the app path (`apps/desktop/dist-app/`) and that it is ready.

## Your part, in order

| Step | What you do | What should happen |
|---|---|---|
| 1 | Open Knack (the app from the folder above; right-click, Open the first time because it is unsigned) | A window about 80% of the screen, the Knack logo in the sidebar and the Dock, five items on the left, one sentence on Home |
| 2 | macOS asks for Microphone, then Speech Recognition: Allow both | A small listening dot in the menu bar. If macOS says on-device recognition is not available for your language, Knack prints one line and stays off: it never uses server recognition |
| 3 | Say "Hey Knack" | The pill shows "Listening", a soft cue, Knack speaks (Gemini voice) |
| 4 | When it asks "Knack may look at your screen while we talk": choose Yes, Not now or Never | Equal buttons; the answer is remembered; "Not now" and "Never" send no frame |
| 5 | Ask it where to click for something on Home ("where do I see what needs me") | A ring and a ghost cursor show the place; it never clicks |
| 6 | Start any routine run from Routines | The window minimises, the corner pill shows what is happening in about five words and Stop; the window does not pop back unless something needs you |
| 7 | Press Stop on the pill, or Option-Shift-Command-K | Everything stops; the pill says so |

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
