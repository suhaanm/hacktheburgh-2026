// Background tasks as a worker reads them: one line each, steps on demand, running first, finished ones fade into "Done today".
import { describe, expect, it } from "vitest";
import runsFx from "../fixtures/agents-runs.json";
import type { AgentRun, TaskRow } from "../types";
import { FADE_MS, announcement, groupTasks, isFinished, justFinished, taskFromRow, taskNote, taskOf, taskState, tasksOf, tasksOfRows, type Task, type TaskState } from "./tasks";

const runs = (runsFx as unknown as { data: AgentRun[] }).data;
const node = (state: string, role = "x") => ({ id: role, role, state, budget: {}, spent: {} });
const run = (over: Partial<AgentRun> & { state: string }, kids: [string, string][] = []): AgentRun => ({
  run_id: over.run_id ?? "r_1", kind: over.kind ?? "data.profile", mode: "foreground", started: over.started ?? "2026-11-08T09:00:00Z",
  state: over.state, parent: node(over.state, "planner"), children: kids.map(([role, state]) => node(state, role)),
});
const NOW = Date.parse("2026-11-08T10:00:00Z");
const task = (id: string, state: TaskState, started = "2026-11-08T09:00:00Z"): Task => ({ id, title: id, state, note: "", steps: [], started, finished: null, isTask: false, open: null, answer: null });

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
    expect(taskOf(r).steps).toEqual([{ label: "commit reader", state: "done" }, { label: "habit counter", state: "running" }, { label: "report writer", state: "running" }]);
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
  it("leaves out a finished task from an earlier day, and keeps one with no usable start time", () => {
    const g = groupTasks([task("yesterday", "done", "2026-11-07T08:00:00Z"), task("nostart", "done", "garbage")], new Map(), NOW);
    expect(g.today.map((t) => t.id)).toEqual(["nostart"]);
  });
  it("a running task from yesterday still shows: it is running", () => {
    const g = groupTasks([task("long", "running", "2026-11-05T08:00:00Z")], new Map(), NOW);
    expect(g.active.map((t) => t.id)).toEqual(["long"]);
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
