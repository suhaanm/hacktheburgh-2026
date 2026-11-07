import { RUNGS, cleanRunsNeeded, nextRung } from "../lib/wilson";
import type { Routine } from "../types";

/** Autonomy rungs A0 to A3 with the Wilson lower bound that earns the next one. A3 is stated as a target the demo does not reach. */
export function Ladder({ routine }: { routine: Routine }) {
  const here = RUNGS.findIndex((r) => r.id === routine.rung);
  const { runs, matches, wilson_lower: lb } = routine.shadow;
  const next = nextRung(routine.rung);
  const need = next?.bound != null ? cleanRunsNeeded(matches, runs, next.bound) : null;
  const moreRuns = next?.runs != null ? Math.max(0, next.runs - runs) : 0;
  const extra = need != null ? Math.max(need, moreRuns) : null;
  return (
    <div className="stack">
      <ol className="ladder" aria-label={`Autonomy rung. This routine is at ${routine.rung}.`}>
        {RUNGS.map((r, i) => (
          <li key={r.id} className="ladder__step" data-reached={i <= here} data-here={i === here} data-target={r.id === "A3"} aria-current={i === here ? "step" : undefined}>
            <span className="ladder__id">{r.id}{i === here ? " · here" : ""}</span>
            <span className="ladder__name">{r.name}</span>
            <span className="ladder__does">{r.does}</span>
            {r.bound != null && <span className="ladder__need">needs bound ≥ {r.bound.toFixed(2)}{r.runs ? `, ${r.runs}+ runs` : ""}</span>}
          </li>
        ))}
      </ol>
      <div className="bound">
        <p className="note">
          Shadow record: <b className="tabular">{matches} of {runs}</b> runs matched you. Wilson lower bound <b className="tabular">{lb.toFixed(2)}</b> (95%).
          {next && extra != null && extra > 0 && <> To reach {next.id} it needs at least <b className="tabular">{extra}</b> more clean runs.</>}
          {next && extra === 0 && <> It meets the bound for {next.id}.</>}
        </p>
        <div className="bound__track" role="img" aria-label={`Lower bound ${lb.toFixed(2)}. A2 needs 0.80. A3 needs 0.95.`}>
          <span className="bound__fill" style={{ width: `${Math.min(100, lb * 100)}%` }} />
          <span className="bound__tick" style={{ left: "80%" }}><span>A2 0.80</span></span>
          <span className="bound__tick bound__tick--a3" style={{ left: "95%" }}><span>A3 0.95</span></span>
        </div>
        <p className="note" style={{ marginTop: "var(--space-5)" }}>A3 is a target. At 0.95 it would take about 75 clean runs, so the demo does not reach it. Any failure, quick undo or injection alert drops a routine one rung.</p>
      </div>
    </div>
  );
}
