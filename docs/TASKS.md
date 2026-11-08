# Tasks: ask Knack for anything

Written by Track T (Claude Sonnet 5.5), 8 Nov 2026, for owner requests 4.18 to 4.21 (`docs/OWNER_REQUESTS.md`) and decision D63. Code: `services/agent/understudy_agent/tasks/`. Tests: `services/agent/tests/tasks/` (141, all with a fake `claude` and a fake model: no model call and no real CLI run in any test). Closed shape of every row and card: `packages/schema/task_row.schema.json` (a test validates every state the service produces against it).

## What a worker can ask

Anything, typed in the task box or said ("Hey Knack, ..."). There is no preset list of jobs. Examples that route without a question:

| The worker says | Route | What happens |
|---|---|---|
| "What is the capital of Scotland?" | `answer` | Answered at once, inline, by the planner model (or locally for the time and date). |
| "Write a python script that renames the files in my downloads folder" | `claude_agent` | A card asks for a click, then Knack starts the owner's own Claude CLI as a monitored child. |
| "Analyse sales.csv and plot the monthly totals" | `claude_agent` | Same. |
| "Go to gov.uk and find the benefit rates" | `browser` | A card, then the agent's own browser window, through the safety pipeline. |
| "Click Save in Excel" | `desktop` | Knack does not click from a typed task. It shows plain steps instead. |
| "Sort this out for me" | `unclear` | One question card: answer it, look it up, work on files or code, or show me how. |

## The router (code decides, a model may only propose)

`tasks/routing.py`. The route comes from a closed set. Weighted rules over the worker's words give each route a score; a clear winner (score of 2 or more and 1 ahead) is the route and no model is called. A plain question with no evidence for an action route is answered. When the rules tie and an action route has some evidence, ONE closed-enum proposal may be asked of the fast model (skipped offline); code accepts it only if it is `answer` or the words already supported that route. Otherwise the task asks one question. A model can never introduce a risky route the words do not support (tested). Every route except `answer` waits for the worker's click.

A folder the worker names (`~/Projects/x`, or an absolute path under `/Users` or `/Volumes`, that exists) becomes the working folder; a named file means its folder. Otherwise a task gets its own folder `~/Knack/work/<slug>`, made only after the click.

## Consent: one real click per task

`needs_consent` is a card. The Claude agent card says, in plain words: "Knack will start a Claude agent on this Mac. It can read and change files and run commands. Your Claude account is used." It lists what it can do and cannot do, the working folder, the pinned command hash (first 12 characters of a hash of the exact command line, folder and environment keys), the cost note ("Uses your Claude account, not Knack's models.") and the time cap. Buttons: **Allow for this task** and **Not now**. Behind a small "More": **Allow everything for this task** (`--dangerously-skip-permissions`), only ever sent by that explicit choice, never by default, never from voice, never unattended. Before the start the command is rebuilt and compared with the pinned hash; any change refuses the start ("The command changed after you saw it").

The consent route is a release route: actor `worker_approval` plus the per-boot token (the dashboard proxy adds the token; a page, a model, the voice actor and the agent actor are refused). Stop is a stop route: no token. The kill file and `POST /kill` stop every task.

The browser card is the same shape (kind `browser`, "Uses Knack's models.", no "More"). Nothing starts before the click.

## The Claude CLI background agent

`tasks/claude_cli.py`. The planner starts the owner's `claude` (the path from `KNACK_CLAUDE_BIN`, else `~/.local/bin/claude`, else `PATH`) as:

`claude -p "<prompt>" --output-format stream-json --verbose --permission-prompts none --session-id <uuid> [--disable-slash-commands | --disallowedTools Skill(..)] --settings '<deny rules>' --permission-mode acceptEdits --allowedTools Read,Edit,Write,Glob,Grep,Bash`

in its own process group, with the working folder as the current directory. `--permission-prompts none` means anything not allowed is refused, so the child can never wait on a prompt nobody sees. The prompt is the worker's request plus a short header and the names (never the text) of the selected skills.

- **Environment allow-list**: `HOME PATH LANG TERM USER TMPDIR`, nothing else. Knack's Gemini, ElevenLabs and every other variable are not passed; Knack's own virtualenv is dropped from `PATH`. The child finds the owner's own Claude login through `HOME`, exactly as in a terminal. Knack never reads, copies, prints or logs a Claude credential.
- **Monitoring**: the stream-json events become short progress lines (a tool name and a file's base name: "Reading data.csv", "Running a command"; never contents, commands, prompts, addresses or the owner's hook output), a "Still working" note after 30 s of silence, a wall-clock cap (30 minutes by default, 1 to 120 by setting or by the card), an idle cap (10 minutes without an event), and an output cap (20 MB, killed at once when crossed).
- **Stop**: Stop, the kill file and `POST /kill` send SIGTERM to the whole process group, SIGKILL after a 3 s grace, then a last SIGKILL sweep, so a shell command the agent started does not outlive the task. A crash or a non-zero exit becomes ONE plain reason ("The Claude agent stopped unexpectedly (exit code 3)", "Claude isn't signed in on this Mac...", "Your Claude account has reached a usage limit"); stderr is classified, never shown.
- **Report back**: the final message is untrusted text. The row shows its first sentence (cut by code to 140 characters) plus **Open folder** or **Open file** (the single file the agent wrote, if exactly one). The full text is kept in `data/tasks/<id>.result.txt` (mode 0600) and, for a Knack-made folder, `RESULT.md` in it. A model sees it only through the existing quarantined reader; nothing in the task code sends it to a model.
- **Ledger and audit (metadata only)**: the privacy ledger gets a `claude_agent_start` row (task id, scope enum, skills count, bytes of the prompt) and a `claude_agent_stop` row (stop code, seconds, output bytes, and the cost the CLI itself reports). `skill_text` rows record that skill text went to a planner model (a count and a size). The hash-chained audit log gets one line per transition (proposed, allowed, started, done and so on). Never the request, never the output. If a ledger row cannot be written, nothing starts.
- **Unattended**: `TaskManager.start_for_routine(routine_id, text)` starts a task with no card ONLY when that routine's own consent record allows an unattended run (mode `unattended`, rung A2 or A3, not revoked), always with the narrower scope, `attended: false`. It is called by code that schedules routines, not over HTTP.

