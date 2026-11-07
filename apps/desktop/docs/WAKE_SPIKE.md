# WAKE: voice activation spike, decision, and stage-day checklist

Owner: WAKE. Code: `src/renderer/wake/**`, `src/main/hotkey.ts`, `spikes/wake/**`, `tests/wake/**`. Date of measurements: 31 Oct 2026, macOS (Darwin 25.2), Electron 45.2.1, `@google/genai` 2.32.0, `gemini-3.5-transcribe-live`. Everything below was measured with synthetic speech (macOS `say`, 18 voices / 6 English accents). **No real human voice in a real room has been tested**; see "Unverified".

## Decision

| Path | Verdict |
|---|---|
| **A. Web Speech API in Electron** | **Dead.** Do not ship. |
| **B. `gemini-3.5-transcribe-live` streaming keyword spotter** | **PRIMARY** voice activation. Works end to end through the production ephemeral-token path. |
| **C. Global hotkey + on-screen button** | **Always on, stage-safe path.** Needs no mic, no network, no permission. Use this on stage unless the wake word has passed the room rehearsal. |

The wake word is best-effort; the hotkey/button is the guarantee.

## A. Web Speech in Electron (20-minute spike, spike A)

`spikes/wake/webspeech-main.cjs` + `webspeech.html`, hidden window, isolated profile, fake media device (`--use-fake-device-for-media-stream`, with and without `--use-file-for-fake-audio-capture=<say wav>`).

- `webkitSpeechRecognition` and `SpeechRecognition` both exist in Electron 45 / Chrome 156.
- `start()` returns and the `start` event fires, but **`audiostart`, `result`, `error` and `end` never fire** in 15 s, with either fake audio source. It fails silently: there is no error to catch, which is worse than an explicit `network` error. Electron ships no Google speech API key, so Chromium's cloud recogniser never connects.
- Conclusion: it cannot be detected as "working" except by a timeout, and it never returned a result. Not used.

## B. `gemini-3.5-transcribe-live` keyword spotter (spike B)

API facts verified against the live service (docs: `aistudio.google.com/docs/live-api/live-transcribe.md`):

- Config: `responseModalities: [TEXT]`, `inputAudioTranscription: { languageCodes, customVocabulary, mode }`. Audio in: PCM16 mono 16 kHz, `audio/pcm;rate=16000`, 100 ms chunks.
- Transcripts: `serverContent.interimInputTranscription.text` (speculative, arrives while the user is speaking) and `serverContent.inputTranscription.text` (final). Also `voiceActivity` events (`ACTIVITY_START` / `ACTIVITY_END`).
- WebSocket setup (connect to `onopen`): p50 38 ms, max 416 ms over 108 connections, so reconnecting is cheap.

### Latency (phrase end to first transcript containing the name)

Real-time paced streaming of 100 ms chunks; 36 "Hey <name>" clips across 18 voices (27 returned an interim containing the name; the rest are the synthetic-clip artefact described below).

| Measure | min | p50 | p90 | max |
|---|---|---|---|---|
| First **interim** containing the name, vs end of speech | -144 ms | **364 ms** | 522 ms | 803 ms |
| **Final** transcript vs end of speech | | 1105 ms | | 1730 ms |

Through the full spotter (`tests/wake/live-e2e.test.ts`: real spotter, production `mintWakeToken` ephemeral token, 1 s of room tone, the clip, then continuous quiet noise), `onWake` fired after the end of speech at **512, 583, 633, 697 ms** for bare "Hey <name>" on four voices and at **1726 ms** on the one voice the recogniser handles worst (Flo). For "Hey <name>, <request>" it fired **476 and 813 ms before the end of the sentence**, because the name is recognised while the user is still speaking the request. Expect roughly **0.5 to 0.7 s after the name** in the normal case and occasional outliers of 1.5 s or more; an earlier run of the same voices showed a 1.4 s and a 3.0 s outlier. The matcher fires on **interim** text; finals take about 1.1 s and are sometimes slow or absent for a short utterance.

### Findings that shaped the implementation

