# REVIEW-PRIVACY: privacy and honesty review of Understudy

Reviewer model: claude-sonnet-5-5 (Claude Sonnet 5.5). Read-only apart from `evals/review/`. Written 7 Nov 2026, 17:20 to about 17:55 GMT, against the working tree at that time (many fixes landed while I reviewed; each finding carries its state at the end of the review).

Disclosures (read these first):
1. **`.env` was opened once, by accident.** My first key-shape scan walked the repo root and opened `.env` as bytes to count regex hits. Nothing was printed except per-file counts (`.env`: 1 OpenAI-shaped, 1 ElevenLabs-shaped, 2 assignment-shaped matches). I excluded it from every later scan and used `git grep` and the tracked-file list. I cannot check the key values in `.env` themselves, and did not try.
2. **I caused the 17:34 `data/KILL`.** The engine's `POST /kill` (`services/engine/understudy_engine/routes_data.py:255`, `post_kill`) calls `_notify_agent_kill()`, which posts to the agent at the default `AGENT_PORT` 7710, the live service. My in-process kill-switch reproducers and a route-probe script (about 17:33 to 17:35) set `UNDERSTUDY_DATA_DIR` but not `AGENT_PORT`, so the notification reached the live agent, which wrote the real `data/KILL`. Since then every reproducer runs under `evals/review/conftest.py` (AGENT_PORT=1, a tripwire on live ports, tmp data and home). Later writes to `data/KILL` (17:46, 17:48) were not mine. I never wrote or cleared `data/KILL`.

## 1. Result in one screen

No Critical finding (nothing found that exposes personal data to a third party with no opt-in and no flag). Six High findings; five are fixed and re-verified by me, one is partly open.

| # | Sev | Finding | State at 17:55 |
|---|---|---|---|
| H1 | High | `POST /voice/speak` sent any text (4000 chars) to ElevenLabs, no ledger row | **Fixed**, verified, attacked |
| H2 | High | P0 model calls (raw page text) not in the ledger unless `UNDERSTUDY_X_PRIVACY=1` | **Fixed**, verified non-mock with a fake provider |
| H3 | High | Origin allow-list was `startswith("http://127.0.0.1")`: any site can write to worker-only routes (ledger clear, spawn agent runs); queue approve had no check | **Fixed on the engine**; agent service (:7710) **open** |
| H4 | High | Any website could set and clear the kill switch; no route checked `Host` (DNS rebinding reads everything) | **Fixed on the engine; agent service open** |
| H5 | High | The live `study` section could be fed from simulated participants (no provenance check on `participants.csv`) | **Fixed** (manifest required), verified |
| H6 | High | Image and file text still go to OpenAI and Gemini from the TypeScript main process with no gate and no ledger | **Open** (DESKTOP task queued); renderer Live path **deleted** |

Medium: 9 findings (section 3). Low: 8 (section 4). What is sound: section 6. What I could not check: section 7.

Answer to the lead's question: **a mock-mode demo path is not a gap for "every call is listed"**, provided the Privacy screen says "mock mode: no call left this machine" in that mode. In mock mode `egress._resolve_port` accepts only offline ports and the Python providers are never built; I verified that `get_model_port(mock=True)` returns the unwrapped mock and that the guard refuses a non-offline port in mock mode. The gap would be a process with `UNDERSTUDY_MOCK=1` that still reaches a network through code that does not read that variable (the TypeScript main process reads `ALONGSIDE_MOCK`/`UNDERSTUDY_MOCK` separately: not exercised by me).

## 2. High findings

### H1 Voice sent free text to a third party (fixed)
- Was: `voice/router.py:21` and `voice/tts.py:189`: `POST /voice/speak {text}` up to 4000 chars to `api.elevenlabs.io`, only a PII regex in front (a person name passes), no purpose, no ledger row, even with `UNDERSTUDY_X=1`.
- Fix landed (LIVE agent): `{line_id, slots}` only; slots are bounded ints or enum ids rendered by code (`voice/lines.py`); free text is 422 unless `UNDERSTUDY_VOICE_DEBUG_TEXT=1`; every real call writes a metadata-only row (`kind: direct`, chars bucket, no text); an unwritable ledger blocks the send.
- My attacks (15 variants, all refused or rendered from fixed sentences): name in an enum slot, newline suffix, Cyrillic homoglyph, extra slot, list value, 10**4000 int, float, bool, digit string, `coach.nice_work\n`, `whisper.<invented step id>`, `whisper.read_case\n`, `question.<name>`.
- Residual (Medium, accepted risk): `UNDERSTUDY_VOICE_DEBUG_TEXT=1` restores free text to the third party (it is ledgered). `whisper.<step_id>` speaks the pack's label text; `cue/vocab.py` lets a pack's `pack.yaml` `short_labels` override the built-in labels with only a length check, no PII scan, so a pack file is a free-text channel to the voice service. Fix: scan pack labels with the backstop when loaded.
- Reproducer: `evals/review/privacy/test_p1b_voice_and_default_ledger.py` (22 pass).

