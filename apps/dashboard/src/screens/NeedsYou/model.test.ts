import { describe, expect, it } from "vitest";
import queueFx from "../../fixtures/queue.json";
import routinesFx from "../../fixtures/routines.json";
import briefingFx from "../../fixtures/briefing.json";
import agentsFx from "../../fixtures/agents-runs.json";
import type { AgentRun, BriefingCard, QueueItem, Routine } from "../../types";
import { firstLoadDone, fieldName, approvalClass, approvalLabels, awayLine, buildItems, consequence, isPausedRun, leadAndRest, neverLine, plainDuration, plainWords, routineName, sameRoutine, saveHint, saveLine, seenLine, touchesLead, visible, visibleItems } from "./model";

const queue = (queueFx as unknown as { data: QueueItem[] }).data;
const routines = (routinesFx as unknown as { data: Routine[] }).data;
const briefing = (briefingFx as unknown as { data: { generated_at: string; cards: BriefingCard[] } }).data;
const runs = (agentsFx as unknown as { data: AgentRun[] }).data;

const NOW_Q = Date.parse("2026-11-08T09:30:00Z");
const q = (over: Partial<QueueItem>): QueueItem => ({ ...queue[0], status: "pending", ...over });

describe("order: safety, then time-sensitive, then the rest, newest first inside a class", () => {
  it("puts an irreversible step before an outward step before a mismatch", () => {
    const items = buildItems({
      queue: [
        q({ id: "c", kind: "shadow_mismatch", risk_class: "normal", created_at: "2026-11-07T13:30:00Z" }),
        q({ id: "b", kind: "outward_step", risk_class: "outward", created_at: "2026-11-07T13:20:00Z" }),
        q({ id: "a", kind: "irreversible_step", risk_class: "irreversible", created_at: "2026-11-07T13:10:00Z" }),
      ],
    });
    expect(items.map((i) => i.key)).toEqual(["q:a", "q:b", "q:c"]);
    expect(items.map((i) => i.cls)).toEqual([0, 1, 2]);
  });

  it("puts a pause for safety first even when it is the oldest", () => {
    const items = buildItems({ queue: [q({ id: "new", kind: "batch_result", risk_class: "normal", created_at: "2026-11-07T15:00:00Z" }), q({ id: "old", kind: "injection_pause", risk_class: "normal", created_at: "2026-11-07T01:00:00Z" })] });
    expect(items[0].key).toBe("q:old");
  });

  it("is newest first inside one class and keeps the source order for ties", () => {
    const items = buildItems({ queue: [q({ id: "1", kind: "batch_result", risk_class: "normal", created_at: "2026-11-07T10:00:00Z" }), q({ id: "2", kind: "batch_result", risk_class: "normal", created_at: "2026-11-07T11:00:00Z" })] });
    expect(items.map((i) => i.key)).toEqual(["q:2", "q:1"]);
  });

  it("lists routine proposals and prepared actions after the dated decisions in their class", () => {
    const items = buildItems({ queue: queue.filter((x) => x.status === "pending"), routines, cards: briefing.cards, cardsAt: briefing.generated_at, runs });
    const kinds = items.map((i) => i.kind);
    expect(kinds.indexOf("approval")).toBe(0);
    expect(items.filter((i) => i.kind === "proposal")).toHaveLength(routines.filter((r) => r.status === "proposed").length);
    expect(items.every((it, i) => i === 0 || items[i - 1].cls <= it.cls)).toBe(true);
  });

  it("drops everything that is not waiting: decided items, routines already chosen, cards already pressed", () => {
    const items = buildItems({ queue: [q({ id: "x", status: "approved" })], routines: routines.map((r) => ({ ...r, status: "shadow" as const })), cards: briefing.cards.map((c) => ({ ...c, status: "fired" as const })) });
    expect(items).toHaveLength(0);
  });

  it("counts one number for the badge", () => {
    const items = buildItems({ queue: queue.filter((x) => x.status === "pending"), routines });
    expect(items.length).toBe(queue.filter((x) => x.status === "pending").length + routines.filter((r) => r.status === "proposed").length);
  });

  it("a source that has not loaded is simply absent", () => {
    expect(buildItems({})).toEqual([]);
    expect(buildItems({ queue: null, routines: null, cards: null, runs: null })).toEqual([]);
  });
});

