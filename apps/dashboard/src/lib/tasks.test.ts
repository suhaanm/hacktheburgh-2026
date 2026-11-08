// Background tasks as a worker reads them: one line each, steps on demand, running first, finished ones fade into "Done today".
import { describe, expect, it } from "vitest";
import runsFx from "../fixtures/agents-runs.json";
import type { AgentRun, TaskRow } from "../types";
import { DAY_MS, FADE_MS, RUN_GHOST_MS, TASK_GHOST_MS, WAITING_GHOST_MS, anyActiveRow, anyActiveRun, announcement, dropStale, groupTasks, isFinished, isGhost, isGhostRow, isGhostRun, isOld, justFinished, pickTasks, taskFromRow, taskNote, taskOf, taskState, tasksOf, tasksOfRows, type Task, type TaskState } from "./tasks";

const runs = (runsFx as unknown as { data: AgentRun[] }).data;
const node = (state: string, role = "x") => ({ id: role, role, state, budget: {}, spent: {} });
const run = (over: Partial<AgentRun> & { state: string }, kids: [string, string][] = []): AgentRun => ({
  run_id: over.run_id ?? "r_1", kind: over.kind ?? "data.profile", mode: "foreground", started: over.started ?? "2026-11-08T09:00:00Z",
  state: over.state, parent: node(over.state, "planner"), children: kids.map(([role, state]) => node(state, role)),
});
const NOW = Date.parse("2026-11-08T10:00:00Z");
const task = (id: string, state: TaskState, started = new Date(NOW - 5 * 60_000).toISOString()): Task => ({ id, title: id, state, note: "", steps: [], started, finished: null, isTask: false, open: null, answer: null });

describe("a task's state", () => {
  it("maps the engine's states to five words", () => {
    expect(taskState(run({ state: "running" }))).toBe("running");
    expect(taskState(run({ state: "queued" }))).toBe("running");
    expect(taskState(run({ state: "paused" }))).toBe("waiting");
    expect(taskState(run({ state: "needs_human" }))).toBe("waiting");
    expect(taskState(run({ state: "done" }))).toBe("done");
    expect(taskState(run({ state: "completed" }))).toBe("done");
    expect(taskState(run({ state: "failed" }))).toBe("failed");
    expect(taskState(run({ state: "stopped" }))).toBe("stopped");
    expect(taskState(run({ state: "revoked" }))).toBe("stopped");
  });
  it("is running while any helper still runs, even when the run itself reads done", () => {
    expect(taskState(run({ state: "done" }, [["a", "done"], ["b", "running"]]))).toBe("running");
  });
  it("copes with a run that is missing its parts", () => {
    expect(taskState({ run_id: "x" } as unknown as AgentRun)).toBe("done");
    expect(taskState(null as unknown as AgentRun)).toBe("done");
  });
});

describe("a task's line", () => {
  it("is a title in plain words with no engine tag and no id", () => {
    const t = taskOf(run({ state: "running", kind: "programming.fix_bugs", run_id: "r_abc123" }, [["habit counter", "running"]]));
    expect(t.title).toBe("Bug fixer");
    expect(`${t.title} ${t.note}`).not.toMatch(/r_abc123|\(long task\)|\d+ of \d+/);
  });
  it("says what a running task is doing, what a waiting one needs, and that a stopped or failed one changed nothing", () => {
    expect(taskNote(run({ state: "running" }, [["commit reader", "done"], ["habit counter", "running"]]), "running")).toBe("Working on habit counter.");
    expect(taskNote(run({ state: "running" }), "running")).toBe("Working.");
    expect(taskNote(run({ state: "paused" }), "waiting")).toBe("Needs you.");
    expect(taskNote(run({ state: "stopped" }), "stopped")).toContain("Nothing was changed");
    expect(taskNote(run({ state: "failed" }), "failed")).toContain("Nothing was changed");
  });
  it("shows a finished task's own summary, cut short, else a plain finish", () => {
    expect(taskNote(run({ state: "done" }), "done", { summary: "Found 3 large commits and 2 without tests." })).toBe("Found 3 large commits and 2 without tests.");
    expect(taskNote(run({ state: "done" }), "done", { summary: "x".repeat(400) }).length).toBeLessThanOrEqual(121);
    expect(taskNote(run({ state: "done" }), "done")).toBe("Finished. Nothing needed from you.");
    expect(taskNote(run({ state: "done" }), "done", { summary: 42 })).toBe("Finished. Nothing needed from you.");
  });
  it("lists the helpers as the steps while the result is not in, and the result's own steps once it is", () => {
    const r = run({ state: "running" }, [["commit reader", "done"], ["habit counter", "running"], ["report writer", "queued"]]);
    expect(taskOf(r).steps).toEqual([{ label: "commit reader", state: "done" }, { label: "habit counter", state: "running" }, { label: "report writer", state: "pending" }]);
    const withResult = taskOf(r, { steps: [{ step: "open_file", check: "verified" }, { step: "copy_text", check: "failed" }] });
    expect(withResult.steps).toEqual([{ label: "open file", state: "done" }, { label: "copy text", state: "failed" }]);
  });
});

