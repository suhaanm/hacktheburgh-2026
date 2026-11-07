# REQ-5 plan: models, always-on awareness, activation, new look and logo

Approved by the owner on Sat 7 Nov 2026 (about 17:05 GMT). Status: BUILDING. Artifact (overview for the owner): https://claude.ai/artifact/C49jKSKjM8xRfH7zi2K65y

Owner's answers: awareness = **triggered glances plus opt-in periodic glances**; activation = **hotkey, menu bar and proactive cards, plus an on-device wake word (stretch)**; Gemini key = **paid tier, so real-screen glances are allowed but stay opt-in**; go-ahead = yes. The Gemini key is in `.env` as `GEMINI_API_KEY`. **Never print it, never put it in a renderer, a log, a prompt, a test fixture or git.** Renderers get ephemeral tokens from main only.

## 1. Models today (verified 7 Nov)

OpenAI through `understudy_agent.models.get_model_port()`: planner `OPENAI_MODEL_PLANNER` (gpt-5.5, effort low), fast `OPENAI_MODEL_FAST` (gpt-5.4-mini, effort none), computer use `OPENAI_MODEL_COMPUTER_USE` (gpt-5.5, effort low). Local: Qwen2.5-7B Q4_K_M on loopback (flag off). Voice: ElevenLabs River (`UNDERSTUDY_VOICE=0`). Gemini: not used by any live path; the owner's old Alongside code in `apps/desktop` (Live voice, wake spotter, file embeddings, grounding) is flagged off and its model IDs in `apps/desktop/src/shared/models.ts` are the old project's defaults. The key sees 61 Gemini models, including `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`, `gemini-3.1-flash-live-preview`, `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.5-transcribe-live`, `gemini-4-argon`, `gemini-embedding-2`, `gemini-3.8-flash-tts`, `gemini-2.5-computer-use-preview-10-2025`. **Do not hard-code model IDs**: read them from the environment and check them at boot with `models.list` (OpenAI and Gemini).

## 2. Proposed role split (code decides; the first model in a role has a fallback in another provider)

| Role | Primary | Fallback | Status |
|---|---|---|---|
| Planning, agent runs, claim checks | OpenAI planner | none (mock) | unchanged |
| Fast structured checks | OpenAI fast | rules | unchanged |
| Computer use | OpenAI computer | none | unchanged; real clicks frozen |
| Pointing and annotation boxes | Gemini flash-lite, escalate to flash when not found or confidence under 0.7 | OpenAI fast with a box prompt | **measure first** |
| Glance (screen state as enums, optional box) | Gemini flash-lite | OpenAI fast (vision) | **measure first** |
| Independent verifier of agent runs | Gemini flash-lite, other family from the actor | same-family verifier | **measure on the live grid** |
| Voice conversation | Gemini Live, hold to talk | text | phase D |
| Spoken coach lines | ElevenLabs River, cached | none | flag off until integrated |
| Private text digests | Qwen local | rules | unchanged |
| Argon | dropped | | |

The old project's 31 Oct benchmark (`apps/desktop/docs/GROUNDING_AB.md`: flash-lite 95% hit on 59 targets, 15 of 15 absent targets rejected, p50 0.88 s, p95 1.2 s; flash 98% on 78 targets, p50 3.8 s; Argon p95 14.5 s) is old-project evidence on the old key. **Every claim about Gemini here must be re-measured on our own sandbox cases (n at least 60, p50 and p95, intervals) and labelled with its origin before it is used to choose a model.** The bake-off is `evals/modelbench/` (MODELS track).

## 3. Awareness ladder (SPEC IDs: new AWR-1..6)