describe("classes", () => {
  it("approvalClass", () => {
    expect(approvalClass({ kind: "irreversible_step", risk_class: "irreversible" })).toBe(0);
    expect(approvalClass({ kind: "injection_pause", risk_class: "normal" })).toBe(0);
    expect(approvalClass({ kind: "outward_step", risk_class: "outward" })).toBe(1);
    expect(approvalClass({ kind: "shadow_mismatch", risk_class: "normal" })).toBe(2);
  });
  it("a paused run is a decision a job waits on", () => {
    const r = { ...runs[0], state: "paused" };
    expect(isPausedRun(r)).toBe(true);
    expect(buildItems({ runs: [r] })[0].cls).toBe(1);
    expect(isPausedRun({ ...runs[0], state: "running", parent: { ...runs[0].parent, state: "running" } })).toBe(false);
  });
});

describe("the consequence is printed as plain words", () => {
  it("names an irreversible and an outward step, and says nothing for a normal one", () => {
    expect(consequence("irreversible")).toBe("Cannot be undone.");
    expect(consequence("outward")).toBe("Reaches outside.");
    expect(consequence("normal")).toBeNull();
  });
  it("keeps the irreversible-step label", () => {
    expect(approvalLabels("irreversible_step")).toEqual({ yes: "Approve and submit", no: "Reject" });
    expect(approvalLabels("outward_step").yes).toBe("Approve and send");
    expect(approvalLabels("shadow_mismatch")).toEqual({ yes: "Accept its answer", no: "Keep mine" });
  });
});