1. **Language hints matter.** With auto-detect, Flo's "Hey Amelia" came back as `miúdo` and Fred's "Hey Marcus" as `Hey Maracas`. `languageCodes: ['en-GB','en-US']` plus `customVocabulary: [<persona names>]` fixed both (A/B on the 14 hardest clips: name heard exactly 7/14 baseline, 8/14 language only, 9/14 vocabulary only; the remaining misses were clips with no transcript at all). Both are on by default in `engine-gemini.ts`. Names for the vocabulary come from `wakePhrases`, never hard-coded.
2. **Synthetic clips that start at speech onset can return nothing.** 11 of the 72 wake clips (4 of 18 voices: Eddy UK, Reed US, Sandy UK, Grandma US) came back with no transcript at all in the bulk run, where the audio began at byte 0 of the stream and 6 sessions ran in parallel. Re-running with 1 s of room tone in front recovered 3 of 5 retested clips; Sandy (UK) stayed empty (a voice quirk). A live microphone always has a lead-in and the spotter streams continuously, so this is a test artefact; the e2e test therefore prepends room tone. It does mean the 36-clip latency sample above covers only the voices that returned text.
3. **The recogniser sometimes drops or mangles "hey".** Real transcripts included `Amelia.` alone, `Emilia`, and on the hardest voice (Flo, en_US) `Amelia` repeated for 9 s as an interim that never finalised, or `유미야` / `É o meu` (Korean/Portuguese hallucinations; about 50% of runs before the fixes). Three defences: language hints + vocabulary (finding 1); the matcher accepts a bare name on a **final** transcript that is exactly the name or opens with it plus a comma (see "Matcher"); and the spotter treats an interim that has stood **unchanged for 1.2 s** as final (the server repeats an unchanged interim about every 0.5 s), so a stuck bare `Amelia.` still wakes while "Marcus Aurelius was..." (text keeps changing) never does. After these changes the Flo clip woke in the one full e2e run made afterwards (at 1.7 s); that is a single sample, not a measured rate. Real voices will be different, which is why the hotkey is the stage path.
4. Mock mode: `getToken()` returns `{token:'mock'}` and the engine goes ready but never transcribes, so `ALONGSIDE_MOCK=1` runs without cloud audio. Use the hotkey or debug `POST /wake` instead.

### 10-minute connection cap and reconnect

The docs state continuous streaming is limited to 10 minutes per session. The spotter:

