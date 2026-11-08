import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { ErrorState, Loading } from "../components/common";
import { cogLabel } from "../lib/format";
import { Details } from "../components/ui";
import type { AnalyticMeta, CoachDecision, CoachOutcome, CoachState } from "../types";

type Chip = CoachDecision["chip"];

const LEVEL: Record<CoachState["level"], { help: number; name: string; note: string }> = {
  L1: { help: 4, name: "full guidance", note: "I point at each step and say what it is." },
  L2: { help: 3, name: "hints", note: "I point at the step that matters and leave the rest to you." },
  L3: { help: 2, name: "nudges", note: "I speak up only when you seem stuck." },
  L4: { help: 1, name: "on your own", note: "I stay out of the way. Ask if you want me." },
};

/** When the study is on, the coach says nothing at all, not even a hint. */
const SILENCED = ["study_mode", "study_post_test", "study_off"];
export const isStudySilenced = (d: Pick<CoachDecision, "reason_codes"> | null): boolean => !!d && (d.reason_codes ?? []).some((c) => SILENCED.includes(c));

const POLL_MS = 3000;

/**
 * The coach decision, kept fresh while Today is open. The first look is passive (`dry`); after that it polls at a steady 3 s,
 * because each real poll advances the coach's dignity gate. Polling pauses while the tab is hidden, and stops when the engine is not live.
 */
function useDecision(person: string | undefined) {
  const [now, setNow] = useState<{ decision: CoachDecision; meta: AnalyticMeta | null; source: "live" | "demo" } | null>(null);
  useEffect(() => {
    if (!person) return;
    let stop = false, busy = false;
    let timer = 0;
    const pull = async (dry: boolean) => {
      if (stop || busy || (!dry && document.hidden)) return;
      busy = true;
      try {
        const r = await api.coachNext(person, dry);
        if (stop) return;
        setNow({ decision: r.data, meta: r.meta, source: r.source });
        if (r.source === "demo") window.clearInterval(timer); // nothing live to poll
      } catch { /* keep the last decision; the next poll tries again */ } finally { busy = false; }
    };
    void pull(true);
    timer = window.setInterval(() => void pull(false), POLL_MS);
    return () => { stop = true; window.clearInterval(timer); };
  }, [person]);
  return now;
}

const missedText = (m: unknown): string | null => {
  if (typeof m === "string") return cogLabel(m);
  if (m && typeof m === "object") { const o = m as Record<string, unknown>; const t = o.label ?? o.cog ?? o.step ?? o.name; return typeof t === "string" ? cogLabel(t) : null; }
  return null;
};