Restart: task files persist in `data/tasks/` (mode 0600). A task that was running when the service restarted becomes `failed` ("Knack restarted while this was running") and a leftover child is ended, but only if its command line carries that task's own session id. A task waiting for a click survives a restart (one more than a day old is dropped then).

## Skills

`tasks/skills.py`. The index reads only the YAML front matter `name` and `description` from `~/.claude/skills/*/SKILL.md`, `~/.claude/plugins/**/skills/*/SKILL.md` (a depth-bounded walk that skips `node_modules` and caches) and `~/Knack/skills/*/SKILL.md` (and single `.md` files with front matter). Local, no network, at most 500 skills, 64 KB read per file, symlinks that leave the folder are skipped, a name clash is won by the worker's own folders.

Selection is code: BM25 over name and description. For `claude_agent` the Claude CLI loads `~/.claude` skills itself (HOME is passed) and Knack adds the selected names to the prompt as a hint. For `answer`, `browser` and `desktop` the top two skills' instructions (6 KB each at most) are added to the planner context wrapped as untrusted guidance; they can never grant a permission, change a gate or add a tool, because none of those is decided by prompt text. Settings: `use_claude_skills` (default on; off also passes `--disable-slash-commands` to the child), a per-skill off list, and `max_minutes`.

**Add a skill**: create `~/Knack/skills/<name>/SKILL.md` that starts with

```
---
name: house-style
description: How we write case notes, in one line that says when to use it
---
The instructions, in plain words.
```

It appears in Settings within 30 seconds (or `GET /skills?refresh=1`). The same file in `~/.claude/skills` is also used by Claude Code.

## Limits and honest notes

- **Full computer access is the owner's choice (D63).** A Claude agent that may run commands can reach anything this account can, including Knack's own files. The `--settings` deny rules for Knack's protected files (kill file, denylist, queue, token, rung record) are defence in depth, **not a sandbox**: the real CLI accepted the flag in the one approved run, but their enforcement was not tested, and a shell command can bypass any such rule. `--dangerously-skip-permissions` is the explicit second choice.
- **Desktop clicks are not wired to typed tasks.** `desktop` always answers "show instead", with or without `data/rung_cleared.json`. The service never clicks. Real clicks stay behind the supervised R1 test and the desktop app's own gates; connecting them to typed tasks is an owner decision (see the report).
- **Browser results are reported, not checked.** A free-text web task has no ground truth for code to verify, so a finished run reads "Reported, not checked: ...". The browser route uses Knack's models (cost), runs in the agent's own browser profile (no saved logins), has no allowlist and obeys the worker's denylist, and stops before anything irreversible.
- **Tested with fakes.** The Claude CLI path is tested with a fake `claude` (ok, crash, sign-in error, usage limit, hang, ignores SIGTERM, floods output, quiet, grandchild processes). One real run was made, once, with the owner's approval: flags `-p`, `--output-format stream-json`, `--verbose`, `--permission-prompts none`, `--session-id`, `--max-turns 1`, `--settings`, `--permission-mode acceptEdits`, `--allowedTools` were accepted by claude 2.1.319; events `system/init`, `system/hook_started`, `system/hook_response`, `assistant`, `rate_limit_event` and `result/success` were seen; exit code 0 in 3.1 s; the CLI reported about US$0.063. Flags not exercised in that run: `--dangerously-skip-permissions`, `--disable-slash-commands`, `--disallowedTools Skill(..)`. The browser runner is tested on a real headless Chromium with a scripted model; no real computer-use model was called.
- **The owner's Claude hooks run inside the child**, as they do in a terminal. Their output is never shown.
- Cost: Claude CLI usage is billed to the owner's Claude account, outside the Gemini cap. The time cap and the CLI's reported cost per task are the only brakes besides Stop.
- At most 3 tasks run at once; at most 20 wait for a click.

## API

See `docs/API_CONTRACT.md`, "Tasks API" and `packages/schema/task_row.schema.json`. Voice (the Live tool `start_task` follows this; the model itself is told only a closed answer, never the summary line): `POST /tasks` with actor `voice` and `source: "voice"`, or `understudy_agent.tasks.submit_task(text, source="voice")`; creating a task never starts a Claude agent, a browser run or a click.
