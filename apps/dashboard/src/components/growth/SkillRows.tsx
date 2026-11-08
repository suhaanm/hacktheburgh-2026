import { useState } from "react";
import { Row, Rows } from "../ui";
import type { IconName } from "../Icon";
import { DIRECTION_WORD, pct, type SkillRowView } from "./model";
import type { Direction } from "./wire";

const LEVEL_NAME = ["", "full", "small", "dot", "gone"];
/** Two words beside the arrow (the full phrase is the row's accessible name). "cannot tell" is never "no change": the interval includes zero. */
const ROW_WORD: Record<Direction, string> = { less_help: "less help", steady: "cannot tell", more_help: "more help", too_early: "too early" };
const TREND_ICON: Record<Direction, IconName> = { less_help: "up", steady: "flat", more_help: "down", too_early: "flat" };
/** How many skills show before "Show all N": two keeps the first screen inside 60 words at 1440 by 900 (KNACK_UX section 5). The spec ceiling is five. */
export const SKILLS_SHOWN = 2;

/**
 * One row per skill: a trend arrow, the skill's short name, three words. A row is a toggle: pressing it shows that skill alone on the curve
 * (the existing behaviour). The pressed row opens its own facts underneath, each with its n, so a number never stands without its count.
 */
export function SkillRows({ rows, focusId, onFocus, needed, limit = SKILLS_SHOWN }: { rows: SkillRowView[]; focusId: string; onFocus: (id: string | null) => void; levelPct: number; needed: number; limit?: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.filter((r, i) => i < limit || r.id === focusId);
  return (
    <>
      <Rows label="Skills">
        {shown.flatMap((r) => {
          const on = focusId === r.id;
          const row = (
            <Row
              key={r.id}
              title={r.name}
              icon={TREND_ICON[r.direction]}
              end={ROW_WORD[r.direction]}
              onClick={() => onFocus(on ? null : r.id)}
              pressed={on}
              chevron={false}
              label={`${r.name}, ${DIRECTION_WORD[r.direction]}. ${on ? "Showing on the curve. Press to show everything." : "Press to show this skill on the curve."}`}
            />
          );
          if (!on) return [row];
          return [row, <li key={`${r.id}-facts`} className="gr-skilldetail"><SkillFacts r={r} needed={needed} /></li>];
        })}
      </Rows>
      {rows.length > shown.length && <button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll(true)}>{`Show all ${rows.length}`}</button>}
      {all && rows.length > limit && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setAll(false)}>Show fewer</button>}
    </>
  );
}

/** What stands behind one skill's row: the counts, the time after a cue, what is kept after days, the help level. All printed, all with n. */
function SkillFacts({ r, needed }: { r: SkillRowView; needed: number }) {
  return (
    <div className="gr-facts">
      <span className="gr-skill__bar" role="img" aria-label={`${r.independent} unaided, ${r.assisted} needed a cue, ${r.other} error or stopped, of ${r.n}`}>
        {r.independent > 0 && <i className="gr-seg gr-seg--unaided" style={{ flexGrow: r.independent }} />}
        {r.assisted > 0 && <i className="gr-seg gr-seg--assisted" style={{ flexGrow: r.assisted }} />}
        {r.other > 0 && <i className="gr-seg gr-seg--other" style={{ flexGrow: r.other }} />}
      </span>
      <dl className="gr-facts__list num">
        <div><dt>Unaided</dt><dd>{r.independent} of {r.n}{r.n >= needed && <> ({pct(r.unaidedShare)})</>}</dd></div>
        <div><dt>Needed a cue</dt><dd>{r.assisted}{r.other > 0 ? `, error or stopped ${r.other}` : ""}</dd></div>
        <div>
          <dt>After a cue</dt>
          <dd>{r.ttp ? <>{Math.round(r.ttp.median)} s{r.ttp.ci ? <span className="gr-iv"> [{Math.round(r.ttp.ci[0])}, {Math.round(r.ttp.ci[1])}]</span> : null}<span className="gr-skill__n"> n {r.ttp.n}</span></> : "no cues yet"}</dd>
        </div>
        <div><dt>Kept after days</dt><dd>{r.retention && r.retention.value != null ? r.retention.text : "not yet"}</dd></div>
        {r.level != null && <div><dt>Help level</dt><dd>L{r.level}, {LEVEL_NAME[r.level]}</dd></div>}
        {r.retrievalDue && <div><dt>Practice due</dt><dd>The next cue is held back and only checks afterwards.</dd></div>}
      </dl>
      {r.recent && <p className="gr-facts__recent">{r.recent}</p>}
    </div>
  );
}
