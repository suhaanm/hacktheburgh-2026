import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api";
import { ErrorState, EmptyState, ExampleBadge, Loading, OriginBadge, PageHead, SourceNote } from "../../components/common";
import { Hint } from "../../components/Hint";
import { useToast } from "../../components/Toasts";
import { Details } from "../../components/ui";
import { HitList } from "../../components/repeats/HitList";
import { fmtHours, fmtHoursRange, heldText, ledeFor, totalExplained } from "../../components/repeats/model";
import type { HitRow, HitState } from "../../components/repeats/types";
import { useLoad, useTimeout } from "../../hooks";
import { useRoute } from "../../router";
import { exampleKind, hideRow, loadFirm, loadRepeats, resetCounts, unhideRow } from "./data";
import { Peek } from "./Peek";

type Win = 7 | 30;
const KEY = "understudy-repeats-window";

function savedWindow(): Win {
  try { return window.localStorage.getItem(KEY) === "30" ? 30 : 7; } catch { return 7; }
}

function WindowSwitch({ value, onChange }: { value: Win; onChange: (w: Win) => void }) {
  return (
    <div className="segmented" role="group" aria-label="Time window">
      {([7, 30] as Win[]).map((w) => (
        <button key={w} type="button" aria-pressed={value === w} onClick={() => { onChange(w); try { window.localStorage.setItem(KEY, String(w)); } catch { /* storage can be blocked */ } }}>{w} days</button>
      ))}
    </div>
  );
}

const EMPTY_TITLE: Record<Exclude<HitState, "ok">, string> = {
  new_user: "Nothing to count yet",
  too_little_data: "Too little to tell yet",
  nothing_repeats: "Nothing repeats yet",
  all_handled: "Nothing left to hand over",
  counting_again: "Counting again",
  capture_off: "Capture is off",
};

const HELPER = "Things you did by hand at least three times, biggest time first.";

export default function Repeats() {
  const route = useRoute();
  return route.query.get("as") === "admin" ? <Firm /> : <Mine kind={exampleKind(route.query.get("example"))} />;
}

