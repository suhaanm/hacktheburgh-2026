import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { ErrorState, Loading, OriginBadge } from "../components/common";
import { cogLabel } from "../lib/format";
import type { CoachState } from "../types";

type Chip = CoachState["chip"];

const LEVEL: Record<CoachState["level"], { help: number; name: string; note: string }> = {
  L1: { help: 4, name: "full guidance", note: "I point at each step and say what it is." },
  L2: { help: 3, name: "hints", note: "I point at the step that matters and leave the rest to you." },
  L3: { help: 2, name: "nudges", note: "I speak up only when you seem stuck." },
  L4: { help: 1, name: "on your own", note: "I stay out of the way. Ask if you want me." },
};

export default function Today() {
  const c = useLoad(() => api.coach(), []);
  const [preview, setPreview] = useState<Chip | null>(null);
  const [stopped, setStopped] = useState(false);
  const [revived, setRevived] = useState(false);

  if (c.status === "error" && !c.data) return <div className="page"><ErrorState error={c.error} retry={c.reload} what="today's task" /></div>;
  if (!c.data) return <div className="page page--read"><Loading label="Loading today's task" /></div>;
  const d = c.data;
  const chip: Chip = revived && (preview ?? d.chip) === "dot" ? "small" : preview ?? d.chip;
  const lv = LEVEL[d.level];
  const mastery = Object.entries(d.mastery).sort((a, b) => a[1] - b[1]);

  return (
    <div className="page page--read">
      <section className="today" aria-labelledby="task-h">
        <div className="today__task">
          <div className="row row--between"><span className="t-label">Today · step {d.task.step} of {d.task.steps_total}</span><OriginBadge meta={c.meta} /></div>
          <h1 className="today__name" id="task-h">{d.task.name}</h1>
          <div className="today__steps" role="img" aria-label={`Step ${d.task.step} of ${d.task.steps_total}`}>
            {Array.from({ length: d.task.steps_total }, (_, i) => <i key={i} data-done={i + 1 < d.task.step} data-now={i + 1 === d.task.step} />)}
          </div>
        </div>

        <div className="today__say" aria-live="polite">
          {stopped ? (
            <>
              <p className="t-lede">Coaching is off for this task. Nothing is being recorded about what you do next.</p>
              <button type="button" className="btn btn--secondary" onClick={() => setStopped(false)}>Turn coaching back on</button>
            </>
          ) : (
            <>
              <div className="coach" data-state={chip} role={chip === "dot" ? "button" : undefined} tabIndex={chip === "dot" ? 0 : undefined} aria-label={chip === "dot" ? "Show the coach" : undefined}
                onClick={() => { if (chip === "dot") { setRevived(true); setPreview("small"); } }}
                onKeyDown={(e) => { if (chip === "dot" && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setRevived(true); setPreview("small"); } }}>
                <span className="coach__dot" />
                <div className="coach__body">
                  <div className="coach__title">{d.message}</div>
                  <div className="coach__more"><div><p>{lv.note}</p></div></div>
                </div>
              </div>
              {chip === "gone" && <p className="t-lede">The coach is quiet. It comes back if you get stuck, or after a break.</p>}
              {chip === "dot" && <p className="note">A dot is all that is left. Click it and the coach returns.</p>}
              <div className="today__meta">
                <span className="level" data-help={lv.help} title={`Level ${d.level}: ${lv.name}`}>
                  <span className="level__ticks" aria-hidden="true"><i /><i /><i /><i /></span>
                  {d.level}<span className="level__name">{lv.name}</span>
                </span>
                <details className="why">
                  <summary>Why this</summary>
                  <div className="why__body">{d.why}</div>
                </details>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => setStopped(true)}>Stop coaching</button>
              </div>
            </>
          )}
        </div>

        <div className="stack">
          <div className="row" role="group" aria-label="Preview how help fades">
            <span className="t-label">Preview how help fades</span>
            <div className="segmented">
              {(["full", "small", "dot", "gone"] as Chip[]).map((s) => (
                <button key={s} type="button" aria-pressed={(preview ?? d.chip) === s} onClick={() => { setRevived(false); setStopped(false); setPreview(s); }}>{s === "full" ? "Full" : s === "small" ? "Small" : s === "dot" ? "Dot" : "Gone"}</button>
              ))}
            </div>
          </div>
          <p className="note">As you master a step, help gets smaller, then a dot, then gone. After a long break it returns.</p>
        </div>

        <details className="details-lite">
          <summary>What you have mastered</summary>
          <div className="mastery">
            {mastery.map(([cog, m]) => (
              <div key={cog} className="mastery__row"><span>{cogLabel(cog)}</span><span className="mastery__track"><i style={{ width: `${m * 100}%` }} /></span><span className="tabular">{Math.round(m * 100)}</span></div>
            ))}
          </div>
        </details>
      </section>
    </div>
  );
}
