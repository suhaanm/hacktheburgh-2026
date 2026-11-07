# Build orchestration: roster, ownership, protocol

Lead = the main session. It owns `docs/**`, `Makefile`, `scripts/**`, root configs, commits, pushes and merges. All build agents are **Claude Sonnet 5.5** (spawned with model `sonnet`; each states its model ID in its first message).

## Ownership (one writer per path; no shared files)

| Track | Owns |
|---|---|
| design | `packages/design/**` |
| engine-data | `services/engine/understudy_engine/{store,personas,cogs,genome,packs,api}/**`, `routes_data.py` (health, events, replay, packs, genome, graph/transitions, queue, audit, kill, eval/report), `cli.py`, tests in `services/engine/tests/{store,personas,cogs,genome,packs,api}/`. `api/app.py` includes the other tracks' routers if importable. |
| engine-analytics | `services/engine/understudy_engine/{hazard,policy,routing,trust,skills}/**`, `routes_analytics.py` (hazard), tests in `services/engine/tests/analytics/` |
| engine-handoff | `services/engine/understudy_engine/{routines,presence,memory}/**`, `routes_handoff.py` (onboarding, memory, coach/state, graph/work, routines, presence, offhours), tests in `services/engine/tests/handoff/` |
| engine-eval | `services/engine/understudy_engine/eval/**`, `services/engine/tests/eval/`, generated `evals/report.json` and `evals/report.md` |
| agent-core | `services/agent/understudy_agent/{supervisor.py,orchestrator.py,navigator.py,tiers/,completion.py,compile.py,shadow.py,offhours.py,server.py,sandbox_sites/}`, tests in `services/agent/tests/core/` |
| agent-safety | `services/agent/understudy_agent/{models/,security/,queue.py,audit.py}`, tests in `services/agent/tests/safety/` |
| desktop | `apps/desktop/**` |
| dashboard | `apps/dashboard/**` |
| platform | `extension/**`, `packages/schema/**` (except the lead's `event.schema.json` and `sensitive_fields.json`, which it may extend additively), `packages/packs/**`, `evals/**` |

Cross-track needs go through the lead (`CONTRACT-CHANGE:` or `NEED:` messages). Never edit another track's files. Do not touch `docs/**`, `Makefile`, root `pyproject.toml`, `package.json`, or `uv.lock` except via `uv add --package <your-package> <dep>` for your own package (retry if the lock is busy).

## Ports

Engine 7700, agent 7710, dashboard 5173, sandbox sites 7801 to 7803. Tests must use ephemeral ports or in-process clients. Use only the port of the service you own.

## Rules every agent follows

1. Read `CLAUDE.md`, `docs/SPEC_LIST.md` (section 0 and principles), the parts of `docs/IMPLEMENTATION_SPEC.md` for your modules, `docs/API_CONTRACT.md`, `docs/UI_DIRECTION.md` if you touch UI. Do not reopen locked decisions.
2. **No git add, commit or push.** The lead commits at checkpoints.
3. Never read, print, copy or log `.env` or any key. Load config via environment only; model IDs come from env. Never hard-code model names. Tests and demos run with `UNDERSTUDY_MOCK=1` and need no network.
4. Never run, install, build or import anything under `references/`. Read only. Re-implement ideas in your own words. Write the short `docs/reference-notes/<slug>.md` notes named in your brief (you may create those new files; touch no other file in `docs/`).
5. Never run a real desktop click or keystroke. Never run an agent against a real account. Sandbox sites and synthetic data only.
6. Tests for every pure module before wiring it (pytest / vitest). Run them. Honest results only: a failing test is reported as failing.
7. A hackathon: working and demonstrable beats rigorous. Cut scope before you cut tests of the P0 paths. Note shortcuts in your final report.
8. Look at any UI you build rendered (use `node scripts/shot.mjs <url> <out.png> [--w 1440 --h 900 --dark]` and read the PNG). Do not use the shared browser pane tools.

## Messaging protocol (use `SendMessage(to="main", ...)`; your plain text output is not seen by anyone)

- First message: your model ID, and that you have started.
- Progress: one short message at each milestone in your brief (what is done and verified, what is next, anything blocked). At least every ~45 minutes of work.
- Immediately: `BLOCKED:` (what you need and from whom), `NEED:` (a contract or file from another track), `CONTRACT-CHANGE:` (a shape you must change), `RISK:` (something that endangers a checkpoint).
- Final message: files created, tests run and results, what you verified by looking/running, shortcuts and known flaws, and what you would do next.
- The lead replies with `ACK`, answers, or new instructions. Act on lead messages promptly; they may re-prioritise using the cut lines.

## Timeline (Sat 7 Nov 2026, GMT)

Feature freeze **Sun 08:00**. Submission **Sun 12:00**, judging 12:30. Checkpoints: T+6 (about 20:30 Sat) ribbon and heatmap render from synthetic data; T+8 one household end to end; T+12 a planted routine goes from proposal to approved background run; freeze at 08:00.