/* ================================================================================================ the worker's list */
function Mine({ kind }: { kind: ReturnType<typeof exampleKind> }) {
  const [win, setWin] = useState<Win>(savedWindow);
  const r = useLoad(() => loadRepeats(win, kind), [win, kind]);
  const toast = useToast();
  const later = useTimeout();
  const [undo, setUndo] = useState<{ id: string; label: string } | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const undoBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (undo) undoBtn.current?.focus(); }, [undo]);

  if (r.status === "error" && !r.data) return <div className="page page--read rp"><ErrorState error={r.error} retry={r.reload} what="your repeated work" /></div>;
  if (!r.data) {
    return (
      <div className="page page--read rp">
        <PageHead eyebrow="Repeats" title="What you do again and again" lede={HELPER} />
        <Loading label="Loading your repeated work" />
      </div>
    );
  }
  const d = r.data;
  const source = r.source ?? "demo";
  const why = r.why;
  const fail = (e: unknown, fallback: string) => setErr(e instanceof ApiError ? e.message : fallback);

  const hide = async (row: HitRow) => {
    setErr(null);
    try {
      await hideRow(row.id, win, source);
      setUndo({ id: row.id, label: row.label });
      later(() => setUndo((u) => (u?.id === row.id ? null : u)), 10_000);
      r.reload();
    } catch (e) { fail(e, "That did not save. Try again."); }
  };
  const show = async (id: string) => {
    setErr(null);
    try { await unhideRow(id, source); setUndo(null); r.reload(); } catch (e) { fail(e, "That did not save. Try again."); }
  };
  const reset = async () => {
    setBusy(true); setErr(null);
    try {
      await resetCounts(source);
      setConfirm(false);
      toast({ tone: "success", text: "Counting again from now.", detail: "Your recordings, routines and memory file were not touched." });
      r.reload();
    } catch (e) { fail(e, "That did not save. Try again."); }
    finally { setBusy(false); }
  };

  const total = d.total;
  const lede = d.state === "ok" && total ? (
    <>
      {ledeFor(total.actions, total.hours_per_week, d.window_days)}{" "}
      <Hint label="How the hours a week were worked out">{totalExplained(total.repeats, d.episodes_in_window, total.hours_per_week, d.window_days)}</Hint>
    </>
  ) : HELPER;
  const held = heldText(d.held_back, d.not_shown);

  return (
    <div className="page page--read rp" aria-busy={r.status === "loading"}>
      <PageHead eyebrow="Repeats" title="What you do again and again" lede={lede} />

      <section className="rp-main" aria-label="Repeated work">
        <div className="rp-bar"><WindowSwitch value={win} onChange={setWin} />{why ? <ExampleBadge why={why} /> : <OriginBadge meta={r.meta} />}</div>

        {d.state === "ok" ? (
          <HitList rows={d.rows} automated={d.automated} windowDays={d.window_days} label={`Repeated work, last ${d.window_days} days`} onHide={hide}
            renderPeek={(row, close) => <Peek row={row} windowDays={d.window_days} source={source} close={close} onDone={r.reload} />} />
        ) : (
          <>
            <EmptyState title={EMPTY_TITLE[d.state]} body={d.message} />
            {d.automated.length > 0 && <HitList rows={[]} automated={d.automated} windowDays={d.window_days} />}
          </>
        )}

        {undo && (
          <p className="rp-undo" role="status">
            <b>Hidden.</b> <span>“{undo.label}” comes back if you do it twice as often.</span>
            <button ref={undoBtn} type="button" className="btn btn--quiet btn--sm" onClick={() => void show(undo.id)}>Undo</button>
          </p>
        )}
        {err && <p className="field__error" role="alert">{err}</p>}
        {d.hidden.length > 0 && (
          <details className="evidence">
            <summary>Hidden <span className="num">({d.hidden.length})</span></summary>
            <div className="hitlist rp-hidden" role="list">
              {d.hidden.map((h) => (
                <div key={h.id} className="rp-hidden__row" role="listitem">
                  <span>{h.label} <span className="u-muted">({h.count} {h.count === 1 ? "time" : "times"}, back at {h.returns_at})</span></span>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => void show(h.id)}>Show again</button>
                </div>
              ))}
            </div>
          </details>
        )}
        {held && <p className="rp-held">{held}</p>}
      </section>

      <div className="rp-foot">
        <p className="note">Counts come from this device. Nothing runs unless you press Automate.</p>
        <SourceNote why={why} />
        <Details summary="About this list">
          <div className="stack" style={{ gap: "var(--space-3)" }}>
            <p className="note">Minutes are estimates of the time you could save each week, with a 95% interval. A step appears once it has repeated three times. A row you hide comes back only when you do it twice as often.</p>
            {confirm ? (
              <div className="rp-confirm" role="group" aria-label="Start counting again">
                <p><b>Start counting again?</b> This clears the counts on this list and any rows you hid. Your recordings, routines and memory file are not touched.</p>
                <div className="row">
                  <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => void reset()}>Start counting again</button>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirm(false)}>Cancel</button>
                </div>
              </div>
            ) : (
              <div><button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirm(true)}>Start counting again</button></div>
            )}
          </div>
        </Details>
      </div>
    </div>
  );
}

/* ================================================================================================ the firm's list (admin) */
function Firm() {
  const [win, setWin] = useState<Win>(savedWindow);
  const r = useLoad(() => loadFirm(win), [win]);
  if (r.status === "error" && !r.data) return <div className="page page--read rp"><ErrorState error={r.error} retry={r.reload} what="the firm's repeated work" /></div>;
  if (!r.data) return <div className="page page--read rp"><PageHead eyebrow="Repeats · firm" title="What the firm does again and again" lede={HELPER} /><Loading label="Loading the firm's repeated work" /></div>;
  const d = r.data;
  return (
    <div className="page page--read rp">
      <PageHead eyebrow="Repeats · firm" title="What the firm does again and again"
        lede={d.rows.length
          ? `${d.total.actions} repeated actions across ${d.people} people, about ${fmtHours(d.total.hours_per_week.point)} a week in all (${fmtHoursRange(d.total.hours_per_week)}, 95% interval). For coaching and onboarding, not for evaluating individuals.`
          : "No action is repeated by five or more people in this window."}
      />
      <section className="rp-main" aria-label="Repeated work across the firm">
        <div className="rp-bar"><WindowSwitch value={win} onChange={setWin} />{r.why ? <ExampleBadge why={r.why} /> : <OriginBadge meta={r.meta} always />}</div>
        {d.rows.length ? <HitList audience="admin" rows={d.rows} windowDays={d.window_days} label={`Repeated work across the firm, last ${d.window_days} days`} />
          : <EmptyState title="Nothing repeats across the firm yet" body="A group of fewer than five people is never listed, so a quiet week can show nothing." />}
        <p className="rp-held">People are counted, never named or ranked. {d.suppressed > 0 ? `${d.suppressed} ${d.suppressed === 1 ? "group" : "groups"} of fewer than ${d.min_group} people ${d.suppressed === 1 ? "is" : "are"} not listed.` : ""}</p>
        <SourceNote why={r.why} />
      </section>
    </div>
  );
}
