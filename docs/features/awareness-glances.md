# Awareness and glances

> Knack notices rhythm on the Mac with nothing leaving it, and looks at the screen only when you have said it may.

**Capability:** Coach on the screen · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (layer is on by default; no frame is sent until the worker records consent; macOS Screen Recording is the owner's to grant) · **Page:** `docs/features/awareness-glances.md` · **Targets:** G-Research

## What it does

Knack notices cursor dwell, typing rhythm and which kind of app is in front, on the Mac, and nothing leaves it. When it needs to see the screen it sends one downscaled frame to a Gemini model, only if you allowed it, and never stores it.

## How it works

Level 0 is always on: input rhythm, cursor dwell and wandering, app kind (no titles stored), hashed browser events. Level 1 is a triggered glance: when the stuck probability crosses its threshold, a loop signature appears, or the worker presses the hotkey, one image (long edge at most 1280 pixels) is held in memory for one call and sent through the egress guard, which logs size, hash, model and latency but never the image. A frame is skipped while macOS secure input is on, when the frontmost app is on the denylist, and in any unattended run. The answer is a closed schema (app kind, task phase, blocker, confidence, optional box); no free text is kept. Periodic glances about every 30 seconds are opt-in and off by default, with a count in the menu bar.

## Where to see it

First use shows a consent card with equal buttons: Yes, Not now, Never. Your data, 'What it looked at or sent' lists every call; 'Capture and glances' holds the switches.

## Demo moment

Show the consent card and press Not now: no frame leaves. Then show Your data with its record of what was sent (size, model, time) and no picture.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Glance on eight synthetic sandbox screens, five repeats each: the same answer as the modal answer 98% [87, 100] (39 of 40) with flash-lite, median 0.88 s, 95th percentile 1.02 s; the answers were plausible for the screen 100% [91, 100] | synthetic sandbox screenshots; repeats of one screenshot are not independent | `evals/modelbench/REPORT.md (section 4)` |
| Awareness is a registered flow in the privacy canary run (0 of 11,456 planted tokens reached the model port) | synthetic, offline | `evals/report.md (Privacy layer)` |

## Honest limit

An allowed frame is raw pixels: the guard decides whether a frame may leave, from which source and what is recorded, but it does not redact, and the provider then sees the whole screen; what a provider does with it is the provider's policy and is not measured here. The gate depends on the caller reporting secure input and the denylist correctly. The screen-change watcher is not built (it needs Screen Recording).

## Hackathon target

- **G-Research (make the invisible visible)**: the hidden state of being stuck made visible, with consent

## 30-second spoken script

> Knack has two levels of awareness. The first runs on your Mac and sends nothing: how you type, where the cursor dwells, what kind of app is in front. The second, a glance, sends one small picture to a Gemini model when you appear stuck, only if you said yes, and never stores it. It is skipped over password fields and from apps on your denylist. Not now and Never are as easy as Yes.

## Slide bullets

- Level 0: rhythm, dwell, app kind. On the Mac. Nothing leaves.
- Level 1: one downscaled frame, in memory for one call, only with consent.
- Never from a denylisted app, over secure input, or in an unattended run.
- The ledger records size, hash, model and latency; never the image.
- Limit: an allowed frame is raw pixels.

## Sources

- `docs/REQ5_PLAN.md (section 3)`
- `docs/FLAGS.md`
- `docs/DECISIONS.md (D30)`
- `CLAUDE.md (Screen frames)`
- `evals/modelbench/REPORT.md`
- `evals/report.md (Privacy layer, Limitations register)`

## Related pages

`privacy-ledger.md`, `cue.md`, `hey-knack.md`
