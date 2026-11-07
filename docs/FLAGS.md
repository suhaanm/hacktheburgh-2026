# Flags and provider (D48, D49)

Decided 7 Nov 2026 about 22:30 GMT on the owner's chat instruction: enable every feature fully and by default in the code, unless it competes with something that adds exactly the same functionality; and, because the OpenAI key was revoked, move every role that was on OpenAI to a Gemini model (never Argon).

## How the defaults work

A running service applies `DEFAULT_ON` once at startup (`understudy_engine/api/flags.py: apply_default_flags`, called by `understudy serve`, `python -m understudy_agent.server` and the demo seed script; the desktop does the same after loading `.env`: `apps/desktop/src/main/default-flags.ts`). An unset or empty variable becomes `1`. **An explicit `0` always wins**, in the shell or in `.env`, so any default can still be turned off for one run. Tests never call the helper, so layers stay off in the test environment unless a test turns them on.

## On by default

| Flag | What it turns on | Notes |
|---|---|---|
| `UNDERSTUDY_X` | Every engine and agent extension layer: privacy, local model, calendar, git, proactive, Cue, awareness, evidence, attention, repeat list, insights, background agents, model routes | Awareness still sends no frame until the worker records consent (below) |
| `UNDERSTUDY_X_GEMINI` | Gemini routes for glance, pointing, verifier, and now every role | Through the egress guard and the ledger |
| `UNDERSTUDY_X_LIVE`, `UNDERSTUDY_FLAG_VOICE` | Live voice in the desktop build | Hold to talk only; no always-listening microphone. The agent service's `live` router does not exist (agent health shows `live: false`): Live voice is a desktop feature |
| `UNDERSTUDY_VOICE` | ElevenLabs spoken lines | Fixed vocabulary. Cue still speaks only on request (D36) |
| `UNDERSTUDY_EVIDENCE_CLOUD` | A cloud wording attempt for "explain this" | Always behind the number check, template fallback. Now routes to Gemini |
| Desktop: voice feature and the Cue, awareness, Gemini and Live experiments | Same, in the Electron main process | `UNDERSTUDY_X_<NAME>=0` turns one off |

## Off on purpose, and why

| Flag | Why it stays off |
|---|---|
| `UNDERSTUDY_REAL_ACTUATOR` | The arm switch for real desktop clicks. The owner's own rule is rung-by-rung approval in chat; only the read-only rung R0 has run; the independent reviewer's verdict is NO-GO for model-driven (R2) and unattended (R3, R4) real clicks; and with the switch on by default the unattended off-hours path could construct a real actuator. A real click already needs a one-time owner token, a countdown and the owner present, per run: the documented R1 command arms it for that run only. Say "run R1" and we do it together |
| `ALONGSIDE_AGENCY_LOOP` | The old Alongside multi-step loop. It duplicates our own agent loop (the Python tier-3 actuator behind the eight layers), without those layers |
| `UNDERSTUDY_JXA_CLICK` | An alternative implementation of the same legacy click. It has only been run against fakes. Off while the legacy actuator is off |
| `UNDERSTUDY_LEGACY_REMOTE` | Lets the old Alongside paths send screenshots and file text to remote models outside the ledger. It duplicates the ledgered Gemini paths and breaks the rule that frames leave only through the egress guard (D30) |
| `UNDERSTUDY_FLAG_WAKE` | The cloud wake-word listener was removed from the code (D29/D30) and competes with hold-to-talk |
| `UNDERSTUDY_FLAG_SCAM`, `UNDERSTUDY_FLAG_FILES` | Old Alongside features that send screen or file content to remote models through the legacy path; not part of the product |
| `UNDERSTUDY_VOICE_DEBUG_TEXT` | A developer escape hatch that disables the fixed-lines rule for speech |
| `UNDERSTUDY_CU_FRAME_HINT` | A frame hint for the computer-use model. The pre-flight run where it was on got stuck loops; the confirmed configuration has it off |
| `UNDERSTUDY_INSIGHTS_HELDOUT` | A run-once guard so the held-out evaluation cannot run by accident |
| Periodic awareness glances (about every 30 s) | Frames leave the device only with the worker's recorded consent (owner decision D30) and macOS Screen Recording, which only the owner can grant. The consent card is one click |

## Provider (D49)

The OpenAI key was revoked by OpenAI ("Your API key has been invalidated") and the owner moved every OpenAI role to Gemini:

| Role | Model (from the environment, checked at boot with `models.list`) |
|---|---|
| Planner | `GEMINI_MODEL_ACCURATE` (gemini-3.8-flash) |
| Fast checks, reader, classifier, glance, pointing, verifier | `GEMINI_MODEL_FAST` (gemini-3.5-flash-lite) |
| Computer use | `GEMINI_MODEL_COMPUTER_USE` if set, otherwise the accurate model |
| Live voice | `GEMINI_MODEL_LIVE` (gemini-3.8-live) |
| Spoken lines | ElevenLabs (unchanged) |
| Private digests | local Qwen (unchanged) |

`UNDERSTUDY_PROVIDER=gemini` is the default (`models/factory.py`); OpenAI stays in the code as an explicit opt-in (`UNDERSTUDY_PROVIDER=openai`) and is never consulted otherwise. Argon (`gemini-4-argon`) is never configured; a test guards it. Every number measured earlier with the OpenAI models (computer use 3 of 3 on development households, 1 of 4 held-out, the injected runs) is evidence about that configuration, not about Gemini.

## Live mode

`make live` runs the whole stack with the real models and voice (keys from `.env`, never printed): `UNDERSTUDY_MOCK=0`, an isolated home under `data/live-home` and `data/live-data` (never your real `~/.understudy`), the example content seeded once. It costs real money per agent run. `make demo` stays the offline mock walkthrough.
