# Open-ended tasks, skills and background pills

> Owner requests from about 00:50 UTC: the worker types or speaks any task, skills and plugins load into context, and background agents show as small live pills. Nothing here is verified.

**Capability:** Agents that do the work safely · **Status:** landing · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** landing (owner requests 4.15 and 4.18 to 4.21 in docs/OWNER_REQUESTS.md, tracks T, V, A, C and E; no document, code or result seen when this was written; everything on this entry is unverified) · **Page:** `docs/features/open-ended-tasks.md` · **Targets:** Wordsmith

## What it does

The worker can type or speak any task in a task box on Home ('What should Knack do?') instead of choosing from a preset list. Skill files and plugins load into the agent's context automatically. Background agents appear as small pills at the top right with animated icons and update live without a refresh. The owner has also asked for computer use and background agents that can create code.

## How it works

Not verified. What is written down: the Home screen is to hold the task box and a short list of background tasks (docs/knack-ux/views.md); the open-ended track is Track T and the connections track is Track E (docs/OWNER_REQUESTS.md); the progress UI is to be as minimal as Claude Code's task list. Rules that already hold and must still hold: every automation is opt-in, an approval is a real click, irreversible steps wait for the worker, and the eight security layers sit between page content and any action. The existing rule that automations are a JSON step language and that model-written code is never executed sits against the request for agents that create code; how the two are reconciled is not documented yet (the runtime's raw mode, which runs model-written code on files the worker named, is foreground only and sandboxed).

**What is different.** Nothing is claimed: this entry records an owner request and the rules it must still obey.

## Where to see it

Home (the task box and the task list); the top right of the screen (pills). Not verified on main.

## Demo moment

Not available. Do not film until it lands and the lead has seen it.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| No evidence: requested and unticked on the owner's checklist | not run | `docs/OWNER_REQUESTS.md (items 4.15, 4.18 to 4.21)` |

## Honest limit

Everything on this entry is a request, not a result. The tension with 'model-generated code is never executed' is stated in the spec and has no recorded resolution.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a workflow the worker defines by typing or speaking, not one we preset

## 30-second spoken script

> This is the part still landing, so we say it plainly. The owner asked that you can type or speak any task, that skills and plugins load into the agent's context, and that background agents show as small live pills. None of that is verified yet, and the rules do not change: every automation is opt-in and an approval is always a real click.

## Slide bullets

- Request: type or speak any task, not a preset list.
- Request: skills and plugins load into context automatically.
- Request: background agents as small live pills, top right.
- Rules unchanged: opt-in, real-click approval, eight layers.
- Not verified; do not film until it lands.

## Sources

- `docs/OWNER_REQUESTS.md`
- `docs/knack-ux/views.md`
- `docs/IMPLEMENTATION_SPEC.md (6.5 and 7.2)`

## Related pages

`background-agents.md`, `connections.md`, `security-layers.md`