describe("words", () => {
  it("says practice, not shadow", () => {
    expect(plainWords("Shadow run disagreed with you on CN-2038")).toBe("Practice run disagreed with you on CN-2038");
    expect(plainWords("The shadow copy put £388 in the note.")).toBe("The practice copy put £388 in the note.");
  });
  it("never prints a rung code, the word rung or the old name", () => {
    expect(plainWords("The routine dropped one rung to A1.")).toBe("The routine dropped one step to watching.");
    expect(plainWords("Let Understudy enter households.")).toBe("Let Knack enter households.");
    expect(plainWords("Moved from A2 to A3")).toBe("Moved from asking first to running on its own");
    expect(plainWords("Hey Knack is off in demo mode")).toBe("Hey Knack is off in test mode");
    expect(plainWords("Demo household")).toBe("Test household");
  });
  it("keeps whole sentences within the word limit and moves the rest to the evidence", () => {
    const { lead, rest } = leadAndRest("One two three. Four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one twenty-two. Last one here.", 12);
    expect(lead).toBe("One two three.");
    expect(rest).toContain("Four five");
    expect(rest).toContain("Last one here.");
    const short = leadAndRest("The three calculators agree. The note is written, waiting for your click.", 24);
    expect(short.rest).toBe("");
  });
  it("always keeps the first sentence", () => {
    const long = Array.from({ length: 40 }, (_, i) => `w${i}`).join(" ") + ".";
    expect(leadAndRest(long, 10).lead).toBe(long);
  });
  it("builds the routine lines", () => {
    expect(seenLine("about 58 times in 3 weeks")).toBe("Seen about 58 times in 3 weeks.");
    expect(seenLine("Seen 3 times.")).toBe("Seen 3 times.");
    expect(saveLine({ value: { hours_saved: [3.1, 5.2], net_gbp: [41, 90], confidence: 0.8 } })).toBe("Could save 3.1 to 5.2 hours.");
    expect(saveLine({ value: { hours_saved: [4, 7], net_gbp: [1, 2], confidence: 0.8 } })).toBe("Could save 4 to 7 hours.");
    expect(saveHint({ value: { hours_saved: [4, 7], net_gbp: [41, 90], confidence: 0.8, horizon_weeks: 4 } })).toContain("95% interval over 4 weeks");
  });
  it("touches: names two and counts the rest, but prints three whole", () => {
    expect(touchesLead(["a", "b", "c"])).toEqual({ lead: "a, b, c", more: 0 });
    expect(touchesLead(["a", "b", "c", "d", "e"])).toEqual({ lead: "a, b", more: 3 });
  });
  it("prints what it will never do, whole", () => {
    expect(neverLine(["Submit the case note", "Send anything to a claimant", "Open sites you have not used in this routine"])).toBe("It will never submit the case note, send anything to a claimant or open sites you have not used in this routine.");
    expect(neverLine(["submit"])).toBe("It will never submit.");
    expect(neverLine([])).toBe("");
  });
  it("says what happened while the worker was away in one line", () => {
    expect(awayLine({ ran: [1], failed: [] })).toBe("Since you were away: 1 run finished, 0 failed.");
    expect(awayLine({ ran: [1, 2], failed: [1] })).toBe("Since you were away: 2 runs finished, 1 failed.");
    expect(awayLine({ ran: [], failed: [] })).toBeNull();
    expect(awayLine(null)).toBeNull();
  });
  it("Needs you shows three rows by default and every safety or blocking row besides", () => {
    const mk = (id: string, kind: QueueItem["kind"], risk: QueueItem["risk_class"], at: string) => q({ id, kind, risk_class: risk, created_at: at });
    const calm = buildItems({ queue: ["1", "2", "3", "4", "5"].map((n) => mk(n, "batch_result", "normal", `2026-11-07T1${n}:00:00Z`)) });
    expect(visibleItems(calm, false)).toHaveLength(3);
    expect(visibleItems(calm, true)).toHaveLength(5);
    const urgent = buildItems({ queue: ["a", "b", "c", "d", "e"].map((n, i) => mk(n, "irreversible_step", "irreversible", `2026-11-07T0${i}:00:00Z`)).concat([mk("z", "batch_result", "normal", "2026-11-07T09:00:00Z")]) });
    expect(visibleItems(urgent, false)).toHaveLength(5);                 // five safety rows: none is folded
    expect(visibleItems(urgent, false).every((i) => i.cls === 0)).toBe(true);
    expect(visibleItems([], false)).toEqual([]);
  });
  it("the first routine proposal is never folded, even when four approvals wait", () => {
    const four = ["a", "b", "c", "d"].map((n, i) => q({ id: n, kind: "irreversible_step", risk_class: "irreversible", created_at: `2026-11-07T0${i}:00:00Z` }));
    const items = buildItems({ queue: four, routines });
    const shown = visibleItems(items, false);
    expect(shown.filter((i) => i.cls === 0)).toHaveLength(4);
    expect(shown.some((i) => i.kind === "proposal")).toBe(true);
    expect(shown.filter((i) => i.kind === "proposal")).toHaveLength(1);                    // the first one only
    expect(visibleItems(items, true)).toHaveLength(items.length);
  });
  it("with room, the proposal replaces the last quiet row rather than adding a fourth", () => {
    const items = buildItems({ queue: [q({ id: "a", kind: "irreversible_step", risk_class: "irreversible" })].concat(["1", "2", "3"].map((n) => q({ id: n, kind: "batch_result", risk_class: "normal", created_at: `2026-11-07T1${n}:00:00Z` }))), routines });
    const shown = visibleItems(items, false);
    expect(shown).toHaveLength(3);
    expect(shown.at(-1)?.kind).toBe("proposal");
    expect(shown[0].key).toBe("q:a");
  });
  it("shows seven rows then all", () => {
    const rows = Array.from({ length: 10 }, (_, i) => i);
    expect(visible(rows, false)).toHaveLength(7);
    expect(visible(rows, true)).toHaveLength(10);
    expect(visible(rows.slice(0, 7), false)).toHaveLength(7);
  });
});

