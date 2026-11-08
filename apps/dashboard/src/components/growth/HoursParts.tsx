import { useState } from "react";
import { ApiError, api } from "../../api";
import { ChartFoot } from "../common";
import { useToast } from "../Toasts";
import { Hint } from "../Hint";
import { Details } from "../ui";
import { Range } from "../common";
import { Heatmap, HeatLegend, cellReadout, type Cursor } from "../Heatmap";
import { DayBand } from "../DayBand";
import { Forecast } from "../Forecast";
import { parseClock } from "../../lib/heatmap";
import { decideLocal, longestWindow } from "../../lib/forecast";
import { dowName } from "../../lib/format";
import type { LoadState } from "../../hooks";
import type { Presence as PresenceData, QuietHours } from "../../types";

// The parts of "Where my time goes" that draw the worker's own working hours: the weekly map, one day with its interval, free hours,
// whether a background run's window will last, and the quiet hours the worker sets. All of it is the worker's own data.

type PresenceMeta = LoadState<PresenceData>["meta"];

/** The weekly map with its readout, its key and its footer. One day's line and band sits under it. */
export function HoursMap({ data, meta }: { data: PresenceData; meta: PresenceMeta }) {
  const [cursor, setCursor] = useState<Cursor | null>(null);
  const [day, setDay] = useState(() => (new Date().getDay() + 6) % 7);
  return (
    <div className="stack">
      <div className="chart chart--wide">
        <Heatmap data={data} cursor={cursor} onCursor={setCursor} day={day} onDay={setDay} />
        <p className="note" aria-live="polite" style={{ minHeight: "3em" }}>{cellReadout(data, cursor)}</p>
        <HeatLegend />
        <ChartFoot variant="about" meta={meta} />
      </div>
      <Details summary={`${dowName(day)}, with its interval`}><DayBand data={data} day={day} /></Details>
    </div>
  );
}

export function IdleStat({ data }: { data: PresenceData }) {
  const i = data.idle_capacity_h;
  return (
    <section className="section" aria-labelledby="idle-h">
      <h3 id="idle-h" className="u-sr-only">Free hours</h3>
      <div className="stat">
        <span className="stat__label">Idle capacity<Hint label="About idle capacity">Hours a week the machine is likely free, outside your quiet hours. 95% interval {i.lo.toFixed(1)} to {i.hi.toFixed(1)} h; the bar runs 0 to {Math.ceil(i.hi * 1.15)} h.</Hint></span>
        <span className="stat__value tabular">{i.mean.toFixed(1)}<span className="stat__unit">hours a week</span></span>
        <Range lo={i.lo} hi={i.hi} pt={i.mean} min={0} max={Math.ceil(i.hi * 1.15)} />
      </div>
    </section>
  );
}

export function ForecastSection({ data, meta }: { data: PresenceData; meta: PresenceMeta }) {
  const [d, setD] = useState(60);
  const thr = data.decision_threshold;
  const best = longestWindow(data.forecast, thr);
  const res = decideLocal(data.forecast, thr, d);
  return (
    <section className="section" aria-labelledby="fc-h">
      <div className="section__head">
        <h3 id="fc-h" className="u-sr-only">Will the window last?</h3>
      </div>
      <p className="section__sub">A run starts only if the chance you stay away beats {Math.round(thr * 100)}%. Today: up to about {best} min.</p>
      <div className="chart">
        <Forecast data={data} d={d} />
        <div className="scrub">
          <div className="scrub__row">
            <label htmlFor="rl" className="t-data" style={{ whiteSpace: "nowrap" }}>Run length {d} min</label>
            <input id="rl" type="range" min={10} max={data.forecast[data.forecast.length - 1]?.d_min ?? 240} step={10} value={d} onChange={(e) => setD(Number(e.target.value))} />
          </div>
          <p className="scrub__caption" aria-live="polite">
            <b>{res.go ? "Go." : "Wait."}</b> A {d}-minute run has a {Math.round(res.survival * 100)}% chance of finishing before you are back. The threshold is {Math.round(thr * 100)}%.
          </p>
        </div>
        <ChartFoot variant="about" meta={meta} extra={<span>band: 95% interval</span>} />
      </div>
    </section>
  );
}

const DAY_LETTERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function QuietEditor({ quiet, onSaved }: { quiet: QuietHours; onSaved: () => void }) {
  const toast = useToast();
  const [start, setStart] = useState(quiet.start);
  const [end, setEnd] = useState(quiet.end);
  const [days, setDays] = useState<number[]>(quiet.days);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const dirty = start !== quiet.start || end !== quiet.end || days.join() !== [...quiet.days].sort().join();

  const save = async () => {
    setErr(null);
    if (Number.isNaN(parseClock(start)) || Number.isNaN(parseClock(end))) return setErr("Enter both times as hours and minutes, for example 22:00.");
    if (start === end) return setErr("Start and end are the same time. Pick two different times.");
    if (!days.length) return setErr("Pick at least one day, or the quiet hours would never apply.");
    setBusy(true);
    try {
      await api.putQuietHours({ start, end, days: [...days].sort() });
      toast({ tone: "success", text: "Quiet hours saved.", detail: "No background run will start inside them." });
      onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save. Try again.");
    } finally { setBusy(false); }
  };

  return (
    <section className="section" aria-labelledby="qh-h">
      <h3 id="qh-h" className="u-sr-only">Quiet hours</h3>
      <p className="section__sub">Nothing starts in the background inside these hours.<Hint label="About running while away">Running while you are away is a separate choice for each routine, and it is off until you turn it on.</Hint></p>
      <div className="stack">
        <div className="time-pair">
          <div className="field">
            <label className="field__label" htmlFor="qs">From</label>
            <input id="qs" className="input" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="qe">Until</label>
            <input id="qe" className="input" type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <span className="field__label" id="qd">On these days</span>
          <div className="day-chips" role="group" aria-labelledby="qd">
            {DAY_LETTERS.map((n, i) => (
              <button key={n} type="button" className="chip" aria-pressed={days.includes(i)}
                onClick={() => setDays((d) => (d.includes(i) ? d.filter((x) => x !== i) : [...d, i]))}>{n}</button>
            ))}
          </div>
        </div>
        {err && <p className="field__error" role="alert">{err}</p>}
        <div className="row">
          <button type="button" className="btn btn--primary" onClick={save} disabled={busy || !dirty}>{busy ? "Saving" : "Save quiet hours"}</button>
          {!dirty && <span className="note">Saved.</span>}
        </div>
      </div>
    </section>
  );
}
