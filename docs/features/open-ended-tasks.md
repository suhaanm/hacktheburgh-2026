# Open-ended tasks and Claude background agents

> The worker types or says any task; Knack routes it by code, asks for one click that says in plain words what an agent can do, and can start the owner's own Claude command as a monitored background agent that writes and runs code.

**Capability:** Agents that do the work safely · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (owner decision D63 (01:05 UTC); merged to main at 01:42 UTC (fded20e): the service, API, router, Claude command runner, skills and browser runner, the consent cards and task list in the dashboard, the pills window in the desktop shell and the Live tool start_task, with docs/TASKS.md; not seen end to end by the lead; two small real runs of the owner's claude command were made with the owner's approval (a one-word prompt, then a throwaway copy of the protected-file layout; about US$0.125 in all, D64), and no real task has been run; the task box on Home ('What should Knack do?') is on main since 02:39 UTC (d9f8929) and has not been seen working with a real service) · **Page:** `docs/features/open-ended-tasks.md` · **Targets:** Wordsmith

## What it does

The worker types or says any task; there is no preset list of jobs. Knack routes it with code to one of four routes: answer inline, work in the agent's own browser window, show how on the real screen, or hand code, data and file work to a Claude background agent. Every route except 'answer' waits for the worker's click. Skills, including the owner's existing ones, load into context, and background agents show as small pills at the top right.

## How it works

Routing is code: weighted rules over the worker's words score each route; a clear winner (a score of 2 or more and one ahead) is the route and no model is called. A plain question with no evidence for an action route is answered. When the rules tie and an action route has some evidence, one closed-list proposal may be asked of the fast model, and code accepts it only if it is 'answer' or the words already supported that route, so a model can break a tie but never introduce a risky route (tested); otherwise Knack asks one question as a card with a button per route. The desktop route never clicks from typed text: it answers 'show instead'.

