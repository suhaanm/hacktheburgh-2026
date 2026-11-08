// Background tasks as a worker reads them: one line each (a task in plain words, one state, one short result or the one thing it needs), steps as a plain
// list on demand. No ids, no budgets, no counts the worker cannot act on: those are the admin's Background runs. Pure: no network, no React.
// The model of the list is how Claude Code shows its tasks: running first, finished ones fade after a minute into "Done today".
import { arr, clip, uniqueBy, validTime } from "./safeText";
import { childResults, kindLabel, stepsOf } from "./agents";
import type { AgentRun, TaskRow } from "../types";

export type TaskState = "running" | "waiting" | "done" | "stopped" | "failed";
export type StepState = "done" | "running" | "pending" | "failed";
export interface TaskStep { label: string; state: StepState }
export interface Task {
  id: string; title: string; state: TaskState;
  /** One short line: the result, or the one thing it needs. */
  note: string; steps: TaskStep[]; started: string | null;
  /** When it finished, if the service says (a task row does; a run does not). */
  finished: string | null;
  /** True for a task from the tasks service: it can be stopped and, when done, opened. */
  isTask: boolean;
  open: { kind: "folder" | "file" } | null;
  /** The full answer of a task that answered a question (a detail read; at most 1500 characters), else null. */
  answer: string | null;
}

const WAITING = new Set(["paused", "needs_human", "blocked"]);
const RUNNING = new Set(["running", "queued", "starting"]);
const DONE = new Set(["done", "completed", "unverified"]);
const STOPPED = new Set(["stopped", "revoked", "cancelled", "killed", "ended"]);
const FAILED = new Set(["failed", "error"]);

/** What the worker is told a state means. A state nobody knows is "done" only when nothing is still going; it is never shown as running by guess. */
export function taskState(run: AgentRun): TaskState {
  const states = [run?.state, run?.parent?.state, ...arr<{ state?: string }>(run?.children).map((c) => c?.state)].filter((s): s is string => typeof s === "string");
  if (states.some((s) => WAITING.has(s))) return "waiting";
  if (states.some((s) => RUNNING.has(s))) return "running";
  const own = typeof run?.state === "string" ? run.state : "";
  if (FAILED.has(own) || (!own && states.some((s) => FAILED.has(s)))) return "failed";
  if (STOPPED.has(own)) return "stopped";
  if (DONE.has(own)) return "done";
  return states.some((s) => FAILED.has(s)) ? "failed" : states.some((s) => STOPPED.has(s)) ? "stopped" : "done";
}

/** The task's name: the job in plain words, without the engine's "(long task)" tag. */
export const taskTitle = (run: AgentRun): string => clip(kindLabel(run?.kind).replace(/\s*\(long task\)\s*$/i, ""), 60) || "Background task";

const plainRole = (r: unknown): string => clip(typeof r === "string" ? r.replace(/[_.]/g, " ") : "", 40);
const childState = (s: unknown): StepState => (typeof s === "string" ? (s === "running" || s === "starting" ? "running" : DONE.has(s) ? "done" : FAILED.has(s) || STOPPED.has(s) ? "failed" : "pending") : "pending");   // queued and waiting are not started yet

/** The steps as a plain list: what the run's result lists once it has one, else the helpers it is using. */
export function taskSteps(run: AgentRun, result?: unknown): TaskStep[] {
  const listed = stepsOf(result);
  if (listed.length > 0) return listed.slice(0, 40).map((s) => ({ label: clip(s.label, 80), state: s.check === "failed" ? "failed" : "done" }));
  const fromResult = childResults(result).flatMap((c) => c.steps.map((s) => ({ label: clip(s.label, 80), state: (s.check === "failed" ? "failed" : "done") as StepState })));
  if (fromResult.length > 0) return fromResult.slice(0, 40);
  return arr<{ role?: string; state?: string }>(run?.children).slice(0, 40).map((c) => ({ label: plainRole(c?.role) || "A helper", state: childState(c?.state) }));
}

/** The one short line: what a finished task found (the result's own summary when it has one), what a running one is doing, or the one thing it needs. */
export function taskNote(run: AgentRun, state: TaskState, result?: unknown): string {
  switch (state) {
    case "running": {
      const doing = arr<{ role?: string; state?: string }>(run?.children).find((c) => c && typeof c.state === "string" && RUNNING.has(c.state));
      return doing && plainRole(doing.role) ? `Working on ${plainRole(doing.role)}.` : "Working.";
    }
    case "waiting": return "Needs you.";
    case "failed": return "Did not finish. Nothing was changed.";
    case "stopped": return "Stopped. Nothing was changed.";
    case "done": {
      const s = result && typeof result === "object" ? (result as { summary?: unknown }).summary : null;
      return typeof s === "string" && s.trim() ? clip(s, 120) : "Finished. Nothing needed from you.";
    }
  }
}

export function taskOf(run: AgentRun, result?: unknown): Task {
  const state = taskState(run);
  return { id: typeof run?.run_id === "string" ? run.run_id : "", title: taskTitle(run), state, note: taskNote(run, state, result), steps: taskSteps(run, result), started: typeof run?.started === "string" ? run.started : null, finished: null, isTask: false, open: null, answer: null };
}

