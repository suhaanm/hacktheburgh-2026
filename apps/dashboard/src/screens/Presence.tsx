import { useMemo, useState } from "react";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { ChartFoot, ErrorState, Loading, OriginBadge, PageHead, Range } from "../components/common";
import { useToast } from "../components/Toasts";
import { Heatmap, HeatLegend, cellReadout, type Cursor } from "../components/Heatmap";
import { DayBand } from "../components/DayBand";
import { Forecast } from "../components/Forecast";
import { busiestWrap, meanRow, parseClock, slotLabel, toGrid } from "../lib/heatmap";
import { decideLocal, longestWindow } from "../lib/forecast";
import { dowName } from "../lib/format";
import type { Presence as PresenceData, QuietHours } from "../types";

export default function Presence() {
  const p = useLoad(() => api.presence(), []);
  const [cursor, setCursor] = useState<Cursor | null>(null);
  const [day, setDay] = useState(() => (new Date().getDay() + 6) % 7);

  const stretch = useMemo(() => (p.data ? busiestWrap(meanRow(toGrid(p.data.bins)), 0.5) : null), [p.data]);

  if (p.status === "error" && !p.data) return <div className="page"><ErrorState error={p.error} retry={p.reload} what="the presence map" /></div>;
  if (!p.data) return <div className="page"><Loading label="Loading the presence map" /></div>;
  const data = p.data;
  const title = stretch ? `You are usually at the machine from ${slotLabel(stretch[0])} to ${slotLabel(stretch[1])}` : "Your working week";

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow="Presence"
        title={title}
        lede="Each cell is a quarter hour. Darker means you are more likely to be there. The gaps are the free hours the agent could use, if you let it."
        aside={<OriginBadge meta={p.meta} />}
      />

      <section className="hero" aria-labelledby="heat-h">
        <h2 id="heat-h" className="u-sr-only">Weekly presence map</h2>
        <div className="chart chart--wide">
          <Heatmap data={data} cursor={cursor} onCursor={setCursor} day={day} onDay={setDay} />
          <p className="note" aria-live="polite" style={{ minHeight: "3em" }}>{cellReadout(data, cursor)}</p>
          <HeatLegend />
          <ChartFoot meta={p.meta} />
        </div>
      </section>

      <section className="section" aria-labelledby="day-h">
        <div className="section__head">
          <h2 id="day-h" className="section__title">{dowName(day)}, with its interval</h2>
          <p className="section__sub">The line is the estimate. The band is the 95% interval. Pick another day with the labels on the map.</p>
        </div>
        <DayBand data={data} day={day} />
      </section>

      <hr className="rule" />

      <div className="cols-2">
        <ForecastSection data={data} meta={p.meta} />
        <div className="stack" style={{ gap: "var(--space-7)" }}>
          <IdleStat data={data} />
          <QuietEditor key={JSON.stringify(data.quiet_hours)} quiet={data.quiet_hours} onSaved={p.reload} />
        </div>
      </div>
    </div>
  );
}

function IdleStat({ data }: { data: PresenceData }) {
  const i = data.idle_capacity_h;
  return (
    <section className="section" aria-labelledby="idle-h">
      <h2 id="idle-h" className="section__title">Free hours</h2>
      <div className="stat">
        <span className="stat__label">Idle capacity</span>
        <span className="stat__value tabular">{i.mean.toFixed(1)}<span className="stat__unit">hours a week</span></span>
        <span className="stat__interval">95% interval [{i.lo.toFixed(1)}, {i.hi.toFixed(1)}] h</span>
        <Range lo={i.lo} hi={i.hi} pt={i.mean} min={0} max={Math.ceil(i.hi * 1.15)} />
        <span className="stat__meta">Hours a week the machine is likely free, outside your quiet hours. The bar runs from 0 to {Math.ceil(i.hi * 1.15)} h.</span>
      </div>
    </section>
  );
}

function ForecastSection({ data, meta }: { data: PresenceData; meta: ReturnType<typeof useLoad<PresenceData>>["meta"] }) {
  const [d, setD] = useState(60);
  const thr = data.decision_threshold;
  const best = longestWindow(data.forecast, thr);
  const res = decideLocal(data.forecast, thr, d);
  return (
    <section className="section" aria-labelledby="fc-h">
      <div className="section__head">
        <h2 id="fc-h" className="section__title">Will the window last?</h2>
      </div>
      <p className="section__sub">A background run starts only when the chance that you stay away for its whole length is above {Math.round(thr * 100)}%. Today that allows runs up to about {best} minutes.</p>
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
        <ChartFoot meta={meta} extra={<span>band: 95% interval</span>} />
      </div>
    </section>
  );
}

const DAY_LETTERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function QuietEditor({ quiet, onSaved }: { quiet: QuietHours; onSaved: () => void }) {
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
      <h2 id="qh-h" className="section__title">Quiet hours</h2>
      <p className="section__sub">Inside these hours nothing starts in the background, even if you are away. Running while you are away is a separate choice for each routine, and it is off until you turn it on.</p>
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