A Claude background agent is the owner's own claude command started as a monitored child in its own process group, in a working folder (a named folder, or a new one under ~/Knack/work made only after the click), with an environment allow-list of six variables (home, path, language, terminal, user, temp folder: Knack's keys and every other variable are not passed) and a refusal of any permission prompt so the child cannot hang. Stream events become short progress lines (a tool name and a file's base name, never contents, commands or prompts), with a 'Still working' note after 30 seconds of silence. Caps: a wall-clock cap (30 minutes by default, 1 to 120 by setting or on the card), an idle cap of 10 minutes, an output cap of 20 MB and a spend limit: every task starts the command with its own budget flag, US$2 by default and set by the worker in Settings from US$0.5 to US$20, shown on the consent card, part of the pinned command hash and kept when the worker chooses the wider option; Knack also watches the cost the command reports and ends the process group itself when it reaches the limit and holds for half a second with no result, and the task then reads 'Reached the spend limit you set.' with its folder still openable. A routine-started task uses the lower of the setting and US$2. The cost the command reported is kept as a number in the task row and added to the result line.

Stop, the kill file and the caps end the whole process group (a polite stop, a hard kill after 3 seconds, then a last sweep), so a shell command the agent started does not outlive the task. A crash becomes one plain reason, never raw error text.

The final message is untrusted text: the row shows its first sentence cut to 140 characters plus Open folder or Open file; the full text is kept locally with mode 0600 and a model sees it only through the existing quarantined reader.

The consent card says in plain words: 'Knack will start a Claude agent on this Mac. It can read and change files and run commands. Your Claude account is used.' It names the working folder, a pinned hash of the exact command and the time cap; buttons are Allow for this task and Not now; behind 'More' is Allow everything for this task (the skip-permissions flag), sent only by that explicit choice, never by default, never from voice, never unattended. Before the start the command is rebuilt and compared with the pinned hash; any change refuses it. The consent route needs the worker's approval actor and the per-boot token, which a page, a model, the voice actor and the agent actor cannot supply. Ledger rows are metadata only (a start row with scope, skill count and prompt size; a stop row with reason, seconds and output size); if a row cannot be written nothing starts.

A routine may start a task unattended only with its own consent record that allows it (rung A2 or A3, not revoked), and then only with the narrower scope. At most 3 tasks run at once and 20 wait for a click. By voice, a Live tool named start_task hands the worker's request to this service (it is declared only when code can answer it, and its code is on main in apps/desktop/src/main/live); the model is told it never starts anything and must say what the answer tells it, for example to tap Allow on the card, and the answer it gets is a closed record (the route chosen and whether a card is waiting), never a summary.

Skills are read from the front matter of skill files in the owner's Claude folders and in ~/Knack/skills, chosen by a word-matching score in code; for non-agent routes the top two are added as untrusted guidance that can never grant a permission, change a gate or add a tool.

**What is different.** Routing is code with a closed list of routes (a model may break a tie but never add a risky route), every non-answer route waits for one consent card that says in plain words what the agent can do, and the agent is a monitored child with caps and a kill path.

## Where to see it

Needs you (the consent card, with Allow and Not now and the wider choice behind More), Routines and Home (a short list of background tasks, live), small pills at the top right of the screen while an agent works (a second overlay column; Knack's own attention stays in the bottom-right column), and Hey Knack by voice ('Hey Knack, do ...'). The task box is on Home (owner request 4.18, decision D66): one field, 'What should Knack do?', placeholder 'Type a task, then press Enter', at most 500 characters, example lines that fill the field and never send, and a microphone where the desktop app can open its Ask bar. A task is only ever something the worker typed or said and then sent; the answer shows at once in its own plain line; a consent card prints its scope whole with two buttons of one size (the wider choice behind More) and focus never lands on a button, so the Enter that sent the task cannot also answer its consent; with no task service running the box says nothing was started and keeps what was typed. The service API is in docs/API_CONTRACT.md (Tasks API).

## Demo moment

Not rehearsed. On Home type a task in 'What should Knack do?' and press Enter (or say it by voice, which needs the owner's first launch and a Gemini key); the consent card names what the agent can do; one click on Allow for this task; a pill appears at the top right; the result arrives as one sentence with Open file. Say that a request such as 'click Save in Excel' is answered with steps, not a click. Allowing a real task spends the owner's Claude account (US$2 limit by default), so click Allow only if a real task is meant, and do not film it until the lead has seen it work.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| 160 tests (the document's count; a static count of test functions on main is 115, and the document does not say what accounts for the difference) cover the routing, the child process handling (fake commands that succeed, crash, report a sign-in error or a usage limit, hang, ignore the stop signal, flood output, stay quiet, or start grandchild processes), the manager and the routes; every one uses a fake claude and a fake model | offline tests with fakes; not a real task | `docs/TASKS.md; services/agent/tests/tasks/` |
| Two real runs of the owner's claude command, each with the owner's approval in chat, each a few cents (about US$0.125 together, on the owner's Claude account): run 1, a one-word prompt, showed the main flags accepted by version 2.1.319, exit 0 in 3.1 seconds, about US$0.063; run 2, on a throwaway copy of the protected-file layout, also showed the budget flag (limit US$0.50) and the flag that disables slash commands accepted, real tool events turned into progress lines that carry base names only, exit 0 in 14.4 seconds, US$0.0619 | two real one-prompt runs, owner approved; not tasks and not results | `docs/TASKS.md; docs/DECISIONS.md (D64)` |
| The deny rules for Knack's protected files were verified once against the real command: its Write tool was refused for a new rung record, a new queue item, a new memory file and an overwrite of the kill file; its Read tool was refused for the token file and the memory file; ordinary writes in the same folder worked, and the files on disk afterwards confirmed nothing was created or changed. Not verified, and to be assumed bypassable: a shell command (a redirect is not a file-tool call), the rules under 'Allow everything', and a path reached through a symlink or another spelling. The budget stop itself was never reached | one real run on a temporary copy of the layout, owner approved | `docs/TASKS.md; docs/DECISIONS.md (D64)` |
| The browser route is tested on a real headless Chromium with a scripted model; no real computer-use model was called; a finished free-text web task reads 'Reported, not checked' because code has no ground truth to verify it | offline tests; not a real run | `docs/TASKS.md` |

## Honest limit

Full computer access is the owner's choice (D63), and the deny rules are a guard rail, not a sandbox: they were verified once against the real command for its file tools, and a shell command can bypass any such rule (untested), as can the rules under 'Allow everything' (untested). Desktop clicks are not wired to typed tasks: the desktop route always answers 'show instead', and real clicks stay behind the supervised first-click test. The owner's own Claude hooks run inside the child, as they do in a terminal. Claude command usage is billed to the owner's own Claude account, outside the US$200 Gemini cap; the brakes are the spend limit, the time cap and Stop, and the command's cost arrives mostly at the end, so a single very expensive turn can overshoot the limit by that turn. The budget stop itself was never reached in a real run, so the name of the result the command gives at its budget is a guess that Knack covers by matching any name containing 'budget' and by watching the reported cost itself. Also unverified against the real command: allow-everything, the skill deny rule and the add-directory flag. Each remaining check needs another approved real run. A task running when the service restarts becomes 'failed' with a plain reason. The consent card, the pills and the voice tool have not been seen working with a real task.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a workflow the worker defines by typing or speaking, with one plain consent per task and a monitored agent

## 30-second spoken script

> You can type or say any task. Knack decides in code whether to answer, browse, show you on screen, or hand the job to a background agent, and for the last two it asks for one click that says in plain words what that agent can do. The background agent is your own Claude command, run as a monitored child with a time cap, and Stop ends the whole thing. It writes and runs code on your Mac because the owner chose that, so the consent card says so, and it never happens inside routines. This is on the main build and tested with a fake command and two small real checks run with the owner's approval; no real task has been run, and the task box on Home has not been used with a real task.

## Slide bullets

- Type or say any task; code routes it: answer, browser, show on screen, or a Claude agent.
- One consent card per task, in plain words: what the agent can read, change and run.
- Monitored child: allow-listed environment, time caps, Stop and the kill file end the process group.
- Full computer access is the owner's choice (D63); deny rules are not a sandbox; never in routines.
- 160 tests with a fake command and two small real checks; the task box is on Home, not yet used with a real task.

## Sources

- `docs/DECISIONS.md (D63)`
- `docs/OWNER_REQUESTS.md`
- `docs/IMPLEMENTATION_SPEC.md (6.5, amended)`
- `docs/knack-ux/views.md`
- `docs/TASKS.md`
- `services/agent/understudy_agent/tasks/`
- `apps/desktop/src/main/knack/agent-pills.ts`
- `apps/dashboard/src/lib/useTasks.ts`

## Related pages

`background-agents.md`, `connections.md`, `security-layers.md`, `hey-knack.md`
