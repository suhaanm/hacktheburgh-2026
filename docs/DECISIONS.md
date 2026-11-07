# Decisions and concerns

Running log. The locked decisions are in [SPEC_LIST.md](SPEC_LIST.md) section 0 and are not reopened. Add dated entries below as you build.

## Concerns from the planner (as of Sat 7 Nov 2026, 14:00 GMT)

These do not block the plan. They explain where the cut lines come from.

1. **Scope is large for about 21 hours.** The owner chose generalised role packs, the full Handoff slice early, a live off-hours run, and both graphs. The spec keeps a runnable demo at every checkpoint and gives an ordered list of cuts (section 12 of the implementation spec). Apply them early rather than late.
2. **Desktop control is unproven.** Alongside's click loop has never executed a real click. Spike S2 decides whether the off-hours run is real or simulated.
3. **OpenAI computer use is unverified.** The research found a computer tool in the Responses API, but model IDs and the response shape were not called. Spike S1 settles it.
4. **Alongside depends on Gemini** for grounding, verification and voice. The model port replaces those calls with OpenAI. Voice stays off.
5. **Evidence is thin by design.** History is synthetic plus the machine's own timestamps, and the live study has four people. Every chart says so. The claim is that the pipeline recovers planted structure and shows its limits, not that real people behave this way.
6. **Reuse and event rules.** Alongside's first commit is 31 Oct, before this event. The owner decided to use the local copy. The README disclosure is mandatory.
7. **PolicyEngine UK is a reference model, not law.** Hand-check about 20 cases and say so.
8. **The "$15 an hour" figure** comes from Y Combinator's Winter 2027 request "The $15-an-Hour Expert". Use it as an illustration of the wage, with a citation.

## Build log

_Add entries here: date and time, what changed, why, and any concern raised._

**Sat 7 Nov, 14:19 to 15:00 GMT (lead).**
- Build started 14:19 GMT (about 21h40m to submission, 17h40m to the 08:00 freeze). Spec, UI direction and the prize PDF read.
- **ALONGSIDE_PATH** is `/Users/suhaan/Desktop/hackathon/deepmind-hackathon` (the owner's own repo `suhaanm/deepmind-hackathon`, first commit 2026-10-31; five uncommitted files in `apps/demo-stage` and `docs/DEMO_SCRIPT_INTERACTIVE.md` at copy time). Copied into `apps/desktop` with the spec's exclusions plus `out/`, `media/` and `.env*` (not code; large). Secret scan of the copy found nothing.
- **Models (spike S1):** planner `gpt-5.5`, fast `gpt-5.4-mini`, computer use `gpt-5.5`; the computer tool works with `{"type":"computer"}` on several models. See `docs/SPIKES.md`.
- **Orchestration:** nine parallel Claude Sonnet 5.5 agents (design, engine-data, engine-analytics, engine-handoff, dashboard, agent-core, agent-safety, desktop, platform), one writer per directory, the lead commits and pushes. Roster, ownership and messaging protocol are in `docs/AGENTS.md`; the cross-track data contract is `docs/API_CONTRACT.md`. The spec's four tracks were split further because engine and agent are each too large for one agent.
- **Concern:** the `bandit` and `okidoki` reference repos could not be cloned (private, deleted or 404). Notes for them come from `docs/REFERENCES.md` and the Devpost descriptions only.
- **Concern:** the UI plan artifact linked in `UI_DIRECTION.md` lives in another claude.ai organisation and could not be read from this session. The tokens in `UI_DIRECTION.md` were used as the starting point.
- **Prize PDF (HackTheBurgh dashboard, 7 Nov):** challenges: Metaview (no brief), HRT (best use of data for predictions and decision making), G-Research (make the invisible visible), JetBrains (help the developer), Bank of Scotland (smart cost of living), Wordsmith (most complicated end-to-end agentic browser-use workflow), InstaLILY (a coding agent that adapts to whoever is using it), Viridien (lithology). MLH has 8 categories: Gemini API, ElevenLabs, Entire, Solana, Tiger Data, Vultr, DEV Writing Challenge, Auth0. Our locked targets stay HRT, G-Research and Wordsmith (D2).