describe("the list", () => {
  it("is newest first, each id once, and tolerates holes", () => {
    const list = tasksOf([run({ run_id: "a", state: "done", started: "2026-11-08T08:00:00Z" }), null, run({ run_id: "b", state: "done", started: "2026-11-08T09:30:00Z" }), run({ run_id: "a", state: "failed" }), "oops", run({ run_id: "c", state: "done", started: "not a time" })]);
    expect(list.map((t) => t.id)).toEqual(["b", "a", "c"]);
    expect(tasksOf(undefined)).toEqual([]);
    expect(tasksOf("nope")).toEqual([]);
  });
  it("lists the example runs without throwing", () => {
    const list = tasksOf(runs);
    expect(list).toHaveLength(runs.length);
    expect(list.find((t) => t.id === "r_a01")!.state).toBe("running");
    expect(list.find((t) => t.id === "r_a03")!.state).toBe("failed");
  });
  it("puts running first, then waiting, keeps one that just finished beside them, and moves older finished ones to Done today", () => {
    const tasks = [task("old", "done"), task("fresh", "done"), task("wait", "waiting"), task("run", "running"), task("run2", "running")];
    const g = groupTasks(tasks, new Map([["fresh", NOW - 20_000], ["old", NOW - FADE_MS - 1]]), NOW);
    expect(g.active.map((t) => t.id)).toEqual(["run", "run2", "wait"]);
    expect(g.recent.map((t) => t.id)).toEqual(["fresh"]);
    expect(g.today.map((t) => t.id)).toEqual(["old"]);
  });
  it("a task already finished when the page loaded goes straight to Done today", () => {
    const g = groupTasks([task("a", "done")], new Map(), NOW);
    expect(g.recent).toEqual([]);
    expect(g.today.map((t) => t.id)).toEqual(["a"]);
  });
  it("leaves out a finished task created more than 24 hours ago, and one with no usable creation time; keeps one created 23 hours ago", () => {
    const g = groupTasks([task("old", "done", new Date(NOW - DAY_MS - 60_000).toISOString()), task("nostart", "done", "garbage"), task("fine", "done", new Date(NOW - 23 * 3_600_000).toISOString())], new Map(), NOW);
    expect(g.today.map((t) => t.id)).toEqual(["fine"]);
  });
  it("a task from earlier today that is still running (a task, not a ghost) shows", () => {
    const g = groupTasks([{ ...task("long", "running", new Date(NOW - 100 * 60_000).toISOString()), isTask: true }], new Map(), NOW);
    expect(g.active.map((t) => t.id)).toEqual(["long"]);
  });
});

