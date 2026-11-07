import { DIRECTION_WORD, pct, type SkillRowView } from "./model";

const LEVEL_NAME = ["", "full", "small", "dot", "gone"];

/** One row per skill, in the pack's own words. Click a row to focus the curve on it. */
export function SkillRows({ rows, focusId, onFocus, levelPct, needed }: { rows: SkillRowView[]; focusId: string; onFocus: (id: string | null) => void; levelPct: number; needed: number }) {
  return (
    <>
      <ul className="gr-skills">
        {rows.map((r) => {
          const on = focusId === r.id;
          return (
            <li key={r.id}>
              <button type="button" className="gr-skill" aria-pressed={on} onClick={() => onFocus(on ? null : r.id)} aria-label={`${r.label}. ${on ? "Showing on the curve. Press to show everything." : "Press to show this skill on the curve."}`}>
                <span className="gr-skill__name">{r.label}</span>
                <span className="gr-skill__tags">
                  {r.level != null && <span className="pill gr-lvl" title={`Help level L${r.level}: ${LEVEL_NAME[r.level]}`}>help L{r.level} {LEVEL_NAME[r.level]}</span>}
                  {r.retrievalDue && (
                    <span className="pill gr-due" title="Practice due: next time this comes up, no cue is shown first. It only checks afterwards.">
                      <span className="gr-due__ring" aria-hidden="true" />practice due
                    </span>
                  )}
                  <span className="gr-skill__dir">{DIRECTION_WORD[r.direction]}</span>
                </span>
                <span className="gr-skill__bar" role="img" aria-label={`${r.independent} unaided, ${r.assisted} needed a cue, ${r.other} error or stopped, of ${r.n}`}>
                  {r.independent > 0 && <i className="gr-seg gr-seg--unaided" style={{ flexGrow: r.independent }} />}
                  {r.assisted > 0 && <i className="gr-seg gr-seg--assisted" style={{ flexGrow: r.assisted }} />}
                  {r.other > 0 && <i className="gr-seg gr-seg--other" style={{ flexGrow: r.other }} />}
                </span>
                <span className="gr-skill__count num">{r.independent} of {r.n} unaided {r.n >= needed && <span className="gr-skill__pct">({pct(r.unaidedShare)})</span>}</span>
                <span className="gr-skill__fact gr-skill__fact--ttp num">
                  <span className="gr-skill__k">After a cue</span>
                  <span className="gr-skill__v">
                    {r.ttp ? <>{Math.round(r.ttp.median)} s{r.ttp.ci ? <span className="gr-iv"> [{Math.round(r.ttp.ci[0])}, {Math.round(r.ttp.ci[1])}]</span> : null}<span className="gr-skill__n"> n {r.ttp.n}</span></> : <span className="gr-skill__none">no cues yet</span>}
                  </span>
                </span>
                <span className="gr-skill__fact gr-skill__fact--keep num">
                  <span className="gr-skill__k">Kept after days</span>
                  <span className="gr-skill__v">{r.retention && r.retention.value != null ? r.retention.text : <span className="gr-skill__none">not yet</span>}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <ul className="legend gr-legend" aria-label="How to read the rows">
        <li className="legend__item"><i className="gr-seg gr-seg--unaided gr-sw" />Finished with no cue accepted</li>
        <li className="legend__item"><i className="gr-seg gr-seg--assisted gr-sw" />Needed a cue</li>
        <li className="legend__item"><i className="gr-seg gr-seg--other gr-sw" />Error or stopped</li>
        <li className="legend__item">Time after a cue is the median seconds until progress, with its {levelPct}% interval.</li>
      </ul>
    </>
  );
}
