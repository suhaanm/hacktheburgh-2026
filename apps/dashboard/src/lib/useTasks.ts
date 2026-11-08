// The one place the background tasks list gets its data. When the tasks service answers (Track T, contract v1: GET /agent/tasks, its event stream at
// /agent/tasks/events) the list is the worker's own tasks, kept live by that stream. Until it does, the list is the agent service's run list
// (GET /agents/runs), polled. Everything below the hook (the list, the grouping, the announcements) is written against `Task` (lib/tasks.ts), so a
// change of source is a change in this file only.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AGENT_URL, api } from "../api";
import { idle, useLoad, type LoadState } from "../hooks";
import { useAppState } from "../store";
import type { AgentRun, TaskRow } from "../types";
import { runActive } from "./agents";
import { useLive, useRegisteredStreams } from "./live";
import { FADE_MS, announcement, groupTasks, isFinished, justFinished, tasksOf, tasksOfRows, type Grouped, type Task, type TaskState } from "./tasks";

export interface TasksView {
  /** Every task, newest first. Empty while the first answer is awaited. */
  tasks: Task[];
  grouped: Grouped;
  /** True once the first answer (live or the built-in sample) is in. */
  ready: boolean;
  /** The list could not be read at all and nothing was shown before. */
  failed: boolean;
  /** Anything is running or waiting now. */
  active: boolean;
  /** True when the tasks service is answering (a task can be stopped or opened); false while the run list stands in for it. */
  fromTasks: boolean;
  /** One quiet sentence about what just finished, for a screen reader and the list; "" when nothing did. It clears itself. */
  announce: string;
  /** The loads behind the list, for the Example data badge. */
  sources: LoadState<unknown>[];
  reload: () => void;
  /** Ask for a task's result and steps (they are read when a row is opened). */
  want: (id: string) => void;
  /** Stop a task, or open what it made. Each says so in its error if it could not. */
  stop: (id: string) => Promise<void>;
  openResult: (id: string) => Promise<void>;
}

const ANNOUNCE_MS = 5000;
const DETAILS_MAX = 8;
const TASKS_STREAM = `${AGENT_URL}/tasks/events`;

/**
 * The tasks list, kept fresh by itself: on the tasks service's event stream when it has one, every 2 s while a task runs and every 15 s otherwise, and at
 * once when the window comes back. `alsoReload` lets the screen refresh its own data on the same beat.
 */
export function useTasks(opts: { alsoReload?: () => void } = {}): TasksView {
  const me = useAppState().person ?? undefined;
  const tl = useLoad(() => api.tasks(), []);
  const fromTasks = tl.source === "live" && Array.isArray(tl.data);
  // Until the tasks service answers, the run list stands in for it (and is not asked for once it does).
  const runs = useLoad(() => (tl.source === "live" ? idle<AgentRun[]>() : api.agentsRuns(me)), [me, tl.source]);
  const [results, setResults] = useState<Record<string, unknown>>({});
  const [stepsBy, setStepsBy] = useState<Record<string, string[]>>({});
  const [answerBy, setAnswerBy] = useState<Record<string, string | null>>({});
  const [wanted, setWanted] = useState<string[]>([]);
  const asked = useRef(new Set<string>());
  const seen = useRef(new Map<string, TaskState>());
  const finishedAt = useRef(new Map<string, number>());
  const [announce, setAnnounce] = useState("");
  const [, bump] = useState(0);
  const alsoRef = useRef(opts.alsoReload);
  alsoRef.current = opts.alsoReload;

  const list = fromTasks ? (tl.data as TaskRow[]) : Array.isArray(runs.data) ? (runs.data as AgentRun[]) : null;
  const tasks = useMemo(() => (fromTasks ? tasksOfRows(list, stepsBy, answerBy) : tasksOf(list, results)), [fromTasks, list, results, stepsBy, answerBy]);
  const active = tasks.some((t) => t.state === "running" || t.state === "waiting") || (!fromTasks && !!(list as AgentRun[] | null)?.some((r) => { try { return runActive(r); } catch { return false; } }));
  const streams = useRegisteredStreams();
  const reload = useCallback(() => { tl.reload(); if (tl.source !== "live") runs.reload(); alsoRef.current?.(); }, [tl.reload, tl.source, runs.reload]);   // eslint-disable-line react-hooks/exhaustive-deps
  useLive(reload, active || streams.length > 0, streams, fromTasks ? [TASKS_STREAM] : []);

  // What finished since the last answer: stamp its time, say so once, and let it fade out of the main list after a minute.
  useEffect(() => {
    if (!list) return;
    const done = seen.current.size === 0 ? [] : justFinished(seen.current, tasks);
    const now = Date.now();
    for (const t of done) finishedAt.current.set(t.id, now);
    seen.current = new Map(tasks.map((t) => [t.id, t.state]));
    if (done.length === 0) return;
    setAnnounce(announcement(done));
    const clear = window.setTimeout(() => setAnnounce(""), ANNOUNCE_MS);
    const fade = window.setTimeout(() => bump((n) => n + 1), FADE_MS + 50);
    return () => { window.clearTimeout(clear); window.clearTimeout(fade); };
  }, [tasks, list]);

  // A run's result is read once, for the few finished ones that show and for any the worker opens (runs only: a task row carries its own result line).
  const finishedIds = fromTasks ? [] : tasks.filter((t) => isFinished(t.state)).slice(0, DETAILS_MAX).map((t) => t.id);
  const need = fromTasks ? [] : [...new Set([...finishedIds, ...wanted])].filter((id) => id && !asked.current.has(id));
  const needKey = need.join(",");
  useEffect(() => {
    if (!needKey) return;
    for (const id of needKey.split(",")) {
      asked.current.add(id);
      api.agentsRunDetail(id).then((r) => setResults((p) => ({ ...p, [id]: r.data?.result ?? null })), () => asked.current.delete(id));
    }
  }, [needKey]);

  // A task's steps are read for the rows the worker opened, and again on every refresh while that task runs.
  useEffect(() => {
    if (!fromTasks) return;
    for (const id of wanted) {
      const t = tasks.find((x) => x.id === id);
      if (!t || (asked.current.has(`s:${id}`) && t.state !== "running" && t.state !== "waiting")) continue;
      asked.current.add(`s:${id}`);
      api.taskDetail(id).then((r) => { const s = r.data?.steps; if (Array.isArray(s)) setStepsBy((p) => ({ ...p, [id]: s.filter((x): x is string => typeof x === "string") })); if (typeof r.data?.answer === "string") setAnswerBy((p) => ({ ...p, [id]: r.data?.answer ?? null })); }, () => asked.current.delete(`s:${id}`));
    }
  }, [fromTasks, wanted, list]);   // eslint-disable-line react-hooks/exhaustive-deps

  const want = useCallback((id: string) => setWanted((w) => (w.includes(id) ? w : [...w, id].slice(-20))), []);
  const stop = useCallback(async (id: string) => { await api.taskStop(id); reload(); }, [reload]);
  const openResult = useCallback(async (id: string) => { await api.taskOpen(id); }, []);
  const grouped = groupTasks(tasks, finishedAt.current, Date.now());
  return { tasks, grouped, ready: !!list, failed: tl.status === "error" && !tl.data && runs.status === "error" && !runs.data, active, fromTasks, announce, sources: [(fromTasks ? tl : runs) as LoadState<unknown>], reload, want, stop, openResult };
}
