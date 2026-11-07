# Third-party notices

Alongside adapts a small amount of third-party code and design. Every adapted file carries a header comment (`// Adapted from <project> (<licence>) ...`) and appears once in the table below. The list below comes from `grep -rn "Adapted from" src apps scripts tools tests`.

## 1. farzaa/clicky and its Windows fork (MIT)

Upstream: <https://github.com/farzaa/clicky> (Swift, macOS) and its Windows fork (C#). Both are MIT licensed. Alongside ported the *algorithms, animations and window recipe* (the bezier pointer flight, arrow and circle drawing, the pointing bubble, the click-through overlay window, screenshot sizing) to TypeScript and SVG, and the safety-policy and audit-log *rules* of its Hermes plugin (Python) to TypeScript; no Swift, C# or Python source is included.

```
MIT License

Copyright (c) 2026 Farza

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Not carried over from Clicky: its analytics, its Cloudflare worker, its audio assets, its login-item registration and its signing configuration.

## 2. Google Gemini example code (`google-gemini/gemini-live-api-examples`)

Provided to builders by the hackathon guide. **That repository ships no LICENSE file**, so no licence text can be reproduced here; it is used as the guide's own example code and each derived file says so in its header. If the upstream publishes a licence later, follow it. The Live JS example (`gemini-live-ephemeral-tokens-websocket/frontend`: `geminilive.js`, `mediaUtils.js`, `audio-processors/`) was converted to TypeScript and extended (context compression and session resumption, `GoAway` handover, instant interruption flush, per-call async tool dispatch, change-gated frames).

`google-gemini/gemini-skills` (Apache-2.0, per its `LICENSE` and `plugin.json`) was read as API reference for model IDs and parameters; no code from it is included in this repository.

## 3. Adapted files

Every file below starts with a header `// Adapted from <project> (<licence>) <upstream path>`. Regenerate this list with `grep -rn "Adapted from" src apps scripts tools tests` and check that the count matches.

### From farzaa/clicky and its Windows fork (MIT)

| File in this repo | Upstream path | What was adapted |
|---|---|---|
| `src/main/capture/index.ts` | `leanring-buddy/CompanionScreenCaptureUtility.swift` | Screen capture and JPEG sizing; own windows kept out of the shot |
| `src/main/capture/sizing.ts` | `leanring-buddy/CompanionScreenCaptureUtility.swift` | Screenshot sizing and JPEG compression |
| `src/main/capture/overlay-window.ts` | `leanring-buddy/OverlayWindow.swift` | Click-through, `screen-saver` level, all Spaces, over full-screen apps |
| `src/renderer/overlay/flight.ts` | `leanring-buddy/OverlayWindow.swift` (`animateBezierFlightArc`); Windows fork `OverlayWindowManager.cs` (`FlyToSequence`) | Quadratic bezier arc, smoothstep ease, scale pulse, heading from the tangent; visit several points in order |
| `src/renderer/overlay/annotations/GhostCursor.tsx` | `leanring-buddy/OverlayWindow.swift` (`BlueCursorView`) | Bezier flight, scale pulse, tangent heading, in SVG + `requestAnimationFrame` (visual only, never clicks) |
| `src/renderer/overlay/annotations/labels.tsx` | `leanring-buddy/OverlayWindow.swift` | Pointing bubble: scale-bounce entrance, character-by-character typing |
| `src/renderer/overlay/annotations/shapes.tsx` | Windows fork `DrawingOverlayControl.cs` | Circle and arrow drawing: glow, round caps, head polygon |
| `src/renderer/overlay/arrow.ts` | Windows fork `DrawingOverlayControl.cs` (`BuildArrowHead`) | Arrow head length and spread |
| `src/renderer/overlay/geometry.ts` | `leanring-buddy/CompanionManager.swift`, `CompanionScreenCaptureUtility.swift` | Screenshot pixel to screen point mapping (Clicky's double Y-flip deliberately removed) |
| `src/main/agency/policy.ts` | `hermes-clicky-plugin/safety_policy.py`, `hermes-clicky-plugin/permission_policy.py` | Permission tiers (observe / point / confirm before action / scoped autopilot, mapped onto Alongside's `agency` setting) and the extra blocking words (destructive, payment, credential entry, permission prompt, send); rewritten in TypeScript with our own URL, app, file and rate-limit rules |
| `src/main/agency/audit.ts` | `hermes-clicky-plugin/audit_log.py` | Append-only JSONL action log, redacted by default (no screen content, no typed text, no URL paths or queries) |

### From google-gemini/gemini-live-api-examples (no LICENSE file upstream)

All under `gemini-live-ephemeral-tokens-websocket/frontend/`.

| File in this repo | Upstream path | What was adapted |
|---|---|---|
| `src/renderer/live/wire.ts` | `geminilive.js` | Message builders and the server-message parser, as a pure protocol layer |
| `src/renderer/live/connection.ts` | `geminilive.js` | Socket setup and receive; resumption, `GoAway` handling and reconnect are our additions (the example has none) |
| `src/renderer/live/LiveSession.ts` | `script.js`, `geminilive.js`, `mediaUtils.js` | Message handling, tool fan-out and session wiring, extended (compression, async tool dispatch, interruption flush, idle and goodbye endings) |
| `src/renderer/live/audio.ts` | `mediaUtils.js` (`AudioStreamer`, `AudioPlayer`); `audio-processors/capture.worklet.js`, `playback.worklet.js` | Browser audio in and out; worklets inlined as Blob URLs |
| `src/renderer/live/frames.ts` | `mediaUtils.js` (`BaseVideoCapture` 1 fps interval) | 1 fps frame sender, with change gating added |

Original, not adapted: `src/renderer/live/tools.ts`, `types.ts`, `index.ts`, `src/renderer/dock/controller.ts`, `tests/live/*`, `spikes/live/*`.

Files that only mention Clicky in a comment, as an explanation of a decision and with no code derived from it (for example `src/main/overlay-controller.ts`), are not listed above.

## 4. Ideas credited, no code taken

- **Sentient OS** (AGPL-3.0): read only for ideas (act only after a fresh read; one editable Markdown profile where the user's edit wins; approval only by a real click). **No code, comments, prompts or structure were copied or translated from it** (checked: `grep -ri sentient src` returns nothing). The act-for-me loop's discipline (mutate only after a fresh screen read, never auto-retry, success only when verified) is written in our own words. Alongside's own code is therefore not subject to the AGPL.
- **HeyClicky, Copilot Vision, Gemini Live, Coco and others** were studied as prior art (see the README); nothing was taken from them.

## 5. npm dependencies

Installed from the npm registry under their own licences: Electron, electron-vite, Vite, React, react-dom, zod, dotenv, `@google/genai`, vitest, TypeScript and their types. See each package's `LICENSE` in `node_modules`.

## 6. Data and facts

Statistics in the README are quoted from Age UK (3 Sep 2026) and Good Things Foundation (Digital Nation 2026) with links; they are reproduced as facts with attribution, not as text.
