# QA status (living document, owner: QA)

Clock: freeze 15:10 GMT, submission 15:40. Times are GMT. "Verified" means I ran it. Real runs use the real Gemini services; the screen is the demo stage painted by a dev hook (`src/main/dev`) because the agent-launched Electron has no Screen Recording grant (real `desktopCapturer` is NOT verified, see risks).

How to run: `npm run e2e` (mock, headless, ~25 s) | `npm run e2e -- --mode real --visible` (real services, stage on screen) | `... --accuracy` (point_at accuracy -> `docs/QA_ACCURACY.md`) | `--with-accuracy`, `--files a,b`, `--record` / `--replay[=hybrid]`. Only one Electron at a time (`scripts/electron-lock.sh`), the runner handles it.

## Security: debug server is opt-in (done)

The debug HTTP server (127.0.0.1:7777: `/shot`, `/state`, `/tool`, `/settings`, no auth) used to start in every unpackaged build. It now starts only when `ALONGSIDE_DEBUG=1` (`src/main/index.ts`). `scripts/electron-lock.sh` and `tests/e2e/run.mjs` export it (so e2e, preflight probe and every agent harness that goes through the lock keep working); `scripts/demo.sh` does not, so a stage launch has no debug surface. Consequence for the demo laptop: `curl 127.0.0.1:7777/shot` only works if you deliberately launch with `ALONGSIDE_DEBUG=1 npm run dev` (noted in `docs/MANUAL_TESTS.md`). `preflight`'s "Alongside already running" row cannot see a normal demo instance any more (it probes `/health`); harmless.

## FINAL GATE NUMBERS (re-run 15:27 GMT, after AGENCY's fix; these supersede the 15:23 table below)

| Gate | Result |
|---|---|
| `npm run typecheck` | PASS |
| `npx vitest run` (unit coverage, mock/fake services only) | PASS: 76 files passed, 7 skipped; 1403 tests passed, 27 skipped, 0 failed |
| `npm run build` | PASS |
| Secrets scan (`AIza` + 30 chars, whole repo incl. untracked, `.env` excluded) | 0 files |
| `node scripts/submit-check.mjs` | PASS 11, WARN 3, FAIL 0. WARN: LICENSE missing (accepted by user), repo PRIVATE, showtime `clips/` empty |
| Preflight network rows (15:25) | All OK (key, models, latency p50 43 ms, Live smoke, wake token). WARN: persona voices TBD for marcus, amelia; demo seed not applied |
| Preflight macOS rows (Screen Recording, real screen grab, Microphone, hotkeys) | NOT RUN: the Electron lock was held by other testers (ptr, uix, macC) at 15:24, 15:25 and 15:27. Must be run on the demo laptop from the stage terminal. |
| Mock e2e (practice-desktop test, last run 14:49, before freeze fixes) | 7 files / 61 tests passed, 24 skipped; not re-run after the freeze, not product evidence |
| Real-macOS pointing/agency by QA | NOT RUN; real clicks are dry-run verified only |

## Earlier run (15:23-15:26 GMT)

Evidence class: unit tests, build and static checks only. Anything run against the stage is a "practice-desktop test", not product evidence. No real-macOS pointing/agency run by QA (the Electron lock was held by MAC-C, PTR, UIX and VIDEO the whole window); real clicks are dry-run verified only.

| Gate | Result |
|---|---|
| `npm run typecheck` | PASS (node + web) |
| `npx vitest run` | 1 FAILED, 1393 passed, 27 skipped (74 files passed, 1 failed, 7 skipped). Failure: `tests/agency/act-for-me.test.ts:194` "two unchanged screens in a row: gave_up" expects `steps: 2`, got `steps: 1` (deterministic, 2 runs). Routed to @AGENCY on bus.md. |
| `npm run build` | PASS |
| Secrets scan (`AIza` + 30 chars, whole repo incl. untracked, `.env` excluded, nothing printed) | 0 files |
| `node scripts/submit-check.mjs` | PASS 10, WARN 3, FAIL 1. FAIL is the vitest row above. WARN: LICENSE missing (accepted by user), repo PRIVATE, showtime `clips/` empty. |
| `node scripts/preflight.mjs` (2 runs) | Network rows all OK: key, 60 models visible, p50 43 ms, Live smoke (connect 890 ms, audio 376 ms), wake token. WARN: persona voices TBD for marcus, amelia; demo seed not applied to `~/.alongside-demo`. 4 FAIL rows (Screen Recording, real screen grab, Microphone, global hotkeys) are "not checked: another Electron instance holds the lock", NOT permission failures. Those must be re-run on the demo laptop from the stage terminal. |
| Live API calls by QA | about 12 (two preflights) |