/** The tasks of a list of runs: real runs only, each id once, newest first. */
export function tasksOf(runs: unknown, results: Record<string, unknown> = {}): Task[] {
  const rows = uniqueBy<AgentRun>(runs, (r, i) => (typeof r?.run_id === "string" && r.run_id ? r.run_id : `#${i}`));
  return rows.map((r, i) => ({ r, i })).sort((a, b) => (validTime(b.r.started) ?? -Infinity) - (validTime(a.r.started) ?? -Infinity) || a.i - b.i).map(({ r }) => taskOf(r, results[r.run_id]));
}

export const isFinished = (s: TaskState): boolean => s === "done" || s === "stopped" || s === "failed";

/** A finished task stays in the main list for this long, then moves to "Done today". */
export const FADE_MS = 60_000;

export interface Grouped { active: Task[]; recent: Task[]; today: Task[] }

/**
 * Running first, then ones that wait for the worker; a task that finished in the last minute stays beside them (so the worker sees it finish); the rest
 * of today's finished tasks are "Done today", collapsed. `finishedAt` is when this page saw a task finish (0 or absent: it was already finished when the
 * page loaded). A task that started on an earlier day is not listed here at all: it is in the admin's Background runs.
 */
export function groupTasks(tasks: Task[], finishedAt: ReadonlyMap<string, number>, now: number): Grouped {
  const active = [...tasks.filter((t) => t.state === "running"), ...tasks.filter((t) => t.state === "waiting")];
  const recent: Task[] = [], today: Task[] = [];
  const day = new Date(now).toDateString();
  for (const t of tasks) {
    if (!isFinished(t.state)) continue;
    const at = finishedAt.get(t.id) ?? validTime(t.finished) ?? 0;
    if (at > 0 && now - at < FADE_MS) { recent.push(t); continue; }
    const started = validTime(t.started);
    if (started === null || new Date(started).toDateString() === day) today.push(t);
  }
  return { active, recent, today };
}

/** Which tasks finished since the last look: they were running or waiting, and now are not. */
export function justFinished(before: ReadonlyMap<string, TaskState>, tasks: Task[]): Task[] {
  return tasks.filter((t) => isFinished(t.state) && (before.get(t.id) === "running" || before.get(t.id) === "waiting"));
}

/** One quiet sentence for a screen reader and the list: never one per task when several finish together. */
export function announcement(done: Task[]): string {
  if (done.length === 0) return "";
  if (done.length > 1) return `${done.length} tasks finished.`;
  const t = done[0];
  return t.state === "done" ? `${t.title} finished.` : t.state === "stopped" ? `${t.title} stopped.` : `${t.title} did not finish.`;
}

/* -- Rows from the tasks service (Track T, contract v1) ---------------------------------------------------------------------------------- */

const ROW_STATE: Record<string, TaskState> = { planning: "running", running: "running", waiting_consent: "waiting", done: "done", stopped: "stopped", failed: "failed" };

/** One row as the list shows it. A question makes a running task wait for the worker. The note is the current step while it runs, the one result line when done. */
export function taskFromRow(row: TaskRow, steps?: string[], answer?: string | null): Task {
  const asked = !!row?.question && typeof row.question.text === "string";
  let state: TaskState = ROW_STATE[row?.state as string] ?? "done";
  if (asked && state === "running") state = "waiting";
  const latest = clip(row?.latest, 100);
  const note =
    state === "waiting" ? (asked ? "Has a question." : "Needs your OK.") :
    state === "running" ? (row?.state === "planning" ? "Getting ready." : latest || "Working.") :
    state === "failed" ? clip(row?.reason, 120) || "Did not finish. Nothing was changed." :
    state === "stopped" ? "Stopped. Nothing was changed." :
    clip(row?.result, 140) || "Finished. Nothing needed from you.";
  const listed: TaskStep[] = arr<unknown>(steps).filter((x): x is string => typeof x === "string" && x.trim() !== "").slice(-40).map((x) => ({ label: clip(x, 100), state: "done" as const }));
  if (state === "running" && latest) listed.push({ label: latest, state: "running" });
  const open = row?.open && (row.open.kind === "folder" || row.open.kind === "file") ? { kind: row.open.kind } : null;
  return {
    id: typeof row?.task_id === "string" ? row.task_id : "", title: clip(row?.title, 60) || "A task", state, note, steps: listed,
    started: typeof row?.started === "string" ? row.started : null, finished: typeof row?.finished === "string" ? row.finished : null, isTask: true, open,
    answer: typeof answer === "string" && answer.trim() ? clip(answer, 1500) : null,
  };
}

/** The tasks of a list of rows: real rows only, each id once, newest first. `steps` are the plain step lines read for the rows the worker opened. */
export function tasksOfRows(rows: unknown, steps: Record<string, string[]> = {}, answers: Record<string, string | null> = {}): Task[] {
  const list = uniqueBy<TaskRow>(rows, (r, i) => (typeof r?.task_id === "string" && r.task_id ? r.task_id : `#${i}`));
  return list.map((r, i) => ({ r, i })).sort((a, b) => (validTime(b.r.started) ?? -Infinity) - (validTime(a.r.started) ?? -Infinity) || a.i - b.i).map(({ r }) => taskFromRow(r, steps[r.task_id], answers[r.task_id]));
}
