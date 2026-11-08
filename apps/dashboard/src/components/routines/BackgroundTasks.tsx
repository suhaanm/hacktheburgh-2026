import { useState } from "react";
import { ApiError } from "../../api";
import { useTasks, type TasksView } from "../../lib/useTasks";
import type { Task, TaskState, TaskStep } from "../../lib/tasks";
import { Details } from "../ui";
import "../kc.css";
import "./tasks.css";

const WORD: Record<TaskState, string> = { running: "Running", waiting: "Needs you", done: "Done", stopped: "Stopped", failed: "Did not finish" };

/**
 * One icon: a spinner while it runs, a check when it is done, a dash when it stopped, a mark when it did not finish, a dot when it waits for the
 * worker. The shape carries the state (never colour alone) and the state word is read out. A spinner is a still ring under reduced motion.
 */
export function TaskIcon({ state }: { state: TaskState }) {
  return (
    <span className={`bt-icon bt-icon--${state}`} aria-hidden="true">
      {state === "running" ? <i className="bt-spin" /> : (
        <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" focusable="false">
          {state === "done" && <path d="M3.5 8.5 6.7 11.5 12.5 4.8" />}
          {state === "stopped" && <path d="M4 8h8" />}
          {state === "failed" && <path d="M5 5l6 6M11 5l-6 6" />}
          {state === "waiting" && <circle cx="8" cy="8" r="2.6" fill="currentColor" stroke="none" />}
        </svg>
      )}
    </span>
  );
}

const STEP_MARK: Record<TaskStep["state"], string> = { done: "✓", running: "…", pending: "·", failed: "✕" };

function Steps({ steps }: { steps: TaskStep[] }) {
  if (steps.length === 0) return <p className="kc-sub">No steps to show yet.</p>;
  return (
    <ul className="bt-steps" aria-label="Steps">
      {steps.map((s, i) => (
        <li key={`${i}-${s.label}`} data-state={s.state}><span className="bt-steps__mark" aria-hidden="true">{STEP_MARK[s.state]}</span><span>{s.label}</span><span className="u-sr-only"> ({s.state === "done" ? "done" : s.state === "failed" ? "did not work" : s.state === "running" ? "running" : "not started"})</span></li>
      ))}
    </ul>
  );
}

/** One task on one line; a click opens its steps in place. Nothing on the line is an id or a count. */
export function TaskRow({ task: t, open, onToggle, onStop, onOpenResult }: { task: Task; open: boolean; onToggle: () => void; onStop?: (id: string) => Promise<void>; onOpenResult?: (id: string) => Promise<void> }) {
  const [busy, setBusy] = useState<"stop" | "open" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (what: "stop" | "open", fn: (id: string) => Promise<void>, fallback: string) => {
    setBusy(what); setErr(null);
    try { await fn(t.id); } catch (e) { setErr(e instanceof ApiError ? e.message : fallback); } finally { setBusy(null); }
  };
  return (
    <li className="bt-task" data-state={t.state}>
      <div className="bt-line">
        <TaskIcon state={t.state} />
        <span className="bt-title">{t.title}<span className="u-sr-only">: {WORD[t.state]}.</span></span>
        <span className="bt-note">{t.note}</span>
        {/* The press target is a wordless button stretched over the line, so the line's words are not a button label. */}
        <button type="button" className="bt-open" aria-expanded={open} aria-controls={`bt-${t.id}`} aria-label={`${t.title}: ${WORD[t.state]}. ${open ? "Hide" : "Show"} the steps`} onClick={onToggle} />
      </div>
      {open && (
        <div className="bt-panel" id={`bt-${t.id}`}>
          {t.answer && <p className="bt-answer" data-testid="task-answer">{t.answer}</p>}
          {(t.steps.length > 0 || !t.answer) && <Steps steps={t.steps} />}
          {err && <p className="kc-error" role="alert">{err}</p>}
          {(t.state === "waiting" || (t.isTask && (t.state === "running" || (t.state === "done" && t.open)))) && (
            <div className="bt-actions">
              {t.state === "waiting" && <a className="kc-link" href="#/needs-you">Open Needs you<span aria-hidden="true"> ›</span></a>}
              {t.isTask && t.state === "running" && onStop && <button type="button" className="btn btn--secondary btn--sm" disabled={busy !== null} onClick={() => void run("stop", onStop, "Could not stop it. Try again.")}>{busy === "stop" ? "Stopping" : "Stop"}</button>}
              {t.isTask && t.state === "done" && t.open && onOpenResult && <button type="button" className="btn btn--secondary btn--sm" disabled={busy !== null} onClick={() => void run("open", onOpenResult, "Could not open it. Try again.")}>{busy === "open" ? "Opening" : t.open.kind === "folder" ? "Open folder" : "Open file"}</button>}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/**
 * The worker's background tasks, the way Claude Code shows its own: running first, one line each, steps on a click, and a finished task fades after a
 * minute into "Done today" (closed). It refreshes by itself (lib/useTasks), so a task that finishes in the background shows as finished with no
 * reload; a finish is a quiet check on the line and one polite sentence for a screen reader, never a toast. Shows nothing when there are no tasks.
 * Pass `view` to share one load with a screen that already holds it.
 */
export function BackgroundTasks({ limit = 4, view, alsoReload }: { limit?: number; view?: TasksView; alsoReload?: () => void }) {
  return view ? <TaskSection v={view} limit={limit} /> : <OwnTasks limit={limit} alsoReload={alsoReload} />;
}

/** The list with its own data (Home, anywhere that has not loaded the tasks itself). */
function OwnTasks({ limit, alsoReload }: { limit: number; alsoReload?: () => void }) {
  return <TaskSection v={useTasks({ alsoReload })} limit={limit} />;
}

export function TaskSection({ v, limit = 4 }: { v: TasksView; limit?: number }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const toggle = (t: Task) => { setOpenId((cur) => (cur === t.id ? null : t.id)); if (t.isTask || (t.state !== "running" && t.state !== "waiting")) v.want(t.id); };

  if (v.failed) return <p className="kc-sub" data-testid="tasks-error">Background tasks could not be read. <button type="button" className="kc-link" onClick={v.reload}>Try again</button></p>;
  const { active, recent, today } = v.grouped;
  const main = [...active, ...recent];
  if (main.length === 0 && today.length === 0) return <div className="u-sr-only" role="status" aria-live="polite" data-testid="tasks-live">{v.announce}</div>;
  const shown = main.slice(0, limit);
  return (
    <section className="bt" aria-label="Background tasks" data-testid="background-tasks">
      <h2 className="kc-label">Background tasks</h2>
      {shown.length > 0 && <ul className="bt-list">{shown.map((t) => <TaskRow key={t.id} task={t} open={openId === t.id} onToggle={() => toggle(t)} onStop={v.stop} onOpenResult={v.openResult} />)}</ul>}
      {main.length > shown.length && <p className="kc-sub">{main.length - shown.length} more running or just finished.</p>}
      {today.length > 0 && (
        <Details summary={`Done today (${today.length})`} className="bt-today">
          <ul className="bt-list">{today.slice(0, 20).map((t) => <TaskRow key={t.id} task={t} open={openId === t.id} onToggle={() => toggle(t)} onStop={v.stop} onOpenResult={v.openResult} />)}</ul>
        </Details>
      )}
      <div className="u-sr-only" role="status" aria-live="polite" data-testid="tasks-live">{v.announce}</div>
    </section>
  );
}
