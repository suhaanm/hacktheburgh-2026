import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { useAppState } from "../store";
import { ErrorState, ExampleBadge, Loading, Note, OriginBadge, PageHead, SourceNote } from "../components/common";
import { BUDGET_FLOOR, BUDGET_MAX, BUDGET_MIN, MODES, MODE_LABEL, budgetWords, clampBudget, groupTypes, hasLines, learnedLines, modeLine, todayHeadline, todaySummary, withMode, type Mode } from "../lib/attention";
import type { AttentionPatch, AttentionSettings } from "../types";

/** One idea: how loudly each kind of notice speaks. Today's counts and the summary sit under it; the floors are said plainly. */
export default function Notices() {
  const me = useAppState().person ?? undefined;
  const settings = useLoad(() => api.attentionSettings(me), [me]);
  const today = useLoad(() => api.attentionDigest(me, "now"), [me]);
  const morning = useLoad(() => api.attentionDigest(me, "morning"), [me]);
  const back = useLoad(() => api.attentionDigest(me, "return"), [me]);
  const [s, setS] = useState<AttentionSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [budget, setBudget] = useState<number | null>(null);
  const seq = useRef(0);

  useEffect(() => { if (settings.data) { setS(settings.data); setBudget(settings.data.budget_per_day); } }, [settings.data]);

  if (settings.status === "error" && !settings.data) return <div className="page"><ErrorState error={settings.error} retry={settings.reload} what="your notice settings" /></div>;
  if (!s || budget == null) return <div className="page"><Loading label="Loading your notice settings" /></div>;
  const example = !!settings.why;

  /** Apply a change at once, send it, and put it back with the engine's own words if it is refused. */
  const apply = async (patch: AttentionPatch, optimistic: (x: AttentionSettings) => AttentionSettings, said: string) => {
    const before = s;
    const mine = ++seq.current;
    setS(optimistic(s)); setErr(null);
    try {
      const r = await api.attentionSet(patch, me);
      if (mine === seq.current && r.data && Array.isArray(r.data.types)) { setS(r.data); setBudget(r.data.budget_per_day); }
      setSaved(said);
    } catch (e) {
      if (mine === seq.current) { setS(before); setBudget(before.budget_per_day); }
      setErr(e instanceof ApiError ? `${e.message}${e.code ? ` (${e.code})` : ""}` : "That did not go through. Nothing changed.");
      setSaved(null);
    }
  };

  const groups = groupTypes(s.types);
  const learned = learnedLines(s.learned);
  const floors = [...new Set(s.floors.map((f) => f.why))];
  const t = todaySummary(today.data?.today);

  return (
    <div className="page page--read">
      <PageHead
        eyebrow="Notices"
        title="How loudly each kind of notice speaks"
        lede="Understudy shows less than it could. For each kind of notice, choose how much of it you want. Safety stops and approvals that block a job always stay visible."
        aside={<><OriginBadge meta={settings.meta} /><ExampleBadge why={settings.why} /></>}
      />
      <SourceNote why={settings.why} />
      {example && <Note>These are example settings. A change here only changes this screen.</Note>}
      <p className="u-sr-only" role="status" aria-live="polite">{saved ?? ""}</p>
      {err && <div className="state state--error" role="alert"><span className="state__mark" aria-hidden="true" /><p className="state__body">{err}</p></div>}

      <section className="notices__today" aria-labelledby="today-h" data-testid="today-strip">
        <h2 className="section__title" id="today-h">Today</h2>
        {today.status === "error" && !today.data ? <p className="note">Today's counts could not be read. {today.error.message}</p> : !today.data ? <Loading label="Loading today's counts" /> : (
          <>
            <p className="notices__headline">{todayHeadline(t, today.data.budget ?? { used: 0, per_day: s.budget_per_day })}</p>
            {t.lines.length === 0 ? <p className="note">Nothing has been shown, held or dropped yet today.</p> : (
              <ul className="plain-list notices__lines">
                {t.lines.map((l) => (
                  <li key={`${l.state}:${l.code}`} className="note" data-state={l.state}>
                    <b className="tabular">{l.n} {l.state === "other" ? "" : l.state}</b> {l.text}
                    {(l.state === "held" || l.state === "dropped") && <details className="notices__why"><summary>Why?</summary><p className="note">{l.text} Nothing was lost: held items stay counted, and a dropped one had stopped being useful. You can change how loud this kind of notice is above.</p></details>}
                  </li>
                ))}
              </ul>
            )}
            {hasLines(today.data) && (
              <ul className="plain-list notices__lines" aria-label="Right now">{today.data.lines.map((x) => <li key={x} className="note">{x}</li>)}</ul>
            )}
          </>
        )}
      </section>

      {groups.map((g) => (
        <section key={g.id} className="notices__group" aria-labelledby={`g-${g.id}`}>
          <div className="section__head">
            <h2 className="section__title" id={`g-${g.id}`}>{g.title}</h2>
            <p className="section__sub">{g.blurb}</p>
          </div>
          <div className="notices__rows">
            {g.rows.map((r) => (
              <div key={r.type} className="notice" data-fixed={r.fixed} data-testid={`notice-${r.type}`}>
                <div className="notice__head">
                  <span className="notice__name">{r.label}</span>
                  {r.fixed ? (
                    <span className="pill notice__lock"><span className="pill__glyph-char" aria-hidden="true">&#9679;</span>Always shown</span>
                  ) : (
                    <div className="segmented" role="group" aria-label={`How loud: ${r.label}`}>
                      {MODES.map((m: Mode) => (
                        <button key={m} type="button" aria-pressed={r.mode === m} onClick={() => { if (r.mode !== m) void apply({ modes: { [r.type]: m } }, (x) => withMode(x, r.type, m), `${r.label}: ${MODE_LABEL[m]}.`); }}>{MODE_LABEL[m]}</button>
                      ))}
                    </div>
                  )}
                </div>
                <p className="note">{modeLine(r.cls, r.mode)}</p>
              </div>
            ))}
          </div>
        </section>
      ))}

      <section className="section" aria-labelledby="budget-h">
        <div className="section__head">
          <h2 className="section__title" id="budget-h">Notices per day</h2>
          <p className="section__sub">{BUDGET_FLOOR}</p>
        </div>
        <div className="notices__budget">
          <label className="u-sr-only" htmlFor="budget">Notices per day, from {BUDGET_MIN} to {BUDGET_MAX}</label>
          <input id="budget" type="range" min={BUDGET_MIN} max={BUDGET_MAX} step={1} value={budget}
            aria-valuetext={`${budget} notices a day`}
            onChange={(e) => setBudget(clampBudget(Number(e.target.value)))}
            onPointerUp={() => { if (budget !== s.budget_per_day) void apply({ budget_per_day: budget }, (x) => ({ ...x, budget_per_day: budget }), `Notices per day: ${budget}.`); }}
            onKeyUp={() => { if (budget !== s.budget_per_day) void apply({ budget_per_day: budget }, (x) => ({ ...x, budget_per_day: budget }), `Notices per day: ${budget}.`); }} />
          <b className="tabular notices__value">{budget}</b>
        </div>
        <p className="note">{budgetWords(budget)}</p>
      </section>

      <section className="section" aria-labelledby="glance-h">
        <h2 className="section__title u-sr-only" id="glance-h">Help level</h2>
        <label className="toggle">
          <input type="checkbox" role="switch" checked={s.level_glance} onChange={(e) => void apply({ level_glance: e.target.checked }, (x) => ({ ...x, level_glance: e.target.checked }), `Help level glance ${e.target.checked ? "on" : "off"}.`)} />
          <span className="toggle__track" aria-hidden="true" />
          <span className="toggle__text"><span>Show the help level for two seconds when it changes</span><span className="toggle__hint">Only when nothing else is on screen and you have been still for a moment.</span></span>
        </label>
      </section>

      <section className="section" aria-labelledby="learn-h">
        <div className="section__head">
          <h2 className="section__title" id="learn-h">What Understudy learned</h2>
          <p className="section__sub">It watches how you react to notices and can make a low-value kind quieter. It can never make one louder, and never quieter than the floors below.</p>
        </div>
        {learned.length === 0 ? <p className="note">Nothing yet. Every kind of notice is as loud as you set it.</p> : (
          <ul className="plain-list">{learned.map((l) => <li key={l.type} className="note">{l.text}</li>)}</ul>
        )}
        {learned.length > 0 && (confirm ? (
          <div className="row">
            <button type="button" className="btn btn--danger btn--sm" onClick={() => { setConfirm(false); void apply({ reset_learned: true }, (x) => ({ ...x, learned: {} }), "What it learned was reset."); }}>Yes, reset what it learned</button>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirm(false)}>Keep it</button>
          </div>
        ) : (
          <div><button type="button" className="btn btn--secondary btn--sm" onClick={() => setConfirm(true)}>Reset what Understudy learned</button></div>
        ))}
      </section>

      <section className="section" aria-labelledby="floor-h">
        <h2 className="section__title" id="floor-h">What no setting can turn off</h2>
        {floors.length === 0 ? <p className="note">The engine listed no fixed floors.</p> : <ul className="plain-list">{floors.map((w) => <li key={w} className="note">{w}</li>)}</ul>}
      </section>

      {[["morning", "Your morning summary", morning], ["return", "Since you were away", back]].map(([id, title, st]) => {
        const d = (st as typeof morning).data;
        if (!hasLines(d)) return null;
        return (
          <section key={id as string} className="section" aria-labelledby={`sum-${id}`} id={`summary-${id}`}>
            <h2 className="section__title" id={`sum-${id}`}>{title as string}</h2>
            <ul className="plain-list">{d!.lines.map((x) => <li key={x} className="note">{x}</li>)}</ul>
          </section>
        );
      })}
    </div>
  );
}