describe("tasks that wait for the worker", () => {
  const NOW = Date.parse("2026-11-08T09:30:00Z");
  const consent = { task_id: "tk_1", title: "Tidy", state: "waiting_consent" as const, started: "2026-11-08T09:00:00Z", needs_consent: { scope_text: "x" } };
  it("a consent card and a question are items; a running task with nothing to ask is not", () => {
    const items = buildItems({ tasks: [consent, { task_id: "tk_2", title: "Ask", state: "running" as const, started: "2026-11-08T09:10:00Z", question: { text: "Which?", options: [] } }, { task_id: "tk_3", title: "Busy", state: "running" as const, started: "2026-11-08T09:10:00Z" }], now: NOW });
    expect(items.map((i) => i.key).sort()).toEqual(["t:tk_1", "t:tk_2"]);
    expect(items).toHaveLength(2);
    expect(items.every((i) => i.kind === "task" && i.cls === 1)).toBe(true);
  });
  it("a finished task with an old question is not asked about again, and a duplicate id is one item", () => {
    expect(buildItems({ tasks: [{ task_id: "tk_9", title: "x", state: "done" as const, started: "2026-11-08T09:10:00Z", question: { text: "Which?", options: [] } }], now: NOW })).toHaveLength(0);
    expect(buildItems({ tasks: [consent, consent], now: NOW })).toHaveLength(1);
  });
  it("a card nobody answered for more than a day, and a run record a dead process left paused, are ghosts: not items", () => {
    const old = { ...consent, task_id: "tk_old", started: "2026-11-06T09:00:00Z" };
    expect(buildItems({ tasks: [old], now: NOW })).toHaveLength(0);
    const ghostRun = { run_id: "r_ghost", kind: "data.profile", mode: "foreground", state: "paused", started: "2026-11-05T09:00:00Z", parent: { id: "p", role: "planner", state: "paused", budget: {}, spent: {} }, children: [] };
    const freshRun = { ...ghostRun, run_id: "r_fresh", started: "2026-11-08T09:25:00Z" };
    expect(buildItems({ runs: [ghostRun, freshRun] as never, now: NOW }).map((i) => i.key)).toEqual(["a:r_fresh"]);
  });
});

describe("field names in the evidence read as words", () => {
  it("turns a key into a sentence-case label and never throws", () => {
    expect(fieldName("case_ref")).toBe("Case ref");
    expect(fieldName("calculators_agree")).toBe("Calculators agree");
    expect(fieldName("note-fields")).toBe("Note fields");
    expect(fieldName("")).toBe("");
    expect(fieldName(undefined as unknown as string)).toBe("");
  });
});

describe("the list is drawn only after every source has answered once", () => {
  it("waits while any source is still on its first load", () => {
    expect(firstLoadDone([{ data: [], status: "ready" }, { data: null, status: "loading" }])).toBe(false);
  });
  it("is done when every source has data, or has failed", () => {
    expect(firstLoadDone([{ data: [], status: "ready" }, { data: null, status: "error" }])).toBe(true);
  });
  it("stays done during a reload (the old data is kept)", () => {
    expect(firstLoadDone([{ data: [1], status: "loading" }])).toBe(true);
  });
});