### H2 Default ledger coverage (fixed)
- Was: `models/factory.py:34` wrapped the port in `LedgeredPort` only when the privacy flag was on; every flag is off by default, so raw planner and reader calls left with no ledger row.
- Fix landed (MODELS): always wrapped except mock; `ledgered=False` and calls from inside the egress module stay raw.
- Re-run in a **non-mock configuration with a fake provider** (UNDERSTUDY_MOCK unset, all extension flags unset, `OpenAIProvider` replaced by a stub that records calls; no key, no network): 5 methods (`plan`, `read`, `check`, `vision`, `computer_step`) wrote 5 rows, each `payload: null`, `content_logged: false`; the canary text, a PNG header and screenshot bytes are not in the ledger; with the ledger path made unwritable the stub received 0 calls (fail closed).
- Residual: `get_model_port(ledgered=False)` returns the raw provider to any caller. A static check finds no production module outside `privacy/` and `models/` using it or `_get_raw_port` today. `security/redteam_live.py:521` builds `OpenAIProvider` directly (sandbox pages only) and `evals/modelbench/contenders.py:61,65` build providers directly (bake-off on sandbox screenshots): expected, but outside the ledger by construction.

### H3 Origin prefix check and unguarded writes (engine fixed, agent open)
- Was: eight routers tested `origin.startswith(("http://localhost", "http://127.0.0.1", ...))` (`routes_privacy.py:39/81`, `routes_localmodel.py:28/75`, `routes_proactive.py:41/76`, `routes_coach.py:77/92`, `routes_handoff.py:53/93/498`, `awareness/routes.py:29/56`, `runtime/routes.py:32/54`). `http://127.0.0.1.evil.example` and `http://localhost.evil.example` passed. A missing `x-understudy-actor` header counted as `worker`. A cross-site `text/plain` POST needs no preflight. Reproduced: `/privacy/ledger/clear` returned 200; `/agents/spawn` (reads `request.json()` whatever the content type) returned a `run_id` and honoured `params.raw_ok`. `POST /queue/{id}/approve|reject` (`routes_data.py:225,230`) had no check and records `origin=HUMAN_UI, decided_by="worker"`.
- Fix landed (ENGINE-DATA): shared `http_guard` (exact scheme/host/port, JSON content type, explicit actor header, per-boot token; the dashboard proxy adds the token server side). Verified: ledger clear 403 for all three prefix origins, queue approve 403 for a foreign Origin, `/agents/spawn` 403 for `Origin: http://localhost.evil.example` with `text/plain`.
- **Still open:** the agent service routes (:7710) answer a foreign `Origin`/`Host` (see H4).

### H4 Kill switch and DNS rebinding (engine fixed, agent open)
- Was: `POST /kill` and `POST /kill/clear` on the engine (`routes_data.py:255,262`) and agent (`server.py:411,420`) accepted a foreign Origin with `text/plain` (200, `killed:false` after clear); `POST /events` and `POST /human-input` too. No route checked `Host`: `GET` with `Host: evil.example` returned 200 for `/events`, `/audit`, `/queue?status=all`, `/privacy/ledger(/export)`, `/memory`, `/eval/report` (engine) and `/health`, `/offhours/report`, `/voice/status`, `/agents/runs` (agent). Pydantic-bodied routes were only protected by FastAPI 0.162's strict JSON content type, which a rebound same-origin page bypasses.
- State: engine now returns 421 `host_refused` for every probed GET and 403 for a foreign-origin kill clear and `/events`. **Open on the agent service:** `POST /kill/clear` with `Origin: http://evil.example` still returns 200; every agent GET answers `Host: evil.example`. Owner: AGENT-CORE (guard pending).
- Smallest fix for the agent: mount the same `http_guard` (Host allow-list, exact Origin, JSON content type plus the token header on every non-GET, never default the actor to `worker`). Allowing `POST /kill` (set) without the token is a reasonable choice (stop should be easy); `kill/clear` must need it.
- Reproducers: `test_p3_origin_prefix_csrf.py` (6 pass), `test_p3b_kill_switch_and_dns_rebinding.py` (4 pass, **2 fail = agent still open**).

