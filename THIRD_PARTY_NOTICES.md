# Third-party notices

Keep this file current. Every file that carries code from another project starts with a header comment: `// Adapted from <project> (<licence>) <upstream path>`. Every such file appears once in the tables below.

## Carried over from Alongside

The desktop app starts as a copy of the owner's Alongside project. Alongside's own `THIRD_PARTY_NOTICES.md` records code adapted from:

- **farzaa/clicky** (MIT): overlay window recipe, bezier pointer flight, arrow and circle drawing, screenshot sizing, and the rules behind the agency policy and audit log.
- **google-gemini/gemini-live-api-examples** (no licence file upstream): the Live session wiring, used as the hackathon guide's example code. This code is only used if voice is enabled, and voice is off by default.

**When copying Alongside into `apps/desktop`, merge Alongside's `THIRD_PARTY_NOTICES.md` into this file and keep every `Adapted from` header.** The owner's own Alongside code needs no notice.

**Merged on 7 Nov 2026** (the authoritative copy, with the full MIT licence text, is `apps/desktop/THIRD_PARTY_NOTICES.md`; it travels with the app). Files in `apps/desktop` that carry an `Adapted from` header:

| Files | Source | Licence | Notes |
|---|---|---|---|
| `src/main/capture/{index,sizing,overlay-window}.ts`, `src/main/agency/{policy,audit}.ts`, `src/renderer/overlay/{flight,arrow,geometry}.ts`, `src/renderer/overlay/annotations/{GhostCursor,labels,shapes}.tsx` | farzaa/clicky | MIT | overlay window recipe, bezier pointer flight, arrow and circle drawing, screenshot sizing, agency policy and audit rules |
| `src/renderer/live/{wire,connection,LiveSession,audio,frames}.ts` | google-gemini/gemini-live-api-examples | no licence file upstream | Live session wiring; voice stays flagged off in this build and these files are not used by the demo |
| (idea only, no code) | Sentient OS | AGPL | credited in Alongside's notices; nothing copied |

Alongside's npm dependencies keep their own licences (see `apps/desktop/package.json`). `apps/desktop/.userdata*/` holds the owner's local replay data and is ignored by git.

## Copied from MIT sources (add a row for each file)

| File here | Source | Path upstream | Licence | Notice |
|---|---|---|---|---|
| _none yet_ | clickyyy (https://github.com/jayamitkatariya/clickyyy) | e.g. `src/shared/command-safety.ts` | MIT, Copyright (c) 2026 Jay Katariya | include licence text |
| _none yet_ | VisionOS (https://github.com/yukevindai/VisionOS) | e.g. `backend/r3_vision/orchestration.py` | MIT, Copyright (c) 2026 Kevin Dai | include licence text |
| `vendor/clicky/clicky_lift/lease.py` | rickkdev/clicky, a Windows fork of farzaa/clicky (https://github.com/rickkdev/clicky ; upstream https://github.com/farzaa/clicky) | `hermes-clicky-plugin/scoped_autopilot.py` | MIT, Copyright (c) 2026 Farza | reshaped: tool-name scope, monotonic clock, parent narrowing, audit-safe events; full licence text in `vendor/clicky/LICENSE` |
| `vendor/clicky/clicky_lift/postcheck.py` | same | `hermes-clicky-plugin/post_action_verification.py` | MIT, Copyright (c) 2026 Farza | reshaped: declarative postconditions over code-read fields; full licence text in `vendor/clicky/LICENSE` |
| `vendor/clicky/clicky_lift/__init__.py` | same | `hermes-clicky-plugin/` (package layout and names only) | MIT, Copyright (c) 2026 Farza | header only |

Include the full MIT licence text of each source once the first file from it is copied.

## Ideas credited, no code taken

Re-implemented from the idea only: Mark8, Pupil, Drigil, Stride, MOA, BandIt, Rouge, PodsControlMac, and the Okidoki idea of record once and replay. See `docs/REFERENCES.md`.

## Dependencies

Installed from package registries under their own licences. Record notable ones here as they are added (for example Playwright, FastAPI, statsmodels, lifelines, React, Electron).

## Later (if used)

Skills or connectors from `anthropics/knowledge-work-plugins` (Apache-2.0): keep the licence text, retain notices and state changes.