## Quality gate (earlier, 14:45-14:50)

| Gate | Result | Last run |
|---|---|---|
| `npm run typecheck` | PASS (node + web projects, no errors) | 14:48 |
| `npx vitest run` | 2 FAILED, 1342 passed, 27 skipped (67 files passed, 1 failed, 7 skipped): both in `src/main/showtime/service.test.ts` (DEMO lane, in flight, routed on bus.md). Earlier run at 14:45 was fully green: 1314 passed, 27 skipped. | 14:48 |
| `npm run build` | PASS | 14:48 |
| `npm run e2e` (mock, headless, under the lock, includes `09-v2` and the `07-security` secrets scan) | PASS: 7 files passed, 61 tests passed, 24 skipped (real-services-only tests); plus `08-privacy-spend` 1 passed / 1 skipped (runtime image check needs real mode). `09-v2`: 11 passed incl. showtime start/stop, 1 skipped (`act_for_me` confirmation needs the real computer_use loop, `ALONGSIDE_AGENCY_LOOP=1`, not run). Earlier run flagged a synthetic `AIza...` literal in `tests/files/text.test.ts` (not the real key); FILES fixed it. | 14:49 |
| Secrets scan (repo files, `AIza` + 30 chars, `.env` excluded) | 0 files match | 14:50 |
| Debug-server gate (SECURITY P1) | PASS, verified on a real headless launch: no `ALONGSIDE_DEBUG` -> nothing on the port (connection refused); `ALONGSIDE_DEBUG=1` -> `/health` 200 | 14:50 |

## P0 acceptance matrix

| # | Criterion | Status | How verified | Last run |
|---|---|---|---|---|
| 1 | Wake / hotkey / button starts a session | PASS for button path with real Live: `POST /wake` -> `connecting` -> `live` in 1.0 s, persona set, second wake switches persona, Stop returns to resting. Spoken wake word and global hotkey UNVERIFIED (need a person; `docs/MANUAL_TESTS.md`) | e2e `06-lifecycle` (real) | 14:08 |
| 2 | `point_at` lands on the correct target | PASS on the stage: 33/34 centre-in-true-rect (97%), median centre error 0.26% of the screen, 5/5 absent targets `found:false`, ring painted at the requested pixels (5/5). Real `desktopCapturer` + real desktop UNVERIFIED | `docs/QA_ACCURACY.md` | 14:03 |
| 3 | Verification tick on a completed step; repair on a wrong step | wrong step PASS (real: `verify_step` -> completed false, no tick, repair hint reaches the voice). Completed-step tick: re-running after a test fix (UNVERIFIED) | e2e `02-lesson` | 14:08 |
| 4 | Level chip fades Walk -> Nudge in demoMode | UNVERIFIED (test fixed, re-running) | e2e `02-lesson` | - |
| 5 | Captions + working Stop | Stop PASS (clears lesson, overlay, pending confirm; idempotent). Captions in dock/overlay UNVERIFIED by test (need transcript events from a real voice) | e2e `06-lifecycle` | 14:08 |
| 6 | Scam Shield highlights red flags; honest "can't tell" | PASS (real): scam text -> `likely_scam`/`suspicious` with flags; genuine text never "safe"; gibberish -> `cannot_tell`/`suspicious`; injection text becomes a red flag, not obeyed; highlights drawn over the staged message | e2e `03-scam` | 14:08 |
| 7 | `spawn_agent` chips | PASS (real): chip appears, runs, completes, result injected as `[AGENT_RESULT kind=... id=...]`; max 3 concurrent, 4th refused in plain English | e2e `03-scam` | 14:08 |
| 8 | Settings toggles take effect | PASS: all 15 booleans flip, invalid values dropped key-by-key, voiceSpeed bounds, locked level pins level, persisted to settings.json, `scamShield` off refuses scam_check, `carerSharing` off refuses lesson_summary | e2e `05-settings`, `03-scam` | 14:08 |
| 9 | `doItForMeAllowed` default false | PASS (fresh profile) | e2e `05-settings` | 14:08 |
| 10 | `ask_user_confirm` clears only on a real answer | PASS: not clearable by `/inject`, settings, other tools, overlay captions, model text; a script `el.click()` is ignored (isTrusted guard); a trusted mouse click answers with exactly that option; Stop cancels as `null` | e2e `07-security` | 14:05 |
| 11 | Screenshots use `store:false` | PASS static (`gemini/client.ts` forces it on every `interactions.create`). Runtime request-body check ran with 0 image requests in that run; re-checked in the accuracy run (see below) | e2e `08-privacy-spend` | 14:05 |
| 12 | No secrets in logs / repo / bundles / state | PASS (app log, userData, `out/`, whole repo, `/state`, `/health` scanned for the key shape and the real key value) | e2e `07-security` | 14:05 |
| 13 | Debug server loopback only, rejects Origin / foreign Host | PASS (lsof: 127.0.0.1 only; Origin and foreign Host give 403; LAN address refused; malformed JSON gives 400) | e2e `07-security` | 14:05 |
| 14 | Failure paths: plain English, no stack traces | Grounder 500/429/401/network/garbage/empty PASS (`found:false`, nothing drawn, no jargon); Verifier failure never ticks PASS; Scam analyst API error PASS. Raw API error shown by the wake spotter FAIL (BUG-1). Architect (custom goal) timeout: re-running | e2e `04-failures` | 14:08 |