### H5 Live study could be fed from simulation (fixed)
- Was: `eval/adapters.py:642-660` checked origin only for `summary.json`; `participants.csv` had no provenance check and the default meta origin was `real`. `evals/study_sim/results/participants.csv` has the same schema (ids `p_sim01`). Copying it into `evals/study/results/` made `adapters.study()` return origin `real`, n=3, simulated rows as participants.
- Fix landed: the section is `not_run` unless `evals/study/results/` carries a human-study manifest (origin human, consent ref, collected-by, n, dates). Verified with the same copy. Residual: the manifest is a file anyone can write; it stops accident, not a motivated author. Also make `evals/study_sim` refuse to write under `evals/study/`.
- Reproducer: `test_p5_study_provenance.py` (1 pass in regression form).

### H6 TypeScript main process: provider calls outside the guard (open)
- `main/model-port/openai.ts:53,169` sends full screenshots as `input_image` data URLs over `fetch` to OpenAI; used by `model-services/{grounder,verifier,scam-analyst,lesson-architect}.ts` and `agency/` (coach, act-for-me). `main/gemini/client.ts:89` and `main/files/{embed,extract}.ts:153` send file text and images to Gemini. `renderer/wake/engine-gemini.ts:39` streams microphone audio to Gemini (flagged off). None references the ledger, the `ImageGate`, a denylist or secure input (grep: only `awareness/*`, `live/ledger.ts` and now `live-auth.ts` mention a ledger). The old renderer Live path (`renderer/live/LiveSession.ts:499`, 1 fps frames behind `UNDERSTUDY_FLAG_VOICE`) has been **deleted**. The new `main/live/egress.ts` is the right shape (one send site, ledger row before frames, kill switch, JPEG buffers zeroed).
- Impact: "image egress only through the privacy spine" (REQ5 section 3, `CLAUDE.md:29`) is false for the legacy desktop vision and file paths today. `docs/FEATURE_CATALOGUE.md` already says so.
- Residual in the new Live code: microphone audio is gated but not ledgered per chunk (the meter counts seconds); frames are announced as batches. I recommend one ledger row per N seconds of audio, metadata only.
- Fix: route vision through the engine's `send_image` (the glance route already does), or POST a metadata row and honour `allowed:false` before every fetch; gate `gemini/client.ts` and `files/*` behind consent and the ledger.
- Reproducer: `test_p1c_ts_provider_inventory.py` (2 pass: renderer Live gone; the TS OpenAI port still has no ledger reference; it fails when DESKTOP's gating lands).

## 3. Medium findings

| # | Finding | Where | State |
|---|---|---|---|
| M1 | Static guard evasions (20 snippets: `from urllib import request`, `import urllib` + `urllib.request`, `asyncio.open_connection`, `/usr/bin/curl`, string-built `curl`, `logging.handlers.HTTPHandler`, `webbrowser`, `ctypes`, `exec` of a string, `x.plan` on a variable not named like a port, `git push` via subprocess, `python -c` child) were all silent, and agent modules `handoff_io.py`, `server.py`, `voice/tts.py`, `sandbox_*` were under no network scan (`privacy/guard.py` walked only engine dirs) | `privacy/guard.py` | **Fixed** (netscan.py; all 20 flagged, agent package scanned). A static, name-based scan remains a net for honest mistakes, as its docstring says |
| M2 | Raw runtime path: with `raw_ok` (an HTTP body parameter) in foreground mode on a named file, up to 12,000 chars of file text (header and cells) reach the provider; the ledger row holds bytes only. Menu mode sends none (verified) | `runtime/run.py:254`, `runtime/child.py:342,361`, `runtime/routes.py:155` | **Accepted risk** (documented, worker-requested); the CSRF fix removes the web-page route to it. Make `raw_ok` a worker setting, not a request field |
| M3 | Image gate inputs are caller assertions: consent, denylisted app, secure input, unattended and the `sandbox` source are booleans/strings the caller computes; a local process can claim `sandbox` (no consent needed, may run unattended) or `consent:true`. The static "sandbox literal" scan is evaded by a non-literal | `privacy/image.py:263-278`, `guard.py` `scan_sandbox_claims`, `awareness/glance_service.py:100` | **Accepted risk** (documented); the ledger `source` column is the audit. Add an Electron-held secret to the glance route |
| M4 | Page screenshots of agent runs are written to disk (`data/runs/<id>/s1..s4.png`) and served at `/runs/{id}/{file}`; `CLAUDE.md:29` says a frame is never written to disk. Sandbox pages by default; a run on a real site stores that site's page | `orchestrator.py:549`, `queue.py:123`, `routes_data.py:269` | **Open (policy)**: state the exception in `CLAUDE.md`, or store only for sandbox hosts, and add retention |
| M5 | Leak-rate interval treats correlated tokens as independent: "0 of 11,336 tokens, upper bound 0.03%" (`report.md:420`). A leak is a property of a code path, not of a token; the honest unit is the run (0 of 80: 3.7%) or the flow (0 of 10: 25.9%). The new run: 4,296 tokens, bound 0.07% in fast mode | `privacy/evaluate.py:897,911` | **Open** |
| M6 | The report showed a failing check as `ok`: the 17:38 `report.md:431` says "Static guard: 27 violations in 172 files" inside a section with status ok. Current code gives 0; the report in the tree is stale | `eval/adapters.py` privacy section, `render_md.py` | **Open**: make violations > 0 fail the section; regenerate before submission |
| M7 | Draft claims stronger than the report: `docs/drafts/DEVPOST.md:20` "Agent runs on sandbox calculators: 40 of 40 pass, no false success claims (mock model)". `report.md:297` says the clean mock path "says little"; the real-model rows (glitch page: 0 of 20 passed, 20 false claims, fix in-sample on 10) are omitted | `docs/drafts/DEVPOST.md`, `DEV_POST.md` | **Open** |
| M8 | Microphone audio to Gemini Live is not ledgered per chunk (see H6) | `main/live/egress.ts` `audio()` | **Open** (design choice) |
| M9 | Agent-run evidence and `data/` growth: no retention for `data/runs`, `data/voice_cache` (spoken sentences as audio) | `queue.py`, `voice/tts.py` | **Open** |

## 4. Low findings

- L1 Hand-typed stale numbers in `docs/FEATURE_CATALOGUE.md`: line 44 "37 attacks, 31 clean" (report: 42 attacks, 31 clean pages); line 62 "18 sections, 72 limitations" (report: 32 sections, 108 limitations). Catalogue numbers are typed; the report is generated.
- L2 `report.md:331,733`: "about None USD" (a formatter bug).
- L3 ext server (`dom-ground/ext-server.ts`) accepts any `chrome-extension://` id (not pinned) and the ring routes need no secret from a local process. Host, Origin and body limits are otherwise correct (my test passes).
- L4 `ALONGSIDE_DEBUG=1` debug server (`debug-server.ts:106`) serves `GET /shot` (real screen) without the gate; opt-in, Host and Origin checked.
- L5 Replay recorder (`dev/replay/index.ts`): off by default, env only (cannot be set by a page or setting). In record mode it writes `<userData>/replay/*.json` indefinitely with a 200-char `preview` of request strings and the full response bodies (extracted file text and screen-read text). No frames, no audio. 32 recordings from 31 Oct exist in `apps/desktop/.userdata-replay` (git-ignored).
- L6 Redactor (`models/redact.py:19-24`) misses `auth_tokens/<id>` (the Live ephemeral token name), `ghp_` tokens and ElevenLabs `sk_` keys unless the exact value is in the environment. Keys otherwise travel in the `x-goog-api-key` header only.
- L7 Tracked docs contain the owner's home path (`docs/DECISIONS.md:24`, `apps/desktop/docs/*`, `evals/realism/measure_v1.py:6`).
- L8 `verify.agent_run` (image verifier) is registered but not wired to any decision. When wired, it may only add a veto; a screen can say "answer yes".

## 5. Reproducers and state

All under `evals/review/privacy/`. Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider evals/review/privacy -q`; the TypeScript one needs vitest from `apps/desktop`: `ln -s ../../../apps/desktop/node_modules evals/review/privacy/node_modules && (cd evals/review/privacy && ../../../apps/desktop/node_modules/.bin/vitest run --root . ext_server.review.test.ts)` then remove the symlink. They are in **regression form**: a failing test means the thing is open. Final run: 88 Python tests (86 pass, 2 fail) and 7 vitest tests pass; no tripwire fired; `data/KILL` absent.

| File | What it proves | Result | State |
|---|---|---|---|
| `test_p1_guard_bypass.py` (28) | 20 evasions and 6 agent-side snippets are flagged; every agent module with a network import is scanned | 28 pass | fixed |
| `test_p1b_voice_and_default_ledger.py` (22) | free text refused; 15 registry attacks; one metadata-only row; unwritable ledger blocks; debug flag residual; non-mock port ledgered (5 rows, fail closed); mock unwrapped; no module uses `ledgered=False` | 22 pass | fixed (residuals: debug flag, pack labels) |
| `test_p1c_ts_provider_inventory.py` (2) | renderer Live gone; TS OpenAI port has no ledger reference | 2 pass | **open** (H6) |
| `test_p2_canary_all_sinks.py` (21) | 7 integration flows x 2 seeds + failing-port exceptions: return values, every file under data/HOME/TMPDIR, stdout, stderr, DEBUG logs with tracebacks | 21 pass, 0 survivors | sound |
| `test_p2b_runtime_canary.py` (2) | menu mode sends no file text; raw mode sends header and cells by design, ledger metadata only | 2 pass | accepted risk (M2) |
| `test_p3_origin_prefix_csrf.py` (6) | prefix origins and queue approve refused; spawn refused | 6 pass | fixed (engine; spawn route is the agent runtime router, in-process) |
| `test_p3b_kill_switch_and_dns_rebinding.py` (6) | engine: kill clear, events, foreign Host, rebound page refused. agent: kill clear, foreign Host | 4 pass, **2 fail** | engine fixed, **agent open** (H4) |
| `test_p5_study_provenance.py` (1) | simulated CSV in the live folder is refused | 1 pass | fixed |
| `ext_server.review.test.ts` (7) | web-page Origin, prefix origin, foreign Host, ring with Origin refused; extension id not pinned (known gap) | 7 pass | accepted risk (L3) |

## 6. Checked and found sound

- **Egress core.** `egress.send` and `send_image` order (purpose, validate, bucket, backstop, port, ledger row, call, answer schema, answer scan), fail closed on an unwritable ledger, messages never contain payload values, `SafeImage` (size, header match, wiped, no repr, no pickle), the closed image schemas (`closed_schema_problem` on all 5 registered image purposes: no problem). No text purpose uses a pattern vocabulary (`hashed_id` is the only one); text purposes' free response strings are `text` (280 chars, model to worker, shown only; the voice now speaks by line id, so no response feeds a prompt or the speech service).
- **Canaries.** Own all-sinks harness over the 7 integration flows: 0 survivors in returns, files (1,892 synthetic-cohort files and the ledger), stdout, stderr, logs, tracebacks. The privacy evaluation re-run (`python -m understudy_engine.privacy --seeds 8`, mock): leaked 0 of 11,456, ledger complete, 11 of 11 negative controls, bucketing 0 failures over 594,114 cases, static guard 0 violations over 177 files, image gate blocks 8 of each reason; it reports `gaps: ["agent_runtime"]` (my P2b is the first runtime canary).
- **Keys.** No key-shaped string in any tracked file or in any of the 15 commits (`git grep` over all revisions: the only matches are fake test values `sk-test-...`, `AIzaSyFAKE...`, `AKIAABCDEFGH...`); `.env` never added (`.env.example` only, placeholders); working tree and `data/` scan (4.4 GB; files over 60 MB skipped) found no key shapes outside tests. Gemini key header only; `run_python` sandbox clears the environment and denies network (`sandbox-exec`); `data/` and `.env*` are git-ignored; the Live token is minted in main with `uses: 1`, 10 minutes and a model-bound setup (`main/live/token.ts`).
- **Browser extension server and dashboard proxy**: Host and Origin handling correct (ext server); the dashboard proxy adds the per-boot token only after Host, Origin and `Sec-Fetch-Site` checks.
- **Steering.** The local-model report is right that digests are steerable (`localmodel/evaluate.py:561`). Downstream code uses digest values only as counts and shares that select from a fixed template table; card risk class and draft text come from code tables (`proactive/candidates.py:295+`); every card needs a press; at most 3 cards. A steered digest can add or hide an advice card; it cannot start work or change a risk class.
- **Honesty.** Report badges, n, split and intervals are present in every section I read; weak and circular results are published (routing circular, hazard false alarms overshoot, skill tracing saturates). The in-sample re-run of the glitch condition is labelled in-sample. Draft numbers that I compared match the report (precision 92%, recall 95%, 229.6 s vs 7.1 s, 0.436 vs 0.509, 1.83 to 0.05 false nudges per hour, 0 of 42 attacks, 116 of 116). Re-running `python -m understudy_engine.eval --fast` offline into a scratch folder reproduces every section's shape; numbers differ only where the fast mode uses fewer resamples or seeds (deficit recovery bootstrap 300 vs 2000; privacy 3 vs 8 seeds) and where code changed since 17:38 (study, evidence, privacy sections).

## 7. Could not check

- Real provider behaviour (no network or model call was made); the real glance, Live and grounding paths end to end; anything needing screen capture, macOS Accessibility or a real click (not run by instruction). The TS awareness gates (denylist, secure input, strict mode) were read, not exercised.
- `main/live/*` and `cue/*` were still being written; I read `live/egress.ts` and `live/token.ts` only. Re-check after they land.
- Content of the 270 tracked screenshots (`apps/desktop/docs`, `apps/dashboard/qa`, `evals/study_roles/screens`): checked by name only, not viewed.
- The browser extension's field handling beyond grep (`content/capture.ts:174` reads `field.value`; I did not trace what is kept), the Auth0 flow, the Graph plugins (tested only against recorded responses by their authors).
- The values in `.env`; whether any key was ever pasted somewhere untracked (home directory, shell history, other repos).
- The numbers behind the model bake-off, Cue and the role studies (not landed at review time: report sections pending).

## 8. Addendum (about 18:00): second round against the hardened guard (M1 reopened as Low-Medium)

PRIVACY's netscan hardening passes my first 28 cases. I wrote 21 more, parse-only (`test_p1d_guard_round2.py`, asserts the guard is SILENT, so a pass means a gap is open). In an extension layer (`calendar/x.py`) **17 of 20 evasions are still silent** and 4 are flagged (dropbox, redis, slack_sdk, `shutil.which('c'+'url')`):
- third-party network or telemetry clients not on the list: `dns.resolver` (dnspython), `google.cloud.storage`, `paho.mqtt`, `posthog`, `sentry_sdk` (ships locals), `selenium`, `playwright` (goto with data in the URL);
- processes: `node -e` and `perl -e` network code (only python and sh `-c` code is parsed), `/usr/sbin/sendmail`, `python -m pip download -i <url>`, `git clone <variable>`;
- model calls hidden from name matching: `operator.attrgetter('plan')(port)`, `functools.partial(port.plan, ...)`, `vars(type(port))['plan']`;
- a write into an iCloud Drive or other synced folder (not network code at all; out of reach for any import scan).

Smallest fix, one change closes the first group and most future ones: in the guarded layers replace the import BLOCKLIST with an ALLOWLIST (stdlib, `understudy_*`, and a short named list of pure-compute dependencies such as pydantic, numpy, pandas, scipy, jsonschema, yaml); any other import is a violation needing a reviewed `ALLOW` entry. For processes, ban `subprocess` in the layers except reviewed entries whose argv[0] and subcommand are constants (the git source: `git log` only). For model calls, flag a bare reference to `.plan`/`.check`/`.read`/`.vision`/`.computer_step` as an attribute (not only a call) on any receiver. Playwright and selenium should be banned outright in the extension layers (the browsing carve-out in D12 belongs to the agent package, not to calendar, git, proactive, localmodel, plugins or awareness). The synced-folder write needs a different control (the layers' write paths pinned to the data dir).

Same limits as before: this remains a static net for honest mistakes, not a defence against a determined author; the runtime defences (`egress.send` as the only builder of a request, the ledger) are what matter.
