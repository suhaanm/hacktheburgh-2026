# Open-ended tasks and Claude background agents

> The worker types or says any task; Knack routes it by code, asks for one click that says in plain words what the agent can do, and can start the owner's own Claude command as a monitored background agent with full computer access.

**Capability:** Agents that do the work safely · **Status:** landing · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** landing (owner decision D63 (01:05 UTC); a vertical slice tested with a fake claude is on the Tasks branch (worktree-agent-a40520cb1ac55fcdc, Track T); docs/TASKS.md has not been seen; nothing run with the real command; not on main) · **Page:** `docs/features/open-ended-tasks.md` · **Targets:** Wordsmith

## What it does

The worker types or says any task (a task box on Home, and 'Hey Knack, do ...'). Knack routes it with code to one of four routes: answer inline, work in the agent's own browser window, show how on the real screen, or hand code, data and file work to a Claude background agent. Every route except 'answer' waits for the worker's click. Skills, including the owner's existing ones, load into context, and background agents show as small pills at the top right.

## How it works

Routing is code: weighted keyword and shape rules score each route; a clear winner is the route; when they cannot separate, an optional fast-model call may propose one value from the closed list, and code accepts it only if it is 'answer' or the rules already found some evidence for it, so a model can break a tie but never introduce a risky route; otherwise Knack asks one question, as a card with a button per route. The desktop route never clicks from this service: it answers 'show instead'. A Claude background agent is the owner's own claude command started as a monitored child in its own process group, in a working folder, with an allow-listed environment (home, path, language, terminal, user, temp folder: Knack's keys and every other variable are never passed), a 30-minute wall-clock cap, a 10-minute idle cap and an output cap. Stream events become short progress lines (a tool name and a file's base name, never contents, commands or prompts). Stop, the kill file and the time cap end the whole process group. The final message is returned as untrusted text. Two permission scopes: files and commands (edits and a fixed tool list, any prompt denied so the child cannot hang), or 'everything' (the skip-permissions flag), used only when the worker picks that second option on the consent card for that task. One consent card per task says in plain words what the agent can do (read and change files, run commands, uses the owner's own Claude account, not Knack's models). Ledger rows are metadata only. An unattended run never gets 'allow everything', and real desktop clicks stay behind the supervised first-click test.

**What is different.** Routing is code with a closed list of routes (a model may break a tie but never add a risky route), every non-answer route waits for one consent card that says in plain words what the agent can do, and the agent is a monitored child with caps and a kill path.

## Where to see it

Home (the task box and a short list of background tasks) and the voice tool in Hey Knack; pills at the top right while an agent works, with Knack's own attention (approvals, voice, Stop) staying in the bottom-right column. Not verified on main.

## Demo moment

Not available yet. When it lands and the lead has seen it: type 'summarise this CSV'; the consent card names what the agent can do; click once; a pill shows progress; the result arrives as text the worker reads. Do not film until then.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| The routing, the child process handling, the manager and the routes are covered by tests that use a fake claude command; nothing was run against the real command | offline tests with a fake command; not a real run | `services/agent/tests/tasks/ (branch worktree-agent-a40520cb1ac55fcdc)` |

## Honest limit

Full computer access is the owner's choice (D63) and the permission deny rules for Knack's own protected files are defence in depth, not a sandbox: a shell command can reach anything the owner's account can. This sits against the routines layer's rule that automations are a JSON step language and model-written code is never executed; the two are different layers and D63 governs the new one, but a judge will ask. Claude CLI usage is billed to the owner's own Claude account, outside the US$200 Gemini cap. Nothing here is verified on main.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a workflow the worker defines by typing or speaking, with one plain consent per task and a monitored agent

## 30-second spoken script

> You can type or say any task. Knack decides in code whether to answer, browse, show you on screen, or hand the job to a background agent, and it asks for one click that says in plain words what that agent can do. The background agent is your own Claude command, run as a monitored child with a time cap, and Stop ends the whole thing. It has full computer access because the owner chose that, so the consent card says so. This is landing and not verified on the main build.

## Slide bullets

- Type or say any task; code routes it: answer, browser, show on screen, or a Claude agent.
- One consent card per task, in plain words: what the agent can read, change and run.
- Monitored child: allow-listed environment, time caps, Stop and the kill file end the process group.
- Full computer access is the owner's choice (D63); deny rules are not a sandbox.
- Tested with a fake command; landing, not on main.

## Sources

- `docs/DECISIONS.md (D63)`
- `docs/OWNER_REQUESTS.md`
- `docs/knack-ux/views.md`
- `services/agent/understudy_agent/tasks/ (branch worktree-agent-a40520cb1ac55fcdc)`
- `docs/TASKS.md (landing)`

## Related pages

`background-agents.md`, `connections.md`, `security-layers.md`, `hey-knack.md`