0. **Always on, on this Mac, no pixels**: input rhythm, cursor dwell and wandering (Electron `screen.getCursorScreenPoint()` needs no permission), app and window kind (never titles stored), browser events (hashed labels). Feeds the existing stuck hazard and expert-path comparison. Leaves the device: nothing.
1. **Triggered glance**: when stuck probability crosses its threshold, a loop signature appears (clickyyy idea), or the worker presses the hotkey. One downscaled frame (JPEG, long edge at most 1280) held in memory, sent through the egress guard to the glance model, never written to disk. Skipped when macOS secure input is on, the frontmost app is on the denylist (password managers, banking categories, messaging by bundle id, worker additions), or the window kind is unknown and the worker chose strict mode. Output: enums plus an optional box, a closed schema: `app_kind`, `task_phase`, `blocker` (enum), `confidence`, `box_2d` optional. No free text is stored.
2. **Periodic glance (opt-in, off by default)**: about every 30 s while a work session is on; pauses on idle, lock, screen share or denylisted app; hard caps per hour and per day in dollars; the count shows in the menu bar and the Privacy screen.
3. **Judge, verify, prepare, press-to-fire** (the PRO track): code decides whether a card shows; at most 3 at once; implicit labels from reactions (Pupil idea) train the bandit; nothing runs without a press.
4. **Live session (opt-in, explicit)**: hold the hotkey, talk; Gemini Live hears you and sees low-rate frames; timer, menu-bar indicator, ends on idle. Phase D.

Controls: attention budget (suggestions per day), per-app off, pause for an hour, editable denylist, a ledger of everything that left (size, hash, model, latency, cost; never the image).

Privacy rules (extend `CLAUDE.md`): screen frames are never stored; image egress only through the privacy spine; glance and periodic modes are opt-in and visible; cloud glances never run on a frame from a denylisted app or secure input; the worker can see every call in the ledger; unattended runs never use real-screen glances.

## 4. Activation

Drop the old personas (Marcus, Amelia) and the cloud wake listener from the UI and settings. One identity: **Understudy**, River voice. Hold-to-talk global hotkey (default `Option+Space`, configurable), menu-bar click, proactive cards. On-device wake word is a stretch goal (a small local keyword spotter; a model download needs the owner's OK first).

## 5. Look, shell and logo (VIS-9, new VIS-10)

- Annotation layer: hairline ring with corner ticks, one 11 to 12 px label, one annotation at a time, mono step pill, ghost cursor as a small dot with a short trail, no glow, no loops. In flight under REQ-4.
- No permanent level chip: the level shows for two seconds when it changes and lives in the menu bar and settings. Stop all is a small pill shown only while an agent acts; the kill hotkey always works.
- Presence in the menu-bar icon only.
- Logo: `packages/design/brand/` (mark, glyph, tray template). Export `icon.icns` (all sizes), `trayTemplate.png` and `@2x`, wire to dock, tray and installer.
- The whole desktop panel, dock, settings and toast move onto `packages/design/tokens.css`. The owner will send a newer design system; keep tokens in one file so it is a swap.

## 6. Tracks and file ownership (one directory per agent; no shared files)

| Track | Owns | Phase |
|---|---|---|
| DESKTOP (existing) | `apps/desktop/src/renderer/overlay/**`, `design/annotation-style.ts`, then shell: `renderer/{design,dock,hud,toast}`, `main/{tray,windows,hotkey,hud,settings}.ts`, personas and wake removal, logo wiring, `build/` icons | A |
| AWARENESS (new) | `apps/desktop/src/main/awareness/**` (new), `services/engine/understudy_engine/awareness/**` (new), glance schema in `packages/schema/` | B |
| MODELS (new) | `services/agent/understudy_agent/models/**`, `evals/modelbench/**`, role routing config, boot check, cost and latency meter | C |
| PRIVACY (existing) | `understudy_engine/privacy/**`: add the image payload kind | B |
| LIVE (later) | `apps/desktop/src/renderer/live/**`, `main/live-*.ts` | D |

## 7. Cut lines

Live voice first, then periodic glances, then recorded-expert pack authoring. Everything is flagged off by default (`UNDERSTUDY_X_AWARENESS`, `UNDERSTUDY_X_GEMINI`, `UNDERSTUDY_X_LIVE`); the lead turns a flag on only after seeing it work end to end.

## 8. Honesty

No Gemini speed or accuracy claim without our own measurement and origin label. The glance model's output is a feature for the existing statistical layer, not a decision-maker. The new look is judged by looking at it rendered, in light and dark, at 1440 by 900 and 390 by 844.
