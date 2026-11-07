# Live voice (REQ-5 phase D): hold to talk

Voice is OFF. It exists only when `UNDERSTUDY_X_LIVE=1` and `UNDERSTUDY_FLAG_VOICE=1`, the worker opted in (consent text in `src/main/live/settings.ts`), the kill switch is off, no agent is acting, macOS has already granted the microphone, and the spending caps have room. Spoken pack lines also need `UNDERSTUDY_VOICE=1`. With the flags off, `manager.start()` creates no timer, no listener and no network call.

## Where things live

| Part | File | Runs in |
|---|---|---|
| Hold-to-talk in, one conversation at a time, start gates, breaker | `src/main/live/manager.ts` | main |
| One conversation: lifecycle, limits, server events, tools | `session.ts` | main |
| The ONE place that sends (audio, frames, control), with the gates, caps and ledger | `egress.ts` | main |
| Websocket (token in an `Authorization: Token` header, never a URL) | `connection.ts`, `wire.ts` | main |
| Ephemeral token (key in one header, model-locked, one use) and the model boot check | `token.ts` | main |
| Gates (consent, kill, pause, unattended, secure input, denylisted app, lock, screen share) | `gates.ts` | main |
| Ledger rows (frames and one per audio turn, before sending) | `ledger.ts` | main |
| Cost and usage (by time and by tokens), the day total, circuit breaker | `meter.ts` | main |
| The four tools and the strict parser | `tools.ts`, `tool-host.ts` | main |
| Cue hooks `CueVoice.listenOnce`, `CueSpeaker.say` | `cue-hooks.ts` | main |
| Microphone and speaker over a narrow IPC bridge | `bridge-ipc.ts`, `preload-api.ts`, `renderer/live/bridge.ts` | main and the dock renderer |
| Real adapters (Electron, probes, HTTP ports) | `electron.ts` | main |

The Gemini key lives only in `.env` and is read in `token.ts` (to mint a token) and `manager.ts` (to check it is set). No renderer holds a key, a token, a websocket or a model call; the old renderer-side Alongside session was removed.

## What a conversation does

