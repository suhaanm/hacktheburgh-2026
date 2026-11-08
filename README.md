# Knack

*Built at Hack the Burgh XIII, Edinburgh, 7 to 8 November 2026. Formerly called Understudy. Tracks: Metaview, HRT, G-Research, Wordsmith, JetBrains.*

**Knack watches how people do the same task, shows where a novice loses time against an expert, coaches on the real screen with help that fades, and lets an agent take repetitive work only when the worker says yes.**

Say "Hey Knack" in any app. Knack sees your screen (only after you say yes), rings the thing to click next, talks you through it, and, when you ask it to do the click, does it behind one card that only your real mouse click can answer.

## What it does

- **Voice and on-screen guidance in every app.** Hey Knack (or Option-Space) opens a live conversation with Gemini Live. Knack looks at your screen, draws a ring on what matters and speaks back. It works over any app on your Mac, your browser included.
- **A coach whose help fades.** Help levels L1 to L4 are decided by plain code, not by a model, so a chatty model cannot talk the product out of fading. Skipped steps are priced in seconds and in wrong answers, because in seconds skipping looks free.
- **The work genome.** A worker's steps are aligned with the nearest expert's, so the gap shows up step by step, with an interval on every number and two controls (expert against expert, shuffled labels).
- **Routines, one opt-in at a time.** Knack finds repeated work, proposes an automation, watches first, runs it, and parks the one irreversible step until you click.
- **Do it for me, in any app.** A task about your screen proposes a card naming the window; Allow for this task starts an 8 second countdown, then every step goes through the safety pipeline (pinned window, trusted target read, structural gates, denylist, kill key). Sending, buying, deleting and submitting stay gated.
- **A browser agent that stops for you.** It browses and reads on its own, clears cookie banners, and waits for your click at anything it cannot judge.
- **Background agents.** A job that needs code or data work starts your own Claude command as a monitored background agent, after one consent card.
- **A firm view.** Admins see a firm in aggregate: roles, people, automation, risk and forecasts, as bands and counts, never a worker's screen.
- **Role packs.** UK benefits processor (deep), data analyst and programmer (thin). A memory file the worker owns adapts Knack to them.

## Try it

macOS, Python 3.12 or newer, `uv`, Node.

```bash
make setup          # Python and Node dependencies
make demo           # offline demo on generated data, mock models, nothing leaves the laptop
```

For live models and voice, copy `.env.example` to `.env`, set `GEMINI_API_KEY` and the model names, then `make live`. Knack.app is built with `cd apps/desktop && npm run package` (unsigned, sealed with a stable identity so macOS keeps its permissions across builds). First launch walks you through Microphone, Speech Recognition, Screen Recording and Accessibility; the two consent cards answer only to a real click.

## Evidence, and what it does not show

- Results are on data we generated (a simulated firm and generated learners), each with n and a 95% interval; the Evidence page says what every number was measured on. `make eval` rebuilds `evals/report.json`.
- HRT: every stuck-model forecast goes into a hash-chained ledger before its outcome exists, scored only from that record on fresh seeds. Of 10 registered claims, 8 passed and 2 did not, and both are printed. Where the generator changed, the model lost its edge, so a guard watches the ledger and falls back. See `evals/hrt/`.
- Computer use with Gemini on our sandbox calculators, pre-registered and held out: 18 of 20 households completed with correct inputs (Wilson interval 0.70 to 0.97), below the 0.80 lower bound we registered; the 2 misses paused instead of finishing, and 20 of 20 injected pages paused. See `evals/agentic/`.
- Not claimed: that coaching makes novices into experts, or that any of this is validated on real workers. The live study with four teammates is small (n = 4), and the simulated study hit a floor and says nothing about the coach.

## Safety and privacy

Capture stores roles and salted hashes: no page text, no URLs, no field values, and sensitive fields are never touched. Frames leave the device only through an egress guard that writes a ledger row (size, hash, model, latency; never the image), only after you opted in, never from a denylisted app or while a password field has the keyboard. The model proposes and code decides: levels, permissions, routing and gates are deterministic code. Every automation is opt-in; an unattended run never gets the desktop.

## Disclosure

- **Alongside.** Knack's desktop app starts from Alongside, the author's own earlier open-source library (`github.com/suhaanm/deepmind-hackathon`, first commit 31 October 2026, before this event, MIT). Of the 303 source files in the copy we started from, 168 are byte-identical in `apps/desktop`, 100 are modified, 35 are not carried over, and 355 files under `apps/desktop/src` are new (a read-only count at about 03:20 GMT on 8 November). Alongside's own real actuator was on by default; in this copy it is off, and real clicks go only through the agent service's guarded path (pinned window, gates, a card, a kill key). Notices for third-party code travel in `THIRD_PARTY_NOTICES.md` and in `Adapted from` headers.
- **How it was built.** Most of the code was written by Claude Sonnet 5.5 agents working under the owner's direction, one agent per area, with a lead agent merging. The owner chose the product, the targets and the limits. The decisions are in `docs/DECISIONS.md`.

## Layout

`services/engine` (analytics, coach brain, routines; FastAPI), `services/agent` (supervisor, safety pipeline, navigators, tasks), `apps/dashboard` (React), `apps/desktop` (Electron), `extension` (Chrome MV3), `packages` (role packs, schemas, design), `evals` (reports, pre-registered plans and results). The build plan is `docs/IMPLEMENTATION_SPEC.md`.
