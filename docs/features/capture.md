# Text-free capture

> Knack records when you are active and which kind of step you took, never what you read.

**Capability:** See the work · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built · **Page:** `docs/features/capture.md` · **Targets:** G-Research, Wordsmith

## What it does

A Chrome extension records roles and salted hashes of what a worker clicks, opens and searches: no page text, no URLs, no field values. It is off until the worker switches it on.

## How it works

A content script (isolated world, local salt) turns each click, navigation, focus, scroll bin, tab switch, copy or paste flag and search (length only) into a small event with an origin (real or synthetic) and an actor (human or agent). A service worker batches events to the local engine every 2 seconds. Identifiers are hashed with a per-install salt; fields named in packages/schema/sensitive_fields.json are never touched. The engine keeps an append-only JSONL log, partitioned real and synthetic, with a pure reducer so a replay always gives the same state. Agent actions run in a separate browser profile and never enter the human trace.

## Where to see it

The extension's popup holds the capture switch. In the app, Your data has a section for capture and glances with the same switch. First run asks once: Yes, Not now or Never, with equal weight.

## Demo moment

Open the sandbox calculator in Chrome with capture on, work one household, and show the capture switch in the popup and in Your data. Say the sentence from first run: it records when you are active, never what you read. Say too that the ribbon in the demo is drawn from synthetic traces; capture is what would feed it for a real worker.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Ten schema-valid events from a real page reached a stub server in about 3.3 s; typing and paste in a password field produced zero events; no page text, URL or secret in the payload | real browser, one Chromium build, one run, stub server | `docs/SPIKES.md (S3)` |
| In the simulated study the extension sent 7,310 of 7,334 events, schema-valid share 1.0000; the event files hold no participant text (0 strings had to be removed) | simulated participants (language model), not people | `evals/study_sim/REPORT.md (section 5)` |
| Extension logic is covered by 192 test functions (static count) | offline tests | `evals/report.facts.json (tests.by_dir, extension/tests)` |

## Honest limit

Chrome only, one browser build checked. Real data is thin: the only real signal is the team's own machine timestamps; there are no real benefits-processor traces (limitation eval-thin-real-data). Because it never stores text, some habits are invisible by construction.

## Hackathon target

- **G-Research (make the invisible visible)**: the raw material for making work visible without recording content
- **Wordsmith (most complicated end-to-end browser-use workflow)**: the human trace is kept apart from agent actions

## 30-second spoken script

> Knack starts by watching how work is done, not what the work says. A small Chrome extension records which kind of step you took and when: a click, a search, a tab switch. It stores no page text, no web addresses and no field values, and it never touches password fields. It is off until you switch it on, and the record stays on this laptop.

## Slide bullets

- Records the kind of step and the time, never the content.
- No page text, no URLs, no field values; sensitive fields are never touched.
- Off until the worker switches it on; the record stays on the device.
- Agent actions are kept out of the human trace.
- Checked once in a real browser; ten events, none with text.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (6.1, 7.5)`
- `docs/SPEC_LIST.md (CAP-1 to CAP-9)`
- `docs/SPIKES.md (S3)`
- `README.md (Privacy and safety)`
- `evals/study_sim/REPORT.md`
- `docs/knack-ux/07-first-run.md`

## Related pages

`privacy-ledger.md`, `your-data.md`, `work-genome.md`