describe("one routine is one row (QA Q1-08)", () => {
  const card = (title: string, id = "c1") => ({ id, kind: "automate", title, why: "You did these steps 14 times.", prepared: {}, risk_class: "normal", sources: [], expires_at: "", status: "ready" }) as never;
  const routine = (title: string, id = "r1") => ({ ...(routines.find((r) => r.status === "proposed") as Routine), id, title });
  it("a prepared 'Automate: X' beside the proposal 'X' is one row, the proposal's, and the card's reason travels with it", () => {
    const items = buildItems({ routines: [routine("Enter the household into three calculators")], cards: [card("Automate: Enter the household into three calculators")], now: NOW_Q });
    expect(items).toHaveLength(1);
    expect(items[0].kind).toBe("proposal");
    expect(items[0].kind === "proposal" && items[0].also?.id).toBe("c1");
  });
  it("sameRoutine ignores the lead-in, the case and extra spaces, and never matches an empty title", () => {
    expect(sameRoutine({ title: "automate:  Enter  the household" } as never, { title: "Enter the household" } as never)).toBe(true);
    expect(sameRoutine({ title: "Protect Wednesday morning for focus" } as never, { title: "Enter the household" } as never)).toBe(false);
    expect(sameRoutine({ title: "" } as never, { title: "" } as never)).toBe(false);
    expect(sameRoutine({} as never, {} as never)).toBe(false);
  });
  it("a prepared action about something else stays its own row, and a card with no twin is untouched", () => {
    const items = buildItems({ routines: [routine("Enter the household")], cards: [card("Protect Wednesday morning for focus")], now: NOW_Q });
    expect(items.map((i) => i.kind).sort()).toEqual(["prepared", "proposal"]);
  });
  it("two cards for one proposal do not become two rows: the second stays its own (only one twin is taken)", () => {
    const items = buildItems({ routines: [routine("Enter the household")], cards: [card("Automate: Enter the household", "c1"), card("Automate: Enter the household", "c2")], now: NOW_Q });
    expect(items.map((i) => i.kind).sort()).toEqual(["prepared", "proposal"]);
  });
});

describe("the away report in a worker's words (QA Q1-09)", () => {
  it("a routine id becomes a name, and a name with spaces is left alone", () => {
    expect(routineName("benefits-workflow")).toBe("Benefits workflow");
    expect(routineName("Copy the three results")).toBe("Copy the three results");
    expect(routineName(undefined)).toBe("A routine");
    expect(routineName("")).toBe("A routine");
  });
  it("minutes become words: under a minute, minutes, hours, days; nonsense is no duration", () => {
    expect(plainDuration(0.3)).toBe("under a minute");
    expect(plainDuration(1)).toBe("1 minute");
    expect(plainDuration(40)).toBe("40 minutes");
    expect(plainDuration(481.3)).toBe("8 hours");
    expect(plainDuration(60 * 24 * 3)).toBe("3 days");
    expect(plainDuration(-5)).toBeNull();
    expect(plainDuration(Number.NaN)).toBeNull();
    expect(plainDuration("481")).toBeNull();
  });
});

describe("a twin found by meaning (the fixture's own wording)", () => {
  const cardB02 = briefing.cards.find((c) => c.kind === "automate") as BriefingCard;
  it("'Let Knack enter households into the three calculators' (kind automate) is the twin of the proposal 'Enter the household into three calculators'", () => {
    const calc = routines.find((r) => r.id === "calc-entry-3x") as Routine;
    expect(sameRoutine(cardB02, calc)).toBe(true);
    const items = buildItems({ routines: [calc], cards: [cardB02], now: NOW_Q });
    expect(items).toHaveLength(1);
    expect(items[0].kind).toBe("proposal");
  });
  it("it is not the twin of a different routine, and a card that is not an 'automate' card is only matched by its exact title", () => {
    const rec = routines.find((r) => r.id === "reconcile-totals") as Routine;
    expect(sameRoutine(cardB02, rec)).toBe(false);
    expect(sameRoutine({ kind: "focus_block", title: "Let Knack enter households into the three calculators" }, routines.find((r) => r.id === "calc-entry-3x") as Routine)).toBe(false);
  });
  it("a title with fewer than three meaning words is never matched by meaning", () => {
    expect(sameRoutine({ kind: "automate", title: "Automate: Tidy up" }, { title: "Tidy up now" } as Routine)).toBe(false);
  });
});