- proactively opens a **new** stream at `maxSessionMs` (9 min, waits for a 2 s quiet gap so it never swaps mid-utterance), switches audio to it, then closes the old one, so there is no deaf gap;
- handles the server's `goAway` message by rotating immediately;
- on an unexpected close or error reconnects with exponential backoff (0.5, 1, 2, 4, 8 s) up to 6 consecutive failures, then reports `state:'unavailable'` with a message pointing at the button/shortcut (microphone permission denied is `unavailable` immediately);
- mints a new ephemeral token for every connection (main's `mintWakeToken` is `uses:1`).

Unit tests cover rotation, no mid-utterance rotation, backoff, give-up, and permission denial (`tests/wake/spotter.test.ts`, fake timers). `tests/wake/live-long.test.ts` (`WAKE_LIVE_LONG=1`, about 12 minutes) plays "Hey Amelia" at 30 s, 530 s, 575 s and 700 s against the real service and asserts all four wake and that a rotation token mint happened near 540 s. Result: see "Verification log" at the end.

### Cost

From `aistudio.google.com/docs/pricing.md`: audio in $3.50 per 1M tokens (about $0.005/min at 25 tokens/s), text out $21.00 per 1M (about $0.004/min), "blended about $0.009 per min". Streaming continuously while listening is therefore **at most about $0.54 per hour** (input about $0.30/h; output only while speech is transcribed). Free tier exists, but free-tier content is used to improve Google's products, so do not use a free-tier key with real user audio. The spotter streams nothing while paused, muted, disabled, push-to-talk-only, or while a Live session owns the mic.

### Privacy truth (surface this in the UI and to judges)

While the status is `listening`, **microphone audio is streamed to Google (Gemini Live Transcribe) to hear the name**. It is not processed on the device. `WakeStatus.cloud` is always `true` and is there so the dock can say so next to the listening light. Controls that stop the stream: the mute button (`micMuted`), the settings toggle `wakeEnabled`, `pushToTalkOnly`, any Live session (the spotter pauses and releases the mic), and TTS pauses. A production version would use an on-device keyword spotter (for example openWakeWord) so no ambient audio leaves the machine; that is the honest "next step" answer to the privacy question.

## C. Global hotkeys (spike C)

`src/main/hotkey.ts` uses Electron `globalShortcut` (no Accessibility or Input Monitoring prompt is expected for this API; not verified on a fresh machine). Probe on this Mac (`spikes/wake/hotkey-probe.cjs`, run under `scripts/electron-lock.sh WAKE`): all 7 candidates it tried registered successfully (the shipped set is the subset below plus the Shift variants).

| Action | Accelerators (all registered, first is primary) |
|---|---|
| Start session with the last/default persona | `CommandOrControl+Alt+Space`, `CommandOrControl+Alt+Shift+Space`, `CommandOrControl+Alt+Shift+S` |
| Stop (closes Live in the dock and ends the session) | `CommandOrControl+Alt+M`, `CommandOrControl+Alt+Shift+X` |

Behaviour: Start emits `session:request{personaId, source:'hotkey'}` using `settings.persona ?? DEFAULT_PERSONA`, and is **ignored while a session is already running** (no accidental restart). Stop calls `session.stop('stop')`, which tells the dock to close Live and emits `session:ended`. Registration failures are tolerated (each action has fallbacks); if no Start or no Stop combo can be registered, `state.lastError` carries a plain-language message. Combos are unregistered on quit. `tests/wake/hotkey.test.ts` covers all of this, including Start then Stop against the real `registerSession`. Cmd+Alt+Space may be claimed by macOS (Finder search window); `register()` returned true here but a real key press has **not** been tried by an agent, so the stage-day checklist includes pressing them, and each action has fallbacks. `Cmd+Alt+Esc` (Force Quit) and `Ctrl+Alt+Space` (input-source switch) are deliberately left alone so the presenter keeps their escape hatches.

## Alias harvest and the realism problem

Names were run through the real recogniser in 18 `say` voices (en_GB, en_US, en_AU, en_IE, en_IN x3, en_ZA, plus novelty/low-fi voices) as "Hey Marcus", "Hey Amelia", and each with a request after it; 12 non-wake sentences ran through 3 voices. Raw data: `spikes/wake/results/harvest.json` (gitignored audio at `spikes/wake/audio/`, regenerate with `node spikes/wake/gen-audio.mjs`; summary with `node spikes/wake/analyze.mjs`). Real transcripts are frozen in `tests/wake/fixtures/asr-transcripts.json`.

What the recogniser actually returned for the name part (auto-detect, no hints):

| Said | Heard (count) |
|---|---|
| Hey Marcus | Marcus (26), Maracas (2), Maritas, Marcos, "Chay Marcus", "Hema kas" / "Hema, ..." (4), "去 Marcos" |
| Hey Amelia | Amelia (21), Emilia (3), "Hear me", miúdo, "1000" |

Takeaways: (1) most mishearings land in the existing `wakeAliases` (`marcos`, `emilia`) or are caught by the phonetic route (`maracas`); (2) the dangerous ones are where the *name itself* is mangled (`Hema`, `Maritas`, `Hear me`, `miúdo`); the matcher deliberately does not rescue those, and language hints plus vocabulary remove the `Maracas`/`miúdo` class; (3) **synthetic voices are cleaner than real people**; real accents, mumbling, and room noise will produce a longer tail, which is why the room test below is mandatory and why the persona names should be tested before they are committed to.

Persona names stay placeholders. To add the real aliases once the user renames the personas: edit **only** `src/shared/personas.ts`, run the rename checklist below.

## The matcher (`src/renderer/wake/matcher.ts`)

Pure, DOM-free, driven only by each persona's `wakePhrases` and `wakeAliases`.

1. Normalise (lower case, strip punctuation/apostrophes/diacritics). Tokenise, remembering where the original text had a comma/stop.
2. Split every phrase/alias into optional prefix words (`hey, hay, hi, ok, okay, hello`) and a core name. Multi-word cores work; a multi-word alias with no prefix (`"a marcus"`) only fires at the start of the utterance.
3. A candidate needs a prefix word immediately before it. Score = `max(spelling similarity, phonetic similarity - 0.05)` where spelling is optimal-string-alignment (edit distance with transpositions) over the longer length, and the phonetic key is a consonant skeleton (so Marcus, Marcos, Markus, Marquis, Maracas collapse together; Amelia and Emilia collapse together). The phonetic route requires the same first sound and a spelling similarity of at least 0.5.
4. Words are also tried glued across 1-2 tokens ("mark us" as `markus`), but never across a comma ("Hey Mark, us two...").
5. Fires when the score is at least `threshold` (default 0.8). An exact configured phrase/alias scores 1.0.
6. `rejectWords` (real words that sound like a name: mark, marks, market, america, emily, camellia...) are never accepted fuzzily. This is data, not logic.
7. If two personas both match, the best must beat the runner-up by `ambiguityMargin` (0.06) or **nothing fires** (the other persona's name never triggers this one; close names must be disambiguated or use the hotkey).
8. `bareNameOnFinal` (default on): a **final** transcript that is exactly a name, or opens with it plus a comma ("Amelia, how do I join..."), also fires. Interim text never does, so "Marcus Aurelius was..." cannot trigger on its first word.
9. `trailing` returns what was said after the name in the same breath.

### Trade-offs and tuning

| Knob | Effect |
|---|---|
| `threshold` up (0.9 to 0.99) | Fewer false triggers, more misses. 0.99 means exact names/aliases only. Tests pin both ends. |
| `threshold` down (0.6) | Catches `marlus`-style slips; admits near-words. Not recommended on stage. |
| `bareNameOnFinal: false` | Needs the literal "hey"; recovers nothing when ASR drops it. |
| More aliases in `personas.ts` | Zero-risk recall (exact), but each alias is trusted completely, so do not add real words. |
| Short names (up to 4 letters) | One edit is already below 0.8, so effectively exact-only. Safe but unforgiving. |

### False-trigger analysis

- **Real recogniser output:** `tests/wake/matcher.test.ts` replays every interim and final transcript from the harvest (97 clips with text) in arrival order. **0 wrong-persona fires, 0 fires on any non-wake sentence** (Hey Google, Hey Alexa, "Marcus Aurelius was...", "I spoke to my friend Amelia", Hey Mark, Hey America, Hey Emily, Hey Marsha/Marcia, the market, the camellia bush, "video call grandma and make the text bigger"). Wake recall over clips where the recogniser returned anything is above the 90% asserted in the test (misses are the mangled-name cases above).
- **Through the live spotter:** 10 non-wake clips, each listened to for 10 s with continuous noise: **0 wakes**.
- **Dictionary sweep** (`WAKE_COLLISIONS=1 npx vitest run tests/wake/collisions.test.ts`, scans `/usr/share/dict/words` as "hey <word>"): 42 obscure words fire (`marquis`, `marco`, `marquess`, `mancus`, `embelia`, `hamelia`, `emil`, `amyl`...). None is a common word; the test asserts none of about 100 very common words fires. The residual risk is a stranger in the room saying "Hey Marco" / "Hey Emil" (a plain first name that is one edit from a persona), which will wake the assistant; the session idles out after 20 s and the privacy light is visible.
- **Residual real-world risks the tests cannot cover:** people in the room named like a persona; the persona's own TTS saying its name (mitigated: the spotter pauses while a Live session exists, `pause('tts')` exists for other TTS, and the system prompt must say "never say your own name except in the greeting"); TV/video call audio from the demo itself saying the name.

### Renaming a persona (checklist)

1. Edit `src/shared/personas.ts`: `wakePhrases` (the `hey <name>` forms) and `wakeAliases` (mishearings). Nothing else changes; the matcher, the recogniser vocabulary and the tests read these fields.
2. Edit the `POS`/`NEG` arrays in `spikes/wake/gen-audio.mjs` to the new names, then `node spikes/wake/gen-audio.mjs && node spikes/wake/harvest.mjs --conc=4` and `node spikes/wake/analyze.mjs`. Copy every mishearing that is a plausible address to the name (not a real word) into `wakeAliases`.
3. `WAKE_COLLISIONS=1 npx vitest run tests/wake/collisions.test.ts`: read the list; add real, common words that sound like the name to `rejectWords` (the matcher option, passed from the dock).
4. `npx vitest run tests/wake`, then `WAKE_LIVE=1 npx vitest run tests/wake/live-e2e.test.ts` (edit the clip names in that file).
5. Say each new name three times in the room before the demo.

Names that ASR finds hard are the main risk; prefer two or three syllables, a hard consonant start, and not a common word or a near-neighbour of the other persona's name.

## Architecture and the mic-arbitration contract

```
mic -> AudioSource (16 kHz PCM16, 100 ms frames) -> PrerollBuffer (3 s ring)
                                   \-> Engine (transcribe-live WebSocket) -> interim/final text -> Matcher -> onWake
```

- `createWakeSpotter({ personas, getToken, onWake, onStatus, settings })` returns `{ start, stop, pause(reason), resume(reason), dispose, takePreroll, setSettings, setPersonas, getStatus }`. Import from `src/renderer/wake/index.ts`. Pass `PERSONA_LIST`; only `id`, `wakePhrases`, `wakeAliases` are read.
- `onWake` is called with `{ personaId, source:'wake', score, heard, trailing, atMs }`. The dock reports it with `window.alongside.wakeDetected({ personaId, source:'wake' })`.
- **Single mic owner:** after a wake the spotter immediately stops streaming to the cloud, keeps capturing **locally only** for at most 6 s (a pre-roll for Live), and treats itself as paused for `'live'`. The controller calls `pause('live')` when the Live session starts and `resume('live')` on `session:ended` (the spotter then waits out a cooldown so the tail of the assistant's voice cannot retrigger it). If a wake is never picked up (no `pause('live')` within 15 s), it resumes listening on its own.
- `takePreroll()` returns PCM16 16 kHz mono, starting about 1.5 s before the name was recognised and including everything since, so "Hey Marcus, make the text bigger" in one breath is not clipped. Call it once the Live socket is open, send it as audio before opening the Live mic; calling it releases the spotter's mic.
- Pause reasons: `live`, `tts` (keeps the mic warm, no streaming, instant resume), `muted`, `disabled` (`wakeEnabled:false`), `push-to-talk-only`, `manual`. It listens only when none is active.
- Status for the UI: `{ state: 'off'|'starting'|'listening'|'reconnecting'|'paused'|'unavailable', listening, pausedFor[], cloud: true, engine, detail? }`. `listening` is true only while audio is actually being sent; map it to `phase:'listening_for_name'` and the `ListeningLight`. `unavailable.detail` is safe to show verbatim.

## Stage-day checklist

Do this in order, on the demo machine, on the venue network, with the same microphone you will use on stage.

1. **Key and build.** `REPO/.env` has `GEMINI_API_KEY` (never visible on screen). `npm run build` passes. Start the app once; open the dock.
2. **Permissions.** System Settings, Privacy and Security: grant **Microphone** and **Screen Recording** to the app (and to Terminal/your IDE if you launch from there). **Quit and restart the app** after granting; macOS only applies them to a fresh process. Check there is no pending permission sheet hiding behind a window.
3. **Network.** Wake word and Live both need the internet. Test on venue Wi-Fi; have a phone hotspot ready. If the dock shows "voice activation is unavailable", it is the network or the mic permission: use the button/shortcut.
4. **Hotkeys.** Press `Cmd+Alt+Space`: a session opens with the last persona. Press `Cmd+Alt+M`: it stops and the dock returns to resting. Press `Cmd+Alt+Space` twice quickly: it must not restart the running session. If a combo does nothing, another app owns it; use the next fallback listed above and quit the conflicting app (Raycast, Alfred, Zoom, screen recorders).
5. **Say each name three times in the room.** "Hey Marcus" then "Hey Amelia", normal voice, at stage distance, with the room noise and the speakers on. Record hits: 3 of 3 for both names is required to use the wake word live. 2 of 3 or worse: **use the hotkey/button and say so honestly.**
6. **Negative test.** Say normal sentences and the other name's neighbours ("Hey Mark", "Marcus Aurelius", "Hey Google"): nothing should open. Let the audience laugh at one on purpose, and keep talking.
7. **Self-trigger test.** Start a session and let the persona greet. It must not re-wake itself, and the listening light must be off while Live runs and back on after the session ends.
8. **Headset or external mic** if the room is loud or speakers feed the mic; it also makes the first words more reliable.
9. **Narration script.** Do not say either persona name in intro narration or on slides with audio; say it only when you mean to wake it.
10. **Privacy line for judges.** "While the light is on, the microphone audio is streamed to Google's speech model to hear the name; mute turns it off, the hotkey needs no microphone, and a production version would run a local wake word." Show the mute control once.
11. **Fallback plan.** If the wake word misses twice in a row, press the hotkey or click Start without commentary beyond one sentence; the product is the teaching, not the wake word. Do not retry the wake word more than twice on stage.

## Unverified (needs a real voice, a real room, or a fresh machine)

- Any real human voice: accents, mumbling, older voices, soft speech, distance, room noise, music, a second speaker, a TV.
- Real key presses for the global shortcuts (registration was verified; the system may swallow `Cmd+Alt+Space` for Finder search before Electron sees it, hence the fallbacks).
- macOS permission prompts for global shortcuts on a clean machine (none expected).
- The spotter running inside the full app with a real microphone. What *was* verified: the real renderer capture path in a hidden Electron window (see the verification log), fed by a synthesised `MediaStream`; Chromium's own `--use-file-for-fake-audio-capture` returned pure silence on this macOS for every WAV format tried, so it could not be used. LIVE has wired the spotter into `dock/controller.ts` (read, not exercised by me).
- The cap test ran one wake before and one after the first rotation (see the log); it did not play speech during the swap itself.
- Echo: persona TTS leaking into the spotter is blocked by pausing for the Live session, not by acoustic echo cancellation.

## Verification log (all on 31 Oct 2026, this Mac, real API key, synthetic speech)

| Check | Result |
|---|---|
| `npm run typecheck` | clean, whole repo (the DOM types needed by two wake files come from `/// <reference lib="dom" />`; no tsconfig change) |
| `npm test` | 40 files / 657 tests pass (wake: matcher 49, spotter 22, hotkey 7, collisions 2; 18 opt-in live tests are skipped by default) |
| `npm run build` | passes |
| Matcher on 97 real transcript streams | 0 wrong/false fires; wake recall above the 90% asserted over clips that returned text |
| Spotter e2e, `WAKE_LIVE=1 npx vitest run tests/wake/live-e2e.test.ts` (real spotter, production `mintWakeToken` ephemeral token) | 17/17 on the final run: 7/7 positives, 10/10 negatives (10 s each, no wake). Earlier runs before the language hints and the stable-interim rule: 6/7 positives (Flo voice intermittent) |
| 12-minute connection cap, `WAKE_LIVE_LONG=1 npx vitest run tests/wake/live-long.test.ts` | pass: woke at 32 s and again at 692 s; the token log shows a **proactive rotation mint at 573 s** (a connection opened at 33 s would have been closed by the server near 633 s); no `reconnecting`/`unavailable` status in between. (A first run of this test had a harness bug that replayed the schedule and instead exercised 22 wake, pause, resume cycles; all 22 worked.) |
| Real renderer path in Electron (`spikes/wake/harness/`, hidden window, `scripts/electron-lock.sh WAKE`) | `createMicAudioSource` produced 100 ms Int16 frames at 10 per second from `getUserMedia`-shaped streams (verified with Chromium's default fake device: peak 32767), then a WAV played through a `MediaStreamDestination` into the real spotter, real ephemeral token and real service woke `marcus` ("Hi Marcus." interim) 2.6 s after playback started (about 0.6 s after the name ended), status went `listening` then `paused` for `live`, and `takePreroll()` returned 1.5 s of audio. The recogniser also emitted `Haymaker` for "Hey" along the way without a false wake |
| Global hotkeys in the real app | `[hotkey] start: CommandOrControl+Alt+Space, CommandOrControl+Alt+Shift+Space, CommandOrControl+Alt+Shift+S \| stop: CommandOrControl+Alt+M, CommandOrControl+Alt+Shift+X` printed by the built app under the Electron lock (`ALONGSIDE_HEADLESS=1 ALONGSIDE_MOCK=1`); `/state` reported phase `listening_for_name`. Start then Stop against the real `registerSession` is a unit test. **Physical key presses: not tried.** |
| Raw error text | QA found raw IPC/API text in `lastError`; fixed (plain-English `detail`, raw error in the console, unit-tested) and the spotter now self-recovers when the network returns (tested with fake timers) |
