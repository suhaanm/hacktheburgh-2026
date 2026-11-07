import { useId, useMemo, useState } from "react";
import { useLoad } from "../../hooks";
import { Loading } from "../common";
import { Details } from "../ui";
import { PolarityGlyph, lookOfPolarity } from "../home/PolarityGlyph";
import { loadDrill } from "../../screens/Firm/data";
import { nWord } from "./Badges";
import { LineBand, ticksFor } from "./LineBand";
import { drillTable, effectText, pct } from "./model";
import type { AdminInsight, WireDrill } from "./wire";

/** Where an insight's action goes. The Firm screen's views are sub-routes (#/firm/roles); other screens take a query. */
export const actionHref = (a: NonNullable<AdminInsight["action"]>): string => (a.to === "firm" ? `#/firm${a.query ? `/${a.query}` : ""}` : `#/${a.to}${a.query ? `?${a.query}` : ""}`);

/** The granular numbers behind one insight, printed: a table with its intervals and n, a series with its band when there is one, and the method. */
function DrillBody({ d }: { d: WireDrill }) {
  const main = useMemo(() => drillTable(d.columns, d.rows), [d]);
  const more = useMemo(() => d.tables.map((t) => ({ id: t.id, title: t.title, view: drillTable(t.columns, t.rows) })), [d]);
  const [all, setAll] = useState(false);
  const rows = all ? main.rows : main.rows.slice(0, 7);
  const share = d.series.every((s) => s.points.every((p) => p.y >= 0 && p.y <= 1.0001 && (p.hi ?? 0) <= 1.0001));
  const pts = d.series.flatMap((s) => s.points);
  const xDomain: [number, number] = pts.length ? [Math.min(...pts.map((p) => p.x)), Math.max(...pts.map((p) => p.x))] : [0, 1];
  const weekly = pts.length > 0 && pts.every((p) => p.x <= 0 && Number.isInteger(p.x));
  return (
    <div className="drill">
      {main.rows.length > 0 && (
        <div className="table-wrap">
          <table className="table drill__table">
            <thead><tr><th scope="col">What</th>{main.heads.map((h) => <th key={h.key} scope="col" className="num">{h.label}</th>)}<th scope="col" className="num">n</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}><th scope="row">{r.label}</th>{r.cells.map((c, i) => <td key={i} className="num">{c}</td>)}<td className="num">{r.n ?? ""}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {main.rows.length > 7 && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setAll((a) => !a)}>{all ? "Show fewer" : `Show all ${main.rows.length}`}</button>}
      {more.map((t) => (
        <div key={t.id} className="drill__more">
          <h4 className="t-label">{t.title}</h4>
          <div className="table-wrap">
            <table className="table drill__table">
              <thead><tr><th scope="col">What</th>{t.view.heads.map((h) => <th key={h.key} scope="col" className="num">{h.label}</th>)}<th scope="col" className="num">n</th></tr></thead>
              <tbody>{t.view.rows.map((r) => <tr key={r.label}><th scope="row">{r.label}</th>{r.cells.map((c, i) => <td key={i} className="num">{c}</td>)}<td className="num">{r.n ?? ""}</td></tr>)}</tbody>
            </table>
          </div>
        </div>
      ))}
      {d.series.map((s) => (
        <figure key={s.label} className="chart drill__chart">
          <figcaption className="chart__title">{s.label}</figcaption>
          <LineBand
            title={s.label} points={s.points}
            xDomain={xDomain} yDomain={share ? [0, 1] : [Math.min(0, ...s.points.map((p) => p.lo ?? p.y)), Math.max(...s.points.map((p) => p.hi ?? p.y)) * 1.05]}
            xTicks={ticksFor(xDomain, 6)} yTicks={share ? [0, 0.25, 0.5, 0.75, 1] : ticksFor([0, Math.max(...s.points.map((p) => p.hi ?? p.y))], 4)}
            formatX={(v) => String(v)} formatY={(v) => (share ? pct(v) : String(Math.round(v * 10) / 10))}
            xLabel={weekly ? "Week (0 is the latest)" : undefined} height={200}
          />
        </figure>
      ))}
      {(d.notes.length > 0 || d.method) && (
        <Details summary="How this was worked out">
          {d.method && <p>{d.method}</p>}
          {d.notes.map((n) => <p key={n}>{n}</p>)}
        </Details>
      )}
    </div>
  );
}

function Drill({ insight }: { insight: AdminInsight }) {
  const q = useLoad(() => loadDrill(insight.drill, insight), [insight.drill]);
  if (q.status === "error" && !q.data) return <p className="drill__state" role="alert">The breakdown could not be loaded. {q.error.message}</p>;
  if (!q.data) return <Loading label="Loading the numbers" />;
  return <DrillBody d={q.data} />;
}

/** One insight, printed for an admin: the headline, its effect with the interval, n and origin, and the numbers behind it one click away. */
function InsightRow({ i, open, onToggle }: { i: AdminInsight; open: boolean; onToggle: () => void }) {
  const id = useId();
  const effect = effectText(i.effect);
  return (
    <li>
      <article className="insight firm-insight" data-polarity={lookOfPolarity(i.polarity)} aria-label={i.a11y_label ?? i.headline}>
        <PolarityGlyph look={lookOfPolarity(i.polarity)} />
        <div className="insight__head">
          <span className="insight__label">{i.polarity_label ?? "Note"}</span>
          <h3 className="insight__title">{i.headline}</h3>
        </div>
        <div className="insight__action">
          <button type="button" className="btn btn--secondary btn--sm" aria-expanded={open} aria-controls={id} onClick={onToggle}>{open ? "Hide the numbers" : "Open the numbers"}</button>
        </div>
        <p className="insight__stats">
          {effect && <><b>{effect}</b> · </>}
          n = <b>{nWord(i.n, i.n_unit)}</b> · {i.badge ?? "synthetic firm"}
        </p>
        {open && (
          <div id={id} className="firm-insight__drill">
            <Drill insight={i} />
            {i.action && <a className="btn btn--quiet btn--sm" href={actionHref(i.action)}>{i.action.label}</a>}
          </div>
        )}
      </article>
    </li>
  );
}

/** The top insights as compact rows (at most seven). `openId` opens one on arrival, as the command palette asks. */
export function InsightRows({ items, openId }: { items: AdminInsight[]; openId?: string | null }) {
  const [open, setOpen] = useState<string | null>(openId && items.some((i) => i.id === openId) ? openId : null);
  return (
    <ol className="firm-insights" aria-label="The seven things to know, in the order they were chosen">
      {items.slice(0, 7).map((i) => <InsightRow key={i.id} i={i} open={open === i.id} onToggle={() => setOpen(open === i.id ? null : i.id)} />)}
    </ol>
  );
}
