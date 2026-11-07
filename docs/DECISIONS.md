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