export default function Today() {
  const state = useLoad(() => api.coach(), []);
  const live = useDecision(state.data?.person);
  const [preview, setPreview] = useState<Chip | null>(null);
  const [stopped, setStopped] = useState(false);
  const [revived, setRevived] = useState(false);
  const [answered, setAnswered] = useState<Record<string, CoachOutcome>>({});
  const [fbErr, setFbErr] = useState<string | null>(null);
  const lastId = useRef<string | null>(null);

  useEffect(() => {
    // A new decision starts fresh: the dot closes again and any earlier error clears.
    const id = live?.decision.decision_id ?? null;
    if (id !== lastId.current) { lastId.current = id; setRevived(false); setFbErr(null); }
  }, [live?.decision.decision_id]);

  if (state.status === "error" && !state.data) return <div className="page"><ErrorState error={state.error} retry={state.reload} what="today's task" /></div>;
  if (!state.data) return <div className="page page--read"><Loading label="Loading today's task" /></div>;
  const s = state.data;
  // Before the first decision arrives (or with no engine id), fall back to the coach state so the screen is never blank.
  const d: CoachDecision = live?.decision ?? {
    action: s.message ? "nudge" : "silent", message: s.message, why: s.why, target: null, missed: [], confidence: 0, level: s.level, chip: s.chip, decision_id: null,
    task_id: s.task.id, step: s.task.step, trigger: null, reason_codes: [], gate: {}, p_stuck: null, p_source: null, candidate: null, mastery: s.mastery,
  };
  const silenced = isStudySilenced(d);
  const baseChip: Chip = d.chip;
  const shown: Chip = revived && (preview ?? baseChip) === "dot" ? "small" : preview ?? baseChip;
  const lv = LEVEL[d.level] ?? LEVEL.L4;
  const step = d.step ?? s.task.step;
  const mastery = Object.entries({ ...s.mastery, ...d.mastery }).sort((a, b) => a[1] - b[1]);
  const hasMessage = d.message.trim().length > 0;
  const outcome = d.decision_id ? answered[d.decision_id] : undefined;
  const missed = (d.missed ?? []).map(missedText).filter((x): x is string => !!x);
  const cand = d.candidate && d.candidate.message?.trim() ? d.candidate : null;

  const send = async (o: CoachOutcome) => {
    if (!d.decision_id) return;
    setFbErr(null);
    try { await api.coachFeedback(d.decision_id, o); setAnswered((a) => ({ ...a, [d.decision_id as string]: o })); }
    catch (e) { setFbErr(e instanceof Error ? e.message : "The coach could not be told. Try again."); }
  };

  return (
    <div className="page page--read">
      <section className="today" aria-labelledby="task-h">
        <div className="today__task">
          <div className="row row--between"><span className="t-label">Step {step} of {s.task.steps_total}{(s as { case?: number }).case ? ` · case ${(s as { case?: number }).case}` : ""}</span></div>
          <h1 className="today__name" id="task-h">{s.task.name}</h1>
          <div className="today__steps" role="img" aria-label={`Step ${step} of ${s.task.steps_total}`}>
            {Array.from({ length: s.task.steps_total }, (_, i) => <i key={i} data-done={i + 1 < step} data-now={i + 1 === step} />)}
          </div>
        </div>

        {silenced ? null : (
          <>
            <div className="today__say" aria-live="polite">
              {stopped ? (
                <>
                  <p className="t-lede">Coaching is off for this task. Nothing is being recorded about what you do next.</p>
                  <button type="button" className="btn btn--secondary" onClick={() => setStopped(false)}>Turn coaching back on</button>
                </>
              ) : (
                <>
                  {hasMessage && !outcome ? (
                    <div className="coach" data-state={shown} role={shown === "dot" ? "button" : undefined} tabIndex={shown === "dot" ? 0 : undefined} aria-label={shown === "dot" ? "Show the coach" : undefined}
                      onClick={() => { if (shown === "dot") { setRevived(true); setPreview("small"); } }}
                      onKeyDown={(e) => { if (shown === "dot" && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setRevived(true); setPreview("small"); } }}>
                      <span className="coach__dot" />
                      <div className="coach__body">
                        <div className="coach__title">{d.message}</div>
                        <div className="coach__more"><div><p>{lv.note}</p></div></div>
                      </div>
                    </div>
                  ) : outcome ? (
                    <p className="t-lede">{outcome === "followed" ? "Thanks. Noted that you did that." : "Dismissed. I will keep that in mind."}</p>
                  ) : (
                    <p className="t-lede">The coach is quiet right now.</p>
                  )}
                  {hasMessage && !outcome && shown === "dot" && <p className="note">A dot is all that is left. Click it and the coach returns.</p>}
                  {hasMessage && !outcome && d.target && (d.target.label_hint || d.target.zone) && (
                    <p className="note">Look for: <b>{d.target.label_hint ?? d.target.zone}</b>{d.target.role_hint ? ` (${d.target.role_hint})` : ""}{d.target.site ? ` on ${d.target.site}` : ""}.</p>
                  )}
                  {hasMessage && !outcome && d.decision_id && shown !== "dot" && (
                    <div className="row" role="group" aria-label="Tell the coach what you did">
                      {d.action !== "takeover_offer" && <button type="button" className="btn btn--secondary btn--sm" onClick={() => send("followed")}>I did that</button>}
                      <button type="button" className="btn btn--quiet btn--sm" onClick={() => send("dismissed")}>{d.action === "takeover_offer" ? "No thanks" : "Dismiss"}</button>
                    </div>
                  )}
                  {fbErr && <p className="field__error" role="alert">{fbErr}</p>}
                  {!hasMessage && cand && (
                    <div className="stack" style={{ gap: "var(--space-1)" }} data-testid="candidate">
                      <span className="t-label">What I would say</span>
                      <p className="note">{cand.message}</p>
                      {cand.why && <Details summary="Why this">{cand.why}</Details>}
                    </div>
                  )}
                  <div className="today__meta">
                    <span className="level" data-help={lv.help}>
                      <span className="level__ticks" aria-hidden="true"><i /><i /><i /><i /></span>
                      {d.level}<span className="level__name">{lv.name}</span>
                    </span>
                    {hasMessage && d.why && (
                      <Details summary="Why this">{d.why}{missed.length > 0 && <> Steps skipped so far: {missed.join(", ")}.</>}</Details>
                    )}
                    <button type="button" className="btn btn--secondary btn--sm" onClick={() => setStopped(true)}>Stop coaching</button>
                  </div>
                </>
              )}
            </div>

            <Details summary="Preview how help fades" wide>
              <div className="stack">
                <p className="note">As you master a step, help gets smaller, then a dot, then gone. After a long break it returns.</p>
                <div className="segmented" role="group" aria-label="Preview how help fades">
                  {(["full", "small", "dot", "gone"] as Chip[]).map((c) => (
                    <button key={c} type="button" aria-pressed={(preview ?? baseChip) === c} onClick={() => { setRevived(false); setStopped(false); setPreview(c); }}>{c === "full" ? "Full" : c === "small" ? "Small" : c === "dot" ? "Dot" : "Gone"}</button>
                  ))}
                </div>
              </div>
            </Details>

            <Details summary="How the coach decided" wide>
              <div className="stack">
                <ul className="plain-list">
                  {d.trigger && <li className="note">Trigger: {d.trigger.replace(/_/g, " ")}</li>}
                  {typeof d.p_stuck === "number" && <li className="note">Chance you are stuck: <b className="tabular">{Math.round(d.p_stuck * 100)}%</b>{d.p_source ? ` (${d.p_source})` : ""}</li>}
                  {d.gate?.reason && <li className="note">Dignity gate: {String(d.gate.reason).replace(/_/g, " ")}{typeof d.gate.consecutive === "number" ? `, ${d.gate.consecutive} stuck signal${d.gate.consecutive === 1 ? "" : "s"} in a row` : ""}</li>}
                  {d.reason_codes.length > 0 && <li className="note">Reasons: {d.reason_codes.map((c) => c.replace(/_/g, " ")).join(", ")}</li>}
                  <li className="note">Rule-based: no model call decides this. The expert policy, the dignity gate and your level do.</li>
                </ul>
              </div>
            </Details>

            <Details summary="What you have mastered" wide>
              <div className="mastery">
                {mastery.map(([cog, m]) => (
                  <div key={cog} className="mastery__row"><span>{cogLabel(cog)}</span><span className="mastery__track"><i style={{ width: `${m * 100}%` }} /></span><span className="tabular">{Math.round(m * 100)}</span></div>
                ))}
              </div>
            </Details>
          </>
        )}
      </section>
    </div>
  );
}
