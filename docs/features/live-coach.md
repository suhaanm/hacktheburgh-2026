# Live coach and fading help

> A coach that speaks rarely, only after two stuck signals, and gives less help as a skill is mastered.

**Capability:** Coach on the screen · **Status:** verified · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Navigation note (landing).** The lead's views rule (`docs/knack-ux/views.md`, from owner requests 4.1, 4.2, 4.11, 4.12 and 4.17 at about 00:50 UTC) is reorganising where screens live. Where this page says 'More, <screen>', check `apps/dashboard/src/components/home/navModel.ts` on main for the final place. 'Today' (Live coach) is retired as a worker destination; the coach itself is unchanged.

This page covers Live coach: one decision at a time, with a dignity gate, Fading help: levels L1 to L4 decided by code.

## Live coach: one decision at a time, with a dignity gate

**Status:** verified · **Page:** `docs/features/live-coach.md` · **Targets:** HRT

### What it does

From live events, the coach decides whether to say nothing, nudge, draw a ring or offer to take over. Silence is the default: it speaks only after two stuck signals in a row, then waits.

### How it works

Plain code, no model. The actions are silent, nudge, annotate and takeover. The dignity gate acts after two consecutive stuck signals, then holds a cooldown, and stays silent when unsure. The worker's own reaction labels each prompt without a questionnaire: followed within 10 seconds, dismissed within 4, repeated within 10, undone within 10. Those labels feed a bandit that logs the probability of each choice, so any new policy is first judged off-policy on old logs (inverse propensity, self-normalised, doubly robust) before it is switched on.

**What is different.** A dignity gate holds the coach back, and a bandit logs the probability of every choice so a new policy is judged off-policy on old logs before it is switched on.

### Where to see it

More, then Live coach (address #/today) shows the current task and the help level. The ring and card appear on the real screen.

### Demo moment

A synthetic novice skips the cliff check. A ring lands on that button, once. The worker ignores it and nothing nags. Replay the same case as an expert: no prompt at all.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| 14 of 14 planted skips ringed over 48 apprentice cases; 0 prompts to experts; no ring on a clean case | synthetic; a test assertion, not a report section | `services/engine/tests/coach/test_replay.py` |
| Dignity gate: false nudges 1.83 to 0.05 an hour (a fall of 97%); stuck events reached 21% to 5%; nudges 186 to 17; median latency 30 s to 60 s | synthetic, 4 people, leave one person out; no interval in the report table | `evals/report.md (Coaching dignity gate)` |
| Off-policy check: the naive on-policy average has mean error +0.193 and its interval covers the truth 0% of the time; IPS covers 96%, self-normalised IPS 96%, doubly robust 88% | synthetic simulator, 24 replications of 2,400 decisions | `evals/report.md (Off-policy evaluation)` |

### Honest limit

The gate buys quiet with coverage: it reaches 5% of stuck events, not 21%. The simulator's reward structure is ours and implicit labels are noisy (a dismissal can mean 'I already knew'). In the detailed 6,000-decision run every estimator's interval missed the true value of 0.018. The replay set plants the skip, so a clean score is expected.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: a decision rule under a false-nudge budget, judged off-policy before it is switched on

## Fading help: levels L1 to L4 decided by code

**Status:** verified · **Page:** `docs/features/live-coach.md` · **Targets:** HRT

### What it does

Help gets lighter as a skill is mastered, from L1 'watch me' to L4 'on my own'. The level is set by plain code, so a chatty model cannot talk the product out of fading.

### How it works

The engine's level module is the authority (L1 full help, L2 small help, L3 a dot, L4 gone). It promotes one level after three clean runs in a row and demotes after two or more errors among the last five counted outcomes; an assisted run is neutral; a level change resets the streak and the window so the new level gets a fair trial. The desktop's own learner store, kept from the owner's earlier library, has its own step-up settings. Per-skill mastery with forgetting feeds the engine and decays with absence, so a skill not seen for weeks is not treated as mastered. The worker's pace setting (gentle, steady, quick) changes how many clean cases come before a prompt gets lighter. The level shows for two seconds when it changes, then lives in the menu bar and Settings.

**What is different.** Levels are code with no model, no randomness and no clock, and mastery can only lower a level after an absence, never raise it.

### Where to see it

Live coach shows the level; Growth has a closed 'The fade' disclosure; Settings has Coaching (on or off, level lock).

### Demo moment

Open Live coach and point at the level; open Growth, then The fade, and show prompts getting lighter as the curve rises. Say that code, not a model, moved the level.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Skill tracing follows the planted curve only weakly: mean Spearman 0.18 across four personas (0.17, 0.18, 0.25, 0.12); mastery saturates on high-volume personas | synthetic, 4 personas, 21 days | `evals/report.md (Skill tracing)` |
| The level rules are code with no model, no randomness and no clock: three clean runs up, two errors in five down, absence can only lower a level | offline tests; a separate small reference implementation agrees on shared cases | `services/engine/understudy_engine/skills/levels.py; docs/reference-notes/drigil.md` |

### Honest limit

The mastery estimate is weak on our data: it saturates within a day or two, so it cannot resolve a slow learning curve. Decay with absence is shown in unit tests, not by this data. The levels are a mechanism, not evidence that people learn.

### Hackathon target

- **HRT (best use of data for predictions and decisions)**: promotion and demotion rules decided in code, with forgetting

## 30-second spoken script

> The coach is built to say very little. It speaks only after two stuck signals in a row, then waits. In a replay, it rang all fourteen planted skips and never prompted an expert. And help fades: after three clean runs the level goes down one step, decided by plain code, not by a model, so it cannot be talked out of fading. The skip is planted, so that is a test, not a result about people.

## Slide bullets

- Silence is the default; speaks after two stuck signals, then a cooldown.
- 14 of 14 planted skips ringed, 0 prompts to experts (synthetic, 48 cases).
- False nudges 1.83 to 0.05 an hour with the gate; it buys quiet with coverage.
- Levels L1 to L4 are code: three clean runs promote, two errors in five demote.
- A new policy is judged off-policy on logged propensities first.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (7.1 policy, skills)`
- `docs/reference-notes/drigil.md`
- `docs/reference-notes/pupil.md`
- `evals/report.md (Coaching dignity gate, Skill tracing, Off-policy evaluation)`
- `docs/drafts/CLAIMS.md (C60)`
- `docs/KNACK_UX.md (section 3, Live coach)`

## Related pages

`screen-annotations.md`, `cue.md`, `growth-independence.md`, `stuck-model.md`