describe("ghosts: a run or task that is not finished and cannot still be going", () => {
  const ago = (ms: number) => new Date(NOW - ms).toISOString();
  it("a run record still going after the 15 minutes the service allows is a ghost; at 14 minutes it is not", () => {
    expect(isGhost({ state: "running", started: ago(RUN_GHOST_MS + 1000), isTask: false }, NOW)).toBe(true);
    expect(isGhost({ state: "running", started: ago(RUN_GHOST_MS - 60_000), isTask: false }, NOW)).toBe(false);
  });
  it("the same for a run read raw: a paused or planning record from three days ago is a ghost", () => {
    expect(isGhostRun(run({ state: "planning", started: ago(3 * DAY_MS) }, [["x", "queued"]]), NOW)).toBe(true);
    expect(isGhostRun(run({ state: "paused", started: ago(3 * DAY_MS) }), NOW)).toBe(true);
    expect(isGhostRun(run({ state: "running", started: ago(60_000) }), NOW)).toBe(false);
  });
  it("a task row may run as long as its longest cap (120 minutes) plus a margin, and not a minute more", () => {
    expect(isGhostRow({ task_id: "t", title: "x", state: "running", started: ago(TASK_GHOST_MS - 60_000) }, NOW)).toBe(false);
    expect(isGhostRow({ task_id: "t", title: "x", state: "running", started: ago(TASK_GHOST_MS + 60_000) }, NOW)).toBe(true);
    expect(isGhostRow({ task_id: "t", title: "x", state: "planning", started: ago(3 * 3_600_000) }, NOW)).toBe(true);
  });
  it("a card that waits for the worker is a ghost after a day, not after a minute", () => {
    expect(isGhostRow({ task_id: "t", title: "x", state: "waiting_consent", started: ago(WAITING_GHOST_MS - 60_000), needs_consent: { scope_text: "x" } }, NOW)).toBe(false);
    expect(isGhostRow({ task_id: "t", title: "x", state: "waiting_consent", started: ago(WAITING_GHOST_MS + 60_000), needs_consent: { scope_text: "x" } }, NOW)).toBe(true);
  });
  it("something not finished with no usable start time is a ghost (nobody can vouch for it), and a finished one is never a ghost", () => {
    expect(isGhost({ state: "running", started: null, isTask: true }, NOW)).toBe(true);
    expect(isGhost({ state: "running", started: "garbage", isTask: false }, NOW)).toBe(true);
    expect(isGhost({ state: "done", started: null, isTask: false }, NOW)).toBe(false);
  });
  it("a start time ahead of the clock is a skewed clock, not a ghost", () => {
    expect(isGhost({ state: "running", started: new Date(NOW + 3_600_000).toISOString(), isTask: false }, NOW)).toBe(false);
  });
  it("a finished record created more than a day ago is old; at 23 hours it is not; unknown is old", () => {
    expect(isOld({ state: "done", started: ago(DAY_MS + 1000) }, NOW)).toBe(true);
    expect(isOld({ state: "done", started: ago(23 * 3_600_000) }, NOW)).toBe(false);
    expect(isOld({ state: "failed", started: null }, NOW)).toBe(true);
    expect(isOld({ state: "running", started: ago(5 * DAY_MS) }, NOW)).toBe(false);
  });
  it("a ghost is in none of the three lists, and an old record is in none", () => {
    const g = groupTasks([task("ghost", "running", ago(RUN_GHOST_MS + 60_000)), task("old", "done", ago(2 * DAY_MS)), task("real", "running")], new Map(), NOW);
    expect(g.active.map((t) => t.id)).toEqual(["real"]);
    expect(g.today).toEqual([]);
    expect(g.recent).toEqual([]);
  });
  it("what the screens ask again for: a ghost does not make a list 'active', a real run does", () => {
    expect(anyActiveRun([run({ state: "running", started: ago(3 * DAY_MS) })], NOW)).toBe(false);
    expect(anyActiveRun([run({ state: "running", started: ago(60_000) })], NOW)).toBe(true);
    expect(anyActiveRow([{ task_id: "t", title: "x", state: "running", started: ago(5 * 3_600_000) }], NOW)).toBe(false);
    expect(anyActiveRow([{ task_id: "t", title: "x", state: "running", started: ago(60_000) }], NOW)).toBe(true);
    expect(anyActiveRun(undefined, NOW)).toBe(false);
  });
  it("drops ghosts and old records but touches nothing else, in order", () => {
    const list = [task("a", "running"), task("g", "running", ago(RUN_GHOST_MS + 1000)), task("b", "done"), task("o", "stopped", ago(3 * DAY_MS))];
    expect(dropStale(list, NOW).map((t) => t.id)).toEqual(["a", "b"]);
  });
});

