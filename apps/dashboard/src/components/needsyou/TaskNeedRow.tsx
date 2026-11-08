import { useState } from "react";
import { ApiError, api } from "../../api";
import { arr, clip } from "../../lib/safeText";
import { plainWords } from "../../screens/NeedsYou/model";
import type { TaskRow } from "../../types";
import { useToast } from "../Toasts";
import { Details } from "../ui";
import { Glyph } from "./Glyph";

const texts = (x: unknown, max = 60): string[] => arr<unknown>(x).filter((t): t is string => typeof t === "string" && t.trim() !== "").slice(0, 12).map((t) => clip(t, max));
const label = (x: unknown, fallback: string, max = 28): string => clip(x, max) || fallback;

/**
 * A task that waits for the worker: a consent card (what the task may do and what it may not, printed whole, then Allow or Decline, each a real click)
 * or a question with its options as buttons. The card's own words come from the tasks service and are shown as sent, cut only at a sane length. The
 * wider choice ("everything this task needs") sits behind More, never beside Allow. No key approves anything.
 */
export function TaskNeedRow({ row, onDone }: { row: TaskRow; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const c = row?.needs_consent ?? null;
  const q = row?.question && typeof row.question.text === "string" ? row.question : null;
  const id = typeof row?.task_id === "string" ? row.task_id : "";
  const title = plainWords(clip(row?.title, 60)) || "A task";
  const can = texts(c?.can), cannot = texts(c?.cannot);
  const limits = [c?.cost_note ? clip(c.cost_note, 120) : "", typeof c?.max_minutes === "number" && c.max_minutes > 0 ? `Stops after ${Math.round(c.max_minutes)} minutes.` : ""].filter(Boolean).join(" ");

  const go = async (what: string, fn: () => Promise<unknown>, done: string) => {
    setBusy(what); setErr(null);
    try { await fn(); toast({ tone: "success", text: done, detail: title }); onDone(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "That did not go through. Nothing was changed. Try again."); }
    finally { setBusy(null); }
  };
  const more = arr<{ id?: string; label?: string }>(c?.buttons?.more).filter((m) => m && m.id === "everything");

  return (
    <article className="kc-row" data-kind="task" data-cls="1" aria-labelledby={`ny-${id}`}>
      <h3 className="kc-row__title" id={`ny-${id}`}>
        <Glyph name="decision" />
        <span>{title}</span>
      </h3>
      {c ? (
        <>
          <p className="kc-row__body" data-testid="scope">{clip(c.scope_text, 240) || "This task needs your OK to go on."}</p>
          {can.length > 0 && <p className="kc-row__meta" data-testid="can">It can: {can.join(", ")}.</p>}
          {cannot.length > 0 && <p className="kc-row__meta" data-testid="cannot">It cannot: {cannot.join(", ")}.</p>}
          {limits && <p className="kc-row__meta">{limits}</p>}
          {err && <p className="kc-error" role="alert">{err}</p>}
          <div className="kc-row__actions" role="group" aria-label="Your choice">
            <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("allow", () => api.taskConsent(id, "allow"), "Allowed.")}>{busy === "allow" ? "Working" : label(c.buttons?.allow, "Allow")}</button>
            <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go("decline", () => api.taskConsent(id, "decline"), "Declined.")}>{busy === "decline" ? "Working" : label(c.buttons?.decline, "Not now")}</button>
          </div>
          {more.length > 0 && (
            <Details summary="More">
              <div className="row">
                {more.map((m) => <button key={m.id} type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => void go("everything", () => api.taskConsent(id, "everything"), "Allowed.")}>{label(m.label, "Allow everything", 60)}</button>)}
              </div>
            </Details>
          )}
        </>
      ) : q ? (
        <>
          <p className="kc-row__body" data-testid="question">{clip(q.text, 240)}</p>
          {err && <p className="kc-error" role="alert">{err}</p>}
          <div className="kc-row__actions" role="group" aria-label="Your answer">
            {arr<{ id?: string; label?: string }>(q.options).filter((o) => o && typeof o.id === "string" && o.id).slice(0, 4).map((o) => (
              <button key={o.id} type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void go(`a:${o.id}`, () => api.taskAnswer(id, o.id as string), "Answered.")}>{busy === `a:${o.id}` ? "Working" : label(o.label, "Choose")}</button>
            ))}
          </div>
        </>
      ) : null}
    </article>
  );
}
