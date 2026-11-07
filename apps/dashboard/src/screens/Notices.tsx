import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { Hint } from "../components/Hint";
import { useLoad } from "../hooks";
import { useAppState } from "../store";
import { ErrorState, ExampleBadge, Loading, OriginBadge, PageHead, SourceNote } from "../components/common";
import { Details } from "../components/ui";
import { BUDGET_FLOOR, SAFETY_LINE, BUDGET_MAX, BUDGET_MIN, MODES, MODE_LABEL, STATE_WORD, budgetWords, clampBudget, groupTypes, hasLines, learnedLines, modeLine, needsYouLine, todayHeadline, todaySummary, whyLines, withMode, type Mode } from "../lib/attention";
import type { AttentionPatch, AttentionSettings } from "../types";

/** "Why?" for one item that needs you: loaded the first time it is opened, in the engine's own fixed words. */
function WhyItem({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const [w, setW] = useState<{ reason: string; steps: { state: string; text: string }[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!open || w || err) return;
    api.attentionWhy(id).then((r) => setW(whyLines(r.data)), (e: unknown) => setErr(e instanceof ApiError ? e.message : "The reason could not be read."));
  }, [open, w, err, id]);
  return (
    <details className="notices__why" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Why?</summary>
      {err ? <p className="note">{err}</p> : !w ? <p className="note">Reading the reason.</p> : (
        <div className="stack" style={{ gap: "var(--space-1)" }}>
          <p className="note">{w.reason || "No reason was recorded."}</p>
          {w.steps.length > 0 && <ol className="plain-list">{w.steps.map((s, i) => <li key={i} className="note"><b>{s.state}</b>: {s.text}</li>)}</ol>}
        </div>
      )}
    </details>
  );
}

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
  const t = todaySummary(today.data?.today, today.data?.today_detail);

  return (
    <div className="page page--read">
      <PageHead
        eyebrow="Notices"
        title="How loudly each kind of notice speaks"
        lede="Choose how loudly each kind of notice speaks. Safety stops and blocking approvals always show."
        aside={<><OriginBadge meta={settings.meta} /><ExampleBadge why={settings.why} /></>}
      />
      <SourceNote why={settings.why} also={example ? "These are example settings. A change here only changes this screen." : undefined} />
      <p className="u-sr-only" role="status" aria-live="polite">{saved ?? ""}</p>
      {err && <div className="state state--error" role="alert"><span className="state__mark" aria-hidden="true" /><p className="state__body">{err}</p></div>}

      <section className="notices__today" aria-labelledby="today-h" data-testid="today-strip">
        <h2 className="section__title" id="today-h">Today</h2>
        {today.status === "error" && !today.data ? <p className="note">Today's counts could not be read. {today.error.message}</p> : !today.data ? <Loading label="Loading today's counts" /> : (
          <>
            <p className="notices__headline">{todayHeadline(t, today.data.budget ?? { used: 0, per_day: s.budget_per_day })}</p>
            {t.lines.length === 0 ? <p className="note">Nothing has been shown, held or dropped yet today.</p> : (
              <details className="details" data-testid="today-detail">
                <summary>Why each count</summary>
                <div className="details__body details__body--wide">
                <ul className="plain-list notices__lines">
                  {t.lines.map((l) => (
                    <li key={`${l.state}:${l.code}`} className="note" data-state={l.state}>
                      <b className="tabular">{l.n} {STATE_WORD[l.state]}</b> {l.text ?? "The engine sent only this count."}
                    </li>
                  ))}
                </ul>
                </div>
              </details>
            )}
            {(today.data.needs_you_items ?? []).length > 0 && (
              <ul className="plain-list notices__lines" aria-label="Needs you" data-testid="needs-you">
                {(today.data.needs_you_items ?? []).map((i) => (
                  <li key={`${i.type}:${i.id ?? ""}`} className="note"><b>{needsYouLine(i)}</b>{i.id ? <WhyItem id={i.id} /> : null}</li>
                ))}
              </ul>
            )}
            {hasLines(today.data) && (
              <ul className="plain-list notices__lines" aria-label="Right now">{today.data.lines.map((x) => <li key={x} className="note">{x}</li>)}</ul>
            )}
          </>
        )}
      </section>

      {groups.map((g, gi) => {
        const fixed = g.rows.filter((r) => r.fixed);
        const rows = g.rows.filter((r) => !r.fixed);
        const changed = rows.filter((r) => r.mode !== "normal").length;
        return (
          <details key={g.id} className="notices__group" open={gi === 0} data-testid={`group-${g.id}`}>
            <summary>
              <span className="section__title">{g.title}</span>
              <span className="notices__count u-muted">{rows.length + fixed.length} kinds{changed > 0 ? `, ${changed} changed` : ""}</span>
            </summary>
            <p className="section__sub">{g.blurb}</p>
            <div className="notices__rows">
              {fixed.length > 0 && (
                <div className="notice" data-fixed="true">
                  <div className="notice__head">
                    <span className="notice__name">Safety stops are always shown.</span>
                    <span className="pill notice__lock"><span className="pill__glyph-char" aria-hidden="true">&#9679;</span>Always shown</span>
                  </div>
                  <Details summary="What always shows">
                    <p className="note">{SAFETY_LINE}</p>
                    <ul className="plain-list">{fixed.map((r) => <li key={r.type} className="note" data-testid={`notice-${r.type}`}>{r.label}. <span className="u-muted">Always shown.</span></li>)}</ul>
                  </Details>
                </div>
              )}
              {rows.map((r) => (
                <div key={r.type} className="notice" data-fixed="false" data-testid={`notice-${r.type}`}>
                  <div className="notice__head">
                    <span className="notice__name">{r.label}<Hint label={`What ${r.label} does at this setting`}>{modeLine(r.cls, r.mode)}</Hint></span>
                    <div className="segmented" role="group" aria-label={`How loud: ${r.label}`}>
                      {MODES.map((m: Mode) => (
                        <button key={m} type="button" aria-pressed={r.mode === m} onClick={() => { if (r.mode !== m) void apply({ modes: { [r.type]: m } }, (x) => withMode(x, r.type, m), `${r.label}: ${MODE_LABEL[m]}.`); }}>{MODE_LABEL[m]}</button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </details>
        );
      })}

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
          <p className="section__sub">It can make a low-value kind quieter, never louder, and never quieter than the floors below.<Hint label="About learning">It watches how you react to notices.</Hint></p>
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