describe("what a list may hold: only what a service really answered", () => {
  const ago = (ms: number) => new Date(NOW - ms).toISOString();
  it("the built-in sample (rows and runs passed as null) is no task at all", () => {
    expect(pickTasks({ rows: null, runs: null }, NOW)).toEqual([]);
    expect(pickTasks({ rows: undefined, runs: "nope" }, NOW)).toEqual([]);
  });
  it("the example runs of the fixture, if a service had answered them today, are old history and a ghost: none is drawn", () => {
    expect(pickTasks({ rows: null, runs }, NOW)).toEqual([]);
  });
  it("rows win over runs, and a ghost row among real ones is dropped", () => {
    const t = pickTasks({ rows: [{ task_id: "a", title: "Real", state: "running", started: ago(60_000) }, { task_id: "g", title: "Ghost", state: "planning", started: ago(6 * 3_600_000) }], runs: [run({ state: "running", started: ago(30_000) })] }, NOW);
    expect(t.map((x) => x.id)).toEqual(["a"]);
  });
  it("with no rows, a real run that started a minute ago is a task", () => {
    expect(pickTasks({ rows: null, runs: [run({ run_id: "r_live", state: "running", started: ago(60_000) }, [["habit counter", "running"]])] }, NOW).map((x) => x.id)).toEqual(["r_live"]);
  });
});

describe("finishing", () => {
  it("notices a task that was running and now is not, once", () => {
    const before = new Map<string, TaskState>([["a", "running"], ["b", "done"], ["c", "waiting"]]);
    const now = [task("a", "done"), task("b", "done"), task("c", "stopped"), task("d", "failed")];
    expect(justFinished(before, now).map((t) => t.id)).toEqual(["a", "c"]);          // d was never seen running: it is not news
  });
  it("announces one quiet sentence, however many finished together", () => {
    expect(announcement([])).toBe("");
    expect(announcement([{ ...task("a", "done"), title: "Chart builder" }])).toBe("Chart builder finished.");
    expect(announcement([{ ...task("a", "stopped"), title: "Chart builder" }])).toBe("Chart builder stopped.");
    expect(announcement([{ ...task("a", "failed"), title: "Chart builder" }])).toBe("Chart builder did not finish.");
    expect(announcement([task("a", "done"), task("b", "done"), task("c", "done")])).toBe("3 tasks finished.");
  });
  it("knows which states are finished", () => {
    expect(["done", "stopped", "failed"].every((s) => isFinished(s as TaskState))).toBe(true);
    expect(["running", "waiting"].some((s) => isFinished(s as TaskState))).toBe(false);
  });
});

