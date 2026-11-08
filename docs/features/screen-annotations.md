# On-screen annotations

> A thin ring with corner ticks and one short label, drawn on the real control, once.

**Capability:** Coach on the screen · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (the lead viewed screenshots; not yet confirmed end to end on a real Chrome tab) · **Page:** `docs/features/screen-annotations.md` · **Targets:** G-Research

## What it does

When Knack points at something it draws a thin ring with corner ticks and one short label on the real control. There is no permanent chip; one annotation at a time.

## How it works

In a browser the extension sends element rectangles so the ring lands exactly (DOM first: exact, free and instant). Elsewhere a fresh frame goes through the egress guard to a Gemini vision model that must answer in a closed form (found or not, and a box); a box is accepted only after sanity checks on size, position and denylisted regions. The ring follows its zone when the page moves and is dropped at once when the zone is gone. A ghost cursor, a small dot with a short trail, can show a move. The overlay is hidden while the Knack window itself is focused, and draws no label while an agent is acting.

**What is different.** The ring is grounded from the page first (exact), a vision model answers only in a closed form with sanity checks, and the overlay draws no label while an agent is acting.

## Where to see it

On the real screen, over the control being pointed at. Settings, Coaching turns coaching off.

## Demo moment

On the sandbox calculator, a ring lands on 'Check cliff edges' and one short label says why. Press the button; the ring goes. Nothing else is drawn.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Pointing by description: Gemini flash-lite hit 95% [90, 98] (140 of 147), median 0.93 s, 95th percentile 1.37 s; Gemini flash 95% [90, 97], median 3.31 s; OpenAI fast 75% [67, 81], median 1.72 s; elements not on screen were rejected 43 of 43 by each model; clicking the viewport centre hits 2% | synthetic sandbox screenshots, 147 positives and 43 negatives | `evals/modelbench/REPORT.md (section 1)` |
| In the simulated study the ring was drawn on arrival for 5 of 12 prompts, because the cliff button only exists on a calculator result tab, not on the case note page where the prompt usually arrives | simulated participants (language model), not people | `evals/study_sim/REPORT.md (section 5)` |

## Honest limit

The overlay is drawn on the primary display only; per-display overlays are a known limit. Pointing numbers are on screenshots of our own sandbox pages, not real apps. Whether the ring lands right on a real Chrome tab, end to end, has not been confirmed by the lead.

## Hackathon target

- **G-Research (make the invisible visible)**: the next step made visible on the real screen

## 30-second spoken script

> When Knack points, it points once and small: a thin ring with corner ticks and a few words, on the real control. In a browser it lands exactly, because the extension tells it where the element is. Elsewhere a Gemini vision model finds the target, and the answer is checked before anything is drawn. No chip, no glow, nothing loops. On our sandbox screenshots the fast model found the right element 95 percent of the time, in under a second.

## Slide bullets

- Thin ring, corner ticks, one label; nothing permanent.
- Browser: exact rectangles from the extension. Elsewhere: a vision model, checked.
- Follows the page; disappears when the target does.
- Gemini flash-lite: 95% [90, 98] on 147 pointing cases, median 0.93 s (synthetic screens).
- Drawn on the primary display only: stated limit.

## Sources

- `docs/REQ5_PLAN.md (section 5)`
- `docs/IDEA_BOARD.md (REQ-4)`
- `docs/DECISIONS.md (Cue follows its ring by zone)`
- `evals/modelbench/REPORT.md`
- `evals/study_sim/REPORT.md`
- `docs/KNACK_UX.md (section 7)`

## Related pages

`cue.md`, `awareness-glances.md`, `models-and-routing.md`
