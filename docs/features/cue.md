# Cue: stuck rescue

> When you are stuck, Cue finds the next step from what experts do, asks one question only if unsure, explains in one line, then goes quiet.

**Capability:** Step in when stuck · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (engine and desktop code built and tested; evaluated on simulated workers only; not run on a real desktop) · **Page:** `docs/features/cue.md` · **Targets:** HRT, G-Research

## What it does

When you are stuck, Cue works out the most likely next step from what experts do and what is on your screen, shows it, and asks one multiple-choice question only when it is unsure. It gives the reason in one short line, then goes quiet and later holds help back so you can recall the step yourself.

## How it works

Candidates come from the expert transition graph: the top three next steps with probabilities. In a browser the target is grounded from the page first; elsewhere a fresh frame and a closed menu go to a Gemini model. The decision is pure code from the stuck probability, the margin between the top two steps, grounding confidence, mastery, cooldowns, the daily attention budget, flow state and consent. Outcomes: nothing (the default), confirm, a cue at a tier, one question, or a small offer. Tiers: a ring; a ring and a chip of at most 40 characters; a ghost-cursor demonstration; a voice whisper of at most 8 words. Hard caps: at most 3 cues in 10 minutes, one question per episode, at least 90 seconds between cues for the same skill unless asked, never in a denylisted app or over secure input. The 'why' is 12 words or fewer, once.

## Where to see it

On the real screen when stuck (ring and card); More, then Live coach; Growth shows the effect over time.

## Demo moment

Pause on the case note page. Cue asks one question with three options; answer by click, key 1 to 4 or voice. The ring shows the step, one line gives the reason, then silence. Say that its numbers so far come from simulated workers.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| False nudges 0.73 an hour (97.5% interval [0.64, 0.83]); the target was 1.0 or less: met | synthetic, 40 simulated personas, 481.5 hours, held-out seed | `evals/cue/held_out.json` |
| 'Faster to resume' target not met: median paired difference 0.0 s (97.5% interval [-9.5, 0.0]); the exploratory mean difference is -34 s [-43.7, -25.2] | synthetic, same run, 1,119 stuck episodes | `evals/cue/held_out.json` |
| Cues reached 27.7% [25.1, 30.1] of stuck episodes; 97.1% of stuck seconds stayed silent; wrong-target cues 0.01 an hour | synthetic, same run | `evals/cue/held_out.json` |
| Learning the tier policy online is left off: the off-policy estimate does not clear the rule's value and the effective sample size is too small | synthetic, 491 logged decisions | `evals/report.md (Cue analysis)` |

## Honest limit

Every Cue result comes from a simulator written by the team that wrote the policy: stalls, pauses and interruption costs are assumptions. One of two primary targets was met. Cue reaches about a quarter of stuck episodes by design. It has not been run on a real desktop or on a person.

## Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision under an attention budget, with a pre-registered held-out evaluation
- **G-Research (make the invisible visible)**: the hidden next step shown at the moment of need

## 30-second spoken script

> An understudy knows everyone's lines. When the actor goes blank, the prompter whispers the next line, and over time stops needing to. Cue does that for work. It notices you are stuck, finds the likely next step from what experts do, and asks one question if it is not sure. Then it explains in a line and goes quiet. In simulation it stayed under one false nudge an hour. It did not make people resume faster at the median, and we say so.

## Slide bullets

- Next step from the expert path and the screen; one question only when unsure.
- Ring, chip, ghost cursor, whisper: the lightest that works, never more.
- Hard caps: 3 cues in 10 minutes, one question per episode.
- Simulated: false nudges 0.73 an hour (target 1.0 met); faster-to-resume not met.
- Not run on a real desktop or on people.

## Sources

- `docs/REQ7_PLAN.md (section 4)`
- `evals/cue/held_out.json`
- `evals/cue/PLAN.md`
- `evals/report.md (Cue analysis, Limitations register)`
- `docs/DECISIONS.md (Cue follows its ring by zone)`
- `README.md (What did not hold up)`

## Related pages

`live-coach.md`, `growth-independence.md`, `screen-annotations.md`, `hey-knack.md`