describe("rows from the tasks service", () => {
  const row = (over: Partial<TaskRow> & { state: TaskRow["state"] }): TaskRow => ({ task_id: "tk_8f3a1c2e", title: "Tidy the invoices folder", started: "2026-11-08T09:00:00Z", ...over });
  it("maps the six states to five words, and a planning task is running", () => {
    expect(taskFromRow(row({ state: "planning" })).state).toBe("running");
    expect(taskFromRow(row({ state: "running" })).state).toBe("running");
    expect(taskFromRow(row({ state: "waiting_consent" })).state).toBe("waiting");
    expect(["done", "stopped", "failed"].map((s) => taskFromRow(row({ state: s as TaskRow["state"] })).state)).toEqual(["done", "stopped", "failed"]);
  });
  it("shows the current step while it runs and the one result line when done, never the id", () => {
    expect(taskFromRow(row({ state: "running", latest: "Reading invoices.pdf" })).note).toBe("Reading invoices.pdf");
    expect(taskFromRow(row({ state: "planning" })).note).toBe("Getting ready.");
    expect(taskFromRow(row({ state: "running" })).note).toBe("Working.");
    expect(taskFromRow(row({ state: "done", result: "Moved 12 files into Paid and Unpaid." })).note).toBe("Moved 12 files into Paid and Unpaid.");
    expect(taskFromRow(row({ state: "done" })).note).toBe("Finished. Nothing needed from you.");
    expect(`${taskFromRow(row({ state: "done" })).title} ${taskFromRow(row({ state: "done" })).note}`).not.toMatch(/tk_8f3a1c2e/);
  });
  it("says what failed in the service's own reason, and that nothing was changed when it gave none", () => {
    expect(taskFromRow(row({ state: "failed", reason: "The folder was not found." })).note).toBe("The folder was not found.");
    expect(taskFromRow(row({ state: "failed" })).note).toContain("Nothing was changed");
  });
  it("a question makes a running task wait for the worker, and a consent card waits for them too", () => {
    expect(taskFromRow(row({ state: "running", question: { text: "Which folder?", options: [] } })).state).toBe("waiting");
    expect(taskFromRow(row({ state: "running", question: { text: "Which folder?", options: [] } })).note).toBe("Has a question.");
    expect(taskFromRow(row({ state: "waiting_consent", needs_consent: { scope_text: "x" } })).note).toBe("Needs your OK.");
  });
  it("lists the plain step lines it was given as done, with the current one running last", () => {
    const t = taskFromRow(row({ state: "running", latest: "Moving files" }), ["Listed the folder", "Read 12 files"]);
    expect(t.steps).toEqual([{ label: "Listed the folder", state: "done" }, { label: "Read 12 files", state: "done" }, { label: "Moving files", state: "running" }]);
    expect(taskFromRow(row({ state: "done" }), ["a", 7 as unknown as string, ""]).steps).toEqual([{ label: "a", state: "done" }]);
  });
  it("keeps what the service says about opening the result, as a kind and no path", () => {
    expect(taskFromRow(row({ state: "done", open: { kind: "folder", path: "/Users/x/Invoices" } })).open).toEqual({ kind: "folder" });
    expect(taskFromRow(row({ state: "done", open: { kind: "weird" as "file", path: "x" } })).open).toBeNull();
  });
  it("uses the service's own finish time: a task that finished 20 s ago stays in the main list with no observation needed", () => {
    const t = taskFromRow(row({ state: "done", finished: new Date(NOW - 20_000).toISOString() }));
    expect(groupTasks([t], new Map(), NOW).recent.map((x) => x.id)).toEqual([t.id]);
    const old = taskFromRow(row({ state: "done", finished: new Date(NOW - 5 * 60_000).toISOString() }));
    expect(groupTasks([old], new Map(), NOW).today.map((x) => x.id)).toEqual([old.id]);
  });
  it("is newest first, each id once, and tolerates holes, long titles and missing fields", () => {
    const list = tasksOfRows([row({ task_id: "a", state: "done", started: "2026-11-08T08:00:00Z" }), null, row({ task_id: "b", state: "running", started: "2026-11-08T09:30:00Z" }), row({ task_id: "a", state: "failed" }), { task_id: "c", state: "done", title: "T".repeat(300) }, "oops"]);
    expect(list.map((x) => x.id)).toEqual(["b", "a", "c"]);
    expect(list.find((x) => x.id === "c")!.title.length).toBeLessThanOrEqual(60);
    expect(tasksOfRows(undefined)).toEqual([]);
    expect(taskFromRow({} as TaskRow).title).toBe("A task");
  });
  it("keeps the full answer a detail read returned, cut at 1500 characters, and none for a task that gave none", () => {
    expect(taskFromRow(row({ state: "done", route: "answer" }), [], "Paris.").answer).toBe("Paris.");
    expect(Array.from(taskFromRow(row({ state: "done" }), [], "x".repeat(4000)).answer ?? "").length).toBeLessThanOrEqual(1500);
    expect(taskFromRow(row({ state: "done" }), [], "  ").answer).toBeNull();
    expect(taskFromRow(row({ state: "done" })).answer).toBeNull();
  });
});
