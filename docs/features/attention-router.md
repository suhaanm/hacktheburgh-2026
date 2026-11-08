# One attention layer

> One router decides whether, where and when the worker is told anything. Silence is the default; safety is never held back.

**Capability:** A calm product: window, attention, context · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (engine built; desktop wiring built; held-out simulated evaluation met 11 of 12 criteria) · **Page:** `docs/features/attention-router.md` · **Targets:** HRT

## What it does

Every part of Knack that could interrupt (Cue, briefings, approvals, agent results, pauses, the help-level glance) goes through one router. It decides whether, where, when and how loudly the worker is told. Safety is shown once and is never batched or repeated.

## How it works

A pure function of the event, the worker's state (flow, a call, a meeting, a screen share, away, locked) and recent history. Principles in code: silence is the default; safety is never suppressed; a decision is shown once and reminded at most once; one voice at a time; nothing important sits unseen (a passive marker exists the moment an item exists); learning can only quiet; the worker can always see why (a one-line fixed reason); metadata only. Channels run from a silent log through a badge, banner, chip and toast to a question card and voice. A digest replaces pings when the worker returns. A new interrupting type needs a row in the attention table first.

**What is different.** Every producer of an interruption goes through one router with a fixed reason for every decision, and learning can only quiet, never amplify.

## Where to see it

Everywhere a notice appears; Needs you; the corner card; Settings, Interruptions (Rarely, Balanced, Often).

## Demo moment

In a meeting or screen share, three cues are dropped and an injection pause is still shown within seconds in content-free words; the held approval appears at the first pause after the meeting.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Against show-everything: 0.150 [0.141, 0.159] non-safety interruptions per flow hour against 1.512 [1.447, 1.582]; 0 hard-quiet breaches; 98.4% [98.0, 98.7] of important items seen in their window; median delay 85 s; 0 of 528 urgent safety items missed | synthetic, 200 simulated workers, 2,000 worker-days, frozen config | `evals/attention/report_held_out.json` |
| Against one daily digest: the digest is quieter but sees 28.3% of important items in window and misses 182 urgent safety items | synthetic, same run | `evals/attention/report_held_out.json` |
| 11 of 12 pre-registered criteria met; criterion 7 not met: later-day can-wait toasts rose by +0.33 a day [+0.08, +0.58], the wrong direction; learning made no difference to any aggregate measure | synthetic, same run; corrected after the fact and the correction is in the file | `evals/attention/report_held_out.json (post_hoc_corrections)` |

## Honest limit

Every number is simulated: workers, schedules, reactions and attention costs are our assumptions. It shows the policy behaves as designed, not that people find it natural. A one-a-day digest costs less attention in the assumed cost model. The n = 4 teammate check was not run.

## Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision policy judged against two baselines and a pre-registered list of criteria

## 30-second spoken script

> Anything in Knack that could interrupt you goes through one router. It decides whether, where and when. Silence is the default; safety is shown once and never held back. In a simulated workday it interrupted a worker in flow about a tenth as often as showing everything, with no breaches of a meeting or a screen share, and almost every important item still seen in time. One of twelve criteria failed, and we published that.

## Slide bullets

- One router for Cue, briefings, approvals, results and pauses.
- Silence is the default; safety never held, never repeated.
- 0.150 against 1.512 non-safety interruptions per flow hour (simulated).
- Criterion 7 not met: later-day toasts rose by 0.33 a day.
- Simulated workers, not people; the live check was not run.

## Sources

- `docs/ATTENTION_DESIGN.md`
- `evals/attention/report_held_out.json`
- `evals/attention/PLAN.md`
- `docs/KNACK_UX.md (section 4, push versus pull)`
- `evals/report.md (Attention routing)`

## Related pages

`needs-you.md`, `knack-shell.md`, `cue.md`
