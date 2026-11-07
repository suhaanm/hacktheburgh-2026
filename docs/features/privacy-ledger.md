# Privacy spine: egress guard and ledger

> Everything that leaves a Knack service goes through one logged choke point, with typed payloads and a record of what was sent. Pictures are never kept.

**Capability:** Privacy and safety · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (built, with a known gap: older desktop paths are gated off by default but not re-reviewed independently) · **Page:** `docs/features/privacy-ledger.md` · **Targets:** G-Research, Wordsmith

## What it does

One choke point sits between Knack and any remote model. Prompts are built from typed values, every call leaves a row in a ledger the worker can read, and a canary test plants secrets to see whether any reach the model.

## How it works

Text calls carry only typed payloads (ids, enums, numbers built by code) from registered purposes. Image calls carry one frame held in memory for one call; the ledger records size, hash, model and latency but never the image. A frame is refused while secure input is on, from a denylisted app, from an unknown source, and in any unattended run; the Gemini key lives only in the main process and renderers get ephemeral tokens. The canary harness plants synthetic secrets in eleven flows, with a capturing fake model port, and counts how many arrive. A layer that registered no flow is listed as none, never counted as passed. The older desktop code that could send screenshots and file text straight to a model is off by default (decision D38) behind one switch.

## Where to see it

Your data, section 'What it looked at or sent': every call, with a delete beside it. Evidence has the canary table.

## Demo moment

Open Your data and the record of what was sent: a row per call with model, size and time, no picture and no text. Say what is not in it: the older desktop paths, which are off.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| 0 of 11,456 planted canary tokens reached the model port across 88 runs of 11 flows (reference flows 0 of 728; integration flows 0 of 10,728); 0 leaks in 88 log, audit and queue files; the ledger was complete for every flow; one-sided 95% upper bound on the leak rate 3.35% per run | synthetic fixtures, offline, 8 seeds per flow | `evals/report.md (Privacy layer)` |
| 11 of 11 negative controls behaved as required (the instrument can fail); bucketing 0 failures over 594,114 cases; 27 of 27 must-catch shapes caught and 0 false positives on 34 ordinary values; static guard 0 violations in 345 files | synthetic, offline | `evals/report.md (Privacy layer)` |
| Independent privacy and honesty review (a separate Claude agent): no critical finding, 6 high; five fixed and re-verified at the time, one open then (older desktop paths that sent images and file text with no gate) | code review at 17:55 on 7 Nov; decision D38 has since switched those paths off | `evals/review/privacy_honesty.md` |

## Honest limit

Zero leaks says nothing about a flow that was not run, and the planted strings are exact strings only. An allowed frame is raw pixels: the guard does not redact them, and the provider's own policy is not measured here. Model calls the worker asked for are recorded as metadata only. The ledger cannot see other software on the laptop. The older Alongside desktop paths are off by default but have not been re-reviewed independently.

## Hackathon target

- **G-Research (make the invisible visible)**: what left the device made visible
- **Wordsmith (most complicated end-to-end browser-use workflow)**: an agent that uses cloud models without leaking what it reads

## 30-second spoken script

> Anything that leaves a Knack service goes through one door, and that door keeps a record. Text calls carry only typed values; images are held in memory for one call and never stored, and the record shows size, model and time but never the picture. We tested it by planting eleven thousand secrets in synthetic flows: none reached the model. That is a test of our code paths, not a promise about everything on your laptop, and the screen says so.

## Slide bullets

- One choke point; typed payloads; a ledger of every call.
- Frames: in memory for one call; ledger records size, hash, model, latency, never the image.
- Canary test: 0 of 11,456 planted tokens reached the model port (synthetic, 88 runs).
- Refused over secure input, from a denylisted app, and in unattended runs.
- Known gap: raw pixels when allowed; older desktop paths off by default.

## Sources

- `README.md (Privacy and safety)`
- `CLAUDE.md (Safety and privacy)`
- `docs/IMPLEMENTATION_SPEC.md (14.2)`
- `docs/DECISIONS.md (D30, D38)`
- `evals/report.md (Privacy layer, Limitations register)`
- `evals/review/privacy_honesty.md`
- `docs/REQ5_PLAN.md`

## Related pages

`your-data.md`, `awareness-glances.md`, `models-and-routing.md`
