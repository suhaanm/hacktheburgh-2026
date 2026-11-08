# Stop everything

> One key, one button, or one menu row stops every agent. The stop never depends on a model.

**Capability:** Agents that do the work safely · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built · **Page:** `docs/features/stop-everything.md` · **Targets:** Wordsmith

## What it does

A single action stops every running agent and holds them stopped until the worker presses Resume. It is reachable from the keyboard, the corner pill, the sidebar and the menu bar.

## How it works

Stopping flips a kill flag on disk and cancels the supervisor's current generation, so the stop never waits for a model call. Results from an older generation are dropped even if a task ignores cancellation. Paths: Option-Shift-Command-K anywhere, Shift-Command-K or Shift-Escape inside Knack, the Stop button on the corner pill while something runs, a small Stop button in the sidebar, and 'Stop everything' or 'Pause for 1 hour' in the menu bar. The Stopped card stays until Resume, and Resume needs a per-boot token so a web page cannot clear it. Page content cannot change or click the kill switch.

**What is different.** Stop is a flag on disk plus a supervisor that drops stale results, so it does not depend on any model call or any in-process cooperation.

## Where to see it

Corner pill (while working), sidebar footer, menu bar, keyboard.

## Demo moment

Start a routine; the window minimises and the pill shows Stop. Press Option-Shift-Command-K: the pill becomes a Stopped card, and nothing continues. Press Resume.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Stop call to finished median 33 ms; kill flag to finished median 39 ms; within 1 s in 8 of 8 trials | synthetic, busy laptop | `evals/report.json (runtime, stop)` |
| The kill flag was reported by the engine in 24 of 24 simulated participants' data folders and the coach stayed silent after it in 24 of 24 | simulated participants (language model), not people | `evals/study_sim/REPORT.md (section 5)` |
| Reviewer findings that the kill hotkey never wrote the flag and that stop did not stop an in-flight action were fixed and re-verified | offline reproducers | `evals/review/safety_actuator.md (S-03, S-04)` |

## Honest limit

Measured on a laptop other processes were also using, with fake desktops for the real actuator. The in-flight stop of a real click has not been exercised on a real desktop.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a visible, key-reachable stop for an agent that acts

## 30-second spoken script

> Every agent in Knack can be stopped three ways: the keyboard, a button on the corner pill, or the menu bar. The stop flips a flag on disk and cancels the supervisor, so it never waits for a model. In our tests it reached a running helper in about thirty-three milliseconds. The Stopped card stays until you press Resume, and a web page cannot clear it.

## Slide bullets

- Option-Shift-Command-K anywhere; Stop on the pill; menu bar; sidebar.
- Kill flag on disk plus supervisor cancel: no model call involved.
- Median 33 ms to finished; 8 of 8 within 1 s.
- Stopped card stays until Resume; page content cannot touch it.
- Real-actuator stop: tested against fakes only.

## Sources

- `docs/reference-notes/vision-os.md`
- `docs/KNACK_UX.md (sections 1, 7, 9)`
- `evals/report.json (runtime, stop)`
- `evals/review/safety_actuator.md`
- `README.md (Privacy and safety)`
- `evals/study_sim/REPORT.md`

## Related pages

`security-layers.md`, `knack-shell.md`, `background-agents.md`
