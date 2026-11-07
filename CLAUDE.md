# Instructions for the build agent

You are the coding agent on the owner's build laptop. You will build **Understudy** for Hack the Burgh XIII. Submission is **Sunday 8 Nov 2026 12:00 GMT**; judging starts 12:30. Run `date` now and plan backwards.

## Read in this order

1. `docs/SPEC_LIST.md`, section 0 (locked decisions) and the principles. Do not reopen decisions. If one looks wrong, build it and note the concern in `docs/DECISIONS.md`.
2. `docs/IMPLEMENTATION_SPEC.md`: architecture, contracts, module specs, milestones, cut lines.
3. `docs/REFERENCES.md`: the ten reference projects and what to take from each.
4. `docs/UI_DIRECTION.md`: **our own good-looking, uncluttered, standout UI. Follow it.**
5. `docs/IDEA_BOARD.md`: what is committed, what is stretch, what is parked.
6. `docs/SPEC_LIST.md` section 14 and `docs/IMPLEMENTATION_SPEC.md` section 14: the extensions requested after kickoff (privacy and egress, local digests, plugins, calendar layer, proactive intelligence, background agents, git analysis). They are flagged off by default and never touch the P0 demo path. New owner requests are handled as in SPEC_LIST section 15.

## What you are building, in one paragraph

A system that watches how people work, shows where a novice loses time against an expert, coaches on the real screen with help that fades, and lets an agent do work for the person. A second layer finds repetitive routines, proposes automations that the worker opts into one at a time, and runs them in the background or while the worker is away. A memory file the worker owns adapts the system to them. It is generalised across job roles through role packs: one deep (UK benefits processor) and two thin (data analyst, programmer). Targets: HRT (predictions and decisions), G-Research (make the invisible visible), Wordsmith (complicated browser-use workflow).

## Rules

**Code and licences**
- The base is the owner's **local copy of Alongside**, at the path in `ALONGSIDE_PATH` (set it in `.env`). It is the owner's own code. Copy it into `apps/desktop` as described in the implementation spec. Keep `THIRD_PARTY_NOTICES.md` and every `Adapted from` header: they carry notices for code that is not the owner's.
- Run `scripts/clone-references.sh` once. It makes read-only local copies of the reference repos in `references/`. **Never run, install, build or import anything from `references/`.** Read only.
- Copy code only from the two MIT sources in `docs/REFERENCES.md` (clickyyy, VisionOS), with a header comment and a notice entry. For every other reference, **re-implement from the idea in your own words**. Do not paste or closely transcribe their code. Do not contact their authors.
- Write a short `docs/reference-notes/<slug>.md` for each reference before building the module it informs.

**Safety and privacy**
- Never commit `.env`, keys or personal data. Never print the API key.
- Logs and memory stay on the device. L0 capture stores no page text, no URLs, no field values. Never record fields listed in `packages/schema/sensitive_fields.json`.
- **No allowlists.** The agent may go anywhere. The worker keeps an optional denylist. The eight security layers in the implementation spec are mandatory, and mostly code, not model judgement.
- **The model proposes, code decides.** Levels, permissions, promotion, routing and gates are deterministic code.
- Every automation is opt-in. Irreversible actions during unattended runs need a per-routine opt-in by the worker.
- Do not run any real desktop click, keystroke or unattended run until spike S2 has passed with the owner present. Never run an agent against a real purchase. **Real accounts (owner decision D26, 7 Nov 2026):** the owner's own accounts (for example their Outlook calendar) may be read for a **read-only, aggregate-only** check, only after the owner approves that specific run in chat, only through the source plugin (never by pasting content into prompts or logs), and storing nothing but counts, durations and enums (no titles, attendees, bodies, names, paths or ids). Sending, posting, changing, accepting, deleting or any other write on a real account still needs the owner's approval for that single action, and unattended runs never write to real accounts. Everything else, including tests, demos and the study, uses the sandbox sites and synthetic data.

**Honesty**
- Every number has a baseline, a split and an interval. Synthetic results carry a badge. Say n = 4 for the live study. Do not claim that novices become experts; the claim is that the system lifts novices and shows its limits.
- Do not hard-code model names. Read them from the environment and check them at boot.

**UI**
- Follow `docs/UI_DIRECTION.md`. Our own look: calm, uncluttered, one idea per screen, nothing decorative. Look at every screen rendered, in light and dark, at 1440 by 900 and 390 by 844, before calling it done.

## How to work

1. **M0 first.** Environment check, spikes S1 to S4, references cloned, Alongside copied and running in mock mode. Record results in `docs/SPIKES.md`.
2. Work through the milestones M1 to M10 in the implementation spec. Keep a runnable demo at every checkpoint. If a checkpoint slips by more than an hour, apply the next cut in section 12 of the spec.
3. **Parallelise with subagents** where tracks are independent: engine analytics; dashboard; agent and desktop; extension, schemas and evals. One directory per subagent; no shared files. You own `docs/`, the Makefile and merges.
4. Write tests for every pure module before wiring it. Run the milestone smoke test before moving on.
5. Commit small and often. End every commit message with:
   `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
6. Push to `main` of this repo at every checkpoint so the owner can follow along.
7. Freeze features at deadline minus 4 hours (08:00 Sunday). After that, fix only what breaks the demo.
8. When you are blocked on a human-only task, stop and ask the owner. These are: granting macOS Accessibility and Screen Recording permissions, putting the API key in `.env`, running the live study with the four teammates, approving the first real-click spike, rehearsing and giving the demo, and submitting.

## Definition of done

- `make demo` runs the full three-minute demo path in mock mode with wifi off.
- `make eval` writes `evals/report.json` and the Evidence page renders it.
- Tests pass. No secrets in git. `THIRD_PARTY_NOTICES.md` is current.
- The README discloses that Alongside is the owner's earlier open-source library (first commit 31 Oct 2026) and lists what was reused.
- The UI passes the checklist at the end of `docs/UI_DIRECTION.md`.