## Open bugs

| ID | Sev | Owner | Title | Status |
|---|---|---|---|---|
| BUG-1 | P1 | WAKE | `state.lastError` shows `Voice activation is unavailable (Error invoking remote method 'wake:token': ApiError: {...})` when the wake-token call fails (spotter.ts:174 interpolates `error.message`); main log prints a full stack | reported 14:07 |
| BUG-2 | P1? | LIVE | Real session did not end by itself within 45 s of silence; phases cycled `live/thinking/speaking` for 11+ s and `/state` then stopped answering for ~35 s in my probe. Needs more data (run 8 records poll latency) | investigating |
| NOTE-1 | P3 | ARCH | `session:ended` does nothing (no runner abort, no overlay clear, no confirm cancel) when phase is already resting, so a debug-started lesson or confirm survives Stop | not reported (unreachable in normal use) |
| NOTE-2 | P3 | SERVICES | Boxes for dropdown menu items are sometimes the whole menu (`messages.thread.report`: IoU 0.29, centre 3.7% off) | info |

## Risks

- Real `desktopCapturer` is blocked here (no Screen Recording grant for the agent-launched Electron). Everything above used the stage-window capture. The demo machine MUST be checked: `curl 127.0.0.1:7777/shot` must show the real screen (`docs/MANUAL_TESTS.md` part 1).
- Voice and wake word cannot be tested headlessly; the real Live session does connect and talk (phase `live` in 1 s, the model spoke unprompted in my run).
- Venue Wi-Fi: Gemini HTTP calls can be recorded and replayed (`--record` / `--replay`, see below). Live voice cannot.
- Lock contention: every role shares one Electron slot; keep runs short.

## Record / replay backup (venue Wi-Fi)

Code: `src/main/dev/replay/` (4 unit tests). `ALONGSIDE_RECORD=1` saves every successful Gemini JSON response keyed by a hash of the request (image bytes ignored, so the same prompt on the same stage screen hits); `ALONGSIDE_REPLAY=1` serves them and fails like a dead network on a miss; `ALONGSIDE_REPLAY=hybrid` serves hits and passes misses through. Dir: `ALONGSIDE_REPLAY_DIR` (default `<userData>/replay`). Covers Grounder, Verifier, Architect, Scam, Router (all use `interactions.create` over `fetch`). Not covered: Live voice, wake transcription, token minting.
Status: recording done in the 14:03 accuracy run (`.userdata-replay/`); offline replay proof pending.