1. The talk key goes down (`talk {press}` from `main/hotkey.ts`): the manager checks every start gate, then opens the microphone (the renderer, on main's command) and the socket together. Audio spoken while the socket opens is held in memory (at most about 3 s) and sent first, through the same gates.
2. The microphone is open only while the key is held. On release (inferred about 450 ms after the key repeat stops) main sends 700 ms of silence and the stream end, and the model answers.
3. The model's audio is played by the renderer. A new press while it speaks cuts it off at once.
4. It ends on: release plus a quiet grace (8 s), a held key with no sound for 60 s, the hard cap (5 minutes), the kill switch, an agent starting to act, an unattended gate, a cost cap, a spoken goodbye (`end_session`), a lost connection, Stop.
5. Tools the model may call (and nothing else): `point_at(description)` (ring on screen; the DOM first, then the vision route; the model hears only found true or false), `show_step(step_id)` (an id from the closed candidate list), `ask_choice(options)` (2 to 4 ids from the same list, opens Cue's question card), `end_session()`. Unknown tools, unknown arguments, ids outside the list and bad descriptions are refused and the model is told so. There is no tool that can click, type, run, send or open anything.

## What leaves the machine, and the record of it

- Audio: only while the key is held, only through `egress.ts`, announced to `POST /privacy/ledger/live/audio` before the first chunk of each turn and completed with seconds and bytes (the engine stores only a range). Nothing is sent if the ledger refuses or cannot be reached.
- Frames (a separate opt-in, `liveFrames`): at most one every 5 s, long edge at most 1024 px, JPEG, held in memory, zeroed after use. A frame older than 4 s when it would be sent is dropped, never re-sent. Announced to `POST /privacy/ledger/live` before sending; the gates are read before the screen is even captured.
- Never stored by Understudy: audio, transcripts, frames. The usage log (`live-usage.jsonl`, 0600) holds counts, seconds, dollars and enums only. A conversation asks the server for NO transcript of either side. (Observed 7 Nov: the server still sends the model's own output transcript; it is dropped on arrival, never kept, never logged.) Only Cue's one-answer turn asks for the worker's words, holds them in memory for that turn and hands them to the one caller that asked.

## Context engineering (REQ-8)

The system instruction is one short fixed text (`prompt.ts`): nothing from the worker, a file, the memory file or a page is ever put in it. What the model gets beyond the audio: the closed menu of at most 6 pack steps (ids with the pack's own labels, in the tool descriptions), the pack chip text and `The worker chose: <pack label>` after a card answer, closed JSON tool results, and a frame at most every 5 s (a frame older than 4 s when it would be sent is dropped, never re-sent). The provider's running context is compressed past about 8000 tokens down to about 4000 and a conversation is at most 5 minutes.
- Gate precedence matches `privacy/image.py`: unattended always blocks, then secure input, a denylisted app, no consent.

## Cost and caps (estimates, labelled assumptions)

Prices default to the vendor's public figures as read on 7 Nov 2026 (the page is undated) and can be set with `UNDERSTUDY_PRICE_GEMINI_LIVE_*`. Two estimates are kept (by time, and by the server's own token counts per modality) and the larger drives the caps: per conversation (`liveSessionUsd`, default US$0.15) and per day (`liveDailyUsd`, default US$0.50). The provider's running context is compressed past about 8000 tokens down to about 4000, so a conversation does not grow without bound.

## Settings (own store, `live.json` in userData; keys can be folded into `shared/settings.ts` later)

`liveEnabled`, `liveFrames`, `liveSessionUsd`, `liveDailyUsd`, `liveGraceMs` (8000), `liveIdleMs` (60000), `liveMaxMs` (300000, never above 5 min), `liveFrameIntervalMs` (5000, never under 5 s), `liveVoiceName`, `liveConsentVersion`, `liveConsentAt`, `livePausedUntilMs`. An untrusted source (debug server, model tools) can only turn things down.

## Tests

`npx vitest run src/main/live src/renderer/live` (hermetic: a loopback websocket server that speaks the protocol shapes, a fake audio bridge, a manual clock). The real-model smoke is manual: `cd apps/desktop && ../../scripts/heavy.sh uv run --env-file ../../.env npx vitest run --config tests/live-model/vitest.live.config.ts` (synthetic speech from macOS `say` as the microphone, a fixture screen image as the frame, a temporary privacy engine for the ledger; costs a few cents).

## Found by testing against the real model (7 Nov 2026)

- A token locked to a model WITHOUT a field mask locks the whole setup, including the empty tool list: the model never saw a declared tool (0 tool calls in 12 turns). The minter now sends `fieldMask: "model"`; with it the model calls the tools (verified, see the smoke numbers in the build report).
- With a `SILENT` tool result the model says nothing after calling a tool, so the ring or chip appeared without words. Screen-changing tools now return `WHEN_IDLE` (one short spoken sentence); the question card and goodbye stay silent.
- `manual` turn mode (activityStart/activityEnd) first gave no reply because the start marker was sent after the buffered audio of the first turn; after fixing the order it answers (5 turns: first response p50 729 ms, p95 1436 ms) against `vad` (12 turns: p50 839 ms, p95 1365 ms), both on a machine with load average 70 to 97, fixture speech. The difference is not significant at this n; `vad` stays the default.
- A server-side transcript of the model's own words arrives even when not requested (dropped on arrival).

## Honest limits

- The real microphone, speakers and screen capture have not been exercised by the build agent (they need the owner's macOS grants). Echo is avoided by design (the microphone is closed while the model speaks) but untested on real speakers.
- The turn-mode default is `vad`; `manual` works but has only 5 measured turns.
- The dedicated transcription model path for Cue (`GEMINI_MODEL_TRANSCRIBE`, text answers) is tested against the fake server only; without that variable Cue's listening turn uses the Live model and discards its audio.
- Audio and frames are ledgered per turn and per batch, not per chunk; the sound itself is not recorded anywhere.
- Latency numbers depend on machine load; the smoke records the load average per turn.
