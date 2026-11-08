import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api";
import { ErrorState, Loading } from "../../components/common";
import { HitList } from "../../components/repeats/HitList";
import { heldText } from "../../components/repeats/model";
import type { HitRow, HitState } from "../../components/repeats/types";
import { BackgroundTasks } from "../../components/routines/BackgroundTasks";
import { RunningRow } from "../../components/routines/RunningRow";
import type { Decide } from "../../components/routines/types";
import { useToast } from "../../components/Toasts";
import { Details } from "../../components/ui";
import { useLoad, useTimeout } from "../../hooks";
import { useTasks } from "../../lib/useTasks";
import { navigate, useRoute } from "../../router";
import { clip } from "../../lib/safeText";
import { refreshNeedsBadge } from "../NeedsYou/count";
import { plainWords } from "../NeedsYou/model";
import { exampleKind, hideRow, loadRepeats, resetCounts, runNow, unhideRow } from "./data";
import { TABS, defaultTab, routinesHeadline, runningRoutines, turnedDown, type Tab } from "./model";
import { Peek } from "./Peek";
import { trackRoutineRun } from "../../lib/wakeContext";
import "../../components/kc.css";
import "../../components/routines/routines.css";

type Win = 7 | 30;
const KEY = "understudy-repeats-window";
const savedWindow = (): Win => { try { return window.localStorage.getItem(KEY) === "30" ? 30 : 7; } catch { return 7; } };

const EMPTY_TITLE: Record<Exclude<HitState, "ok">, string> = {
  new_user: "Nothing to count yet",
  too_little_data: "Too little to tell yet",
  nothing_repeats: "Nothing repeats yet",
  all_handled: "Nothing left to hand over",
  counting_again: "Counting again",
  capture_off: "Capture is off",
};

/**
 * Routines: Your routines (the ones you set up and how far each is trusted) and Could automate (what you do by hand again and again, biggest time first).
 * The decision to start one is made in Needs you; this is where you manage what already runs and find what could. At most seven rows, then "Show all".
 */
export default function Routines() {
  const route = useRoute();
  const asked = route.query.get("tab");
  const rt = useLoad(() => api.routines(), []);
  const [win, setWin] = useState<Win>(savedWindow);
  const kind = exampleKind(route.query.get("example"));
  const rep = useLoad(() => loadRepeats(win, kind), [win, kind]);
  const toast = useToast();
  const [openId, setOpenId] = useState<string | null>(null);
  const [limit, setLimit] = useState(7);
  // The tasks list and the routines refresh together, by themselves (every 2 s while a task runs, 15 s otherwise, on focus, on the run's own stream).
  const tasks = useTasks({ alsoReload: rt.reload });

  const setTab = (t: Tab) => navigate(`/routines?tab=${t}`);      // always explicit: a worker who chose a tab keeps it
  const running = runningRoutines(rt.data);
  const could = rep.data?.state === "ok" ? rep.data.rows.length : 0;
  // With no tab asked for, open where there is something: Could automate when Your routines is empty and that list is not.
  const tab: Tab = defaultTab(asked, running.length, could);

  // The tab strip is a real tab list: arrow keys move between the two tabs.
  const onTabKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = tab === "running" ? "could-automate" : "running";
    setTab(next);
    window.setTimeout(() => document.getElementById(`tab-${next}`)?.focus(), 0);
  };

  if (rt.status === "error" && !rt.data) return <div className="page page--read kc-page"><ErrorState error={rt.error} retry={rt.reload} what="your routines" /></div>;
  if (!rt.data) return <div className="page page--read kc-page"><Loading label="Loading your routines" /></div>;

  const decide: Decide = async (routine, body, done) => {
    await api.setConsent(routine.id, body);
    toast({ tone: "success", text: done });
    rt.reload();
    void refreshNeedsBadge();
  };
  const onRun = async (r: { id: string; status: string; title: string }): Promise<string | null> => {
    const started = await runNow(r.id, r.status);
    if (!started) return "The agent service did not answer, so nothing started. Try again in a moment.";
    toast({ tone: "success", text: "Started.", detail: `${r.title}. Stop it any time with Stop.` });
    if (started.run_id) trackRoutineRun(r.id, started.run_id);      // the voice context learns which routine runs and at which step (when the agent says how many there are)
    return `Started${started.run_id ? ` (${started.run_id})` : ""}. Stop it any time with Stop.`;
  };

  const shown = running.slice(0, limit);
  const headline = routinesHeadline({
    tasksRunning: tasks.grouped.active.filter((x) => x.state === "running").length, routinesRunning: running.length,
    couldMinutes: rep.data?.state === "ok" ? rep.data.rows.reduce((a, row) => a + (Number.isFinite(row.minutes_per_week?.point) ? Math.max(0, row.minutes_per_week.point) : 0), 0) : 0,
  });

  return (
    <div className="page page--read kc-page">
      <div className="kc-head">
        <h1 className="kc-title">Routines</h1>
      </div>
      {headline && <p className="kc-headline" data-testid="headline">{headline}</p>}

      <div className="rt-bar">
        <div className="kc-tabs" role="tablist" aria-label="Routines" onKeyDown={onTabKey} style={{ flex: "1 1 auto" }}>
          {TABS.map((t) => (
            <button key={t.id} id={`tab-${t.id}`} type="button" role="tab" aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} tabIndex={tab === t.id ? 0 : -1} onClick={() => setTab(t.id)}>
              {t.label}<span className="kc-count">{t.id === "running" ? running.length : could}</span>
            </button>
          ))}
        </div>
      </div>

      {tab === "running" ? (
        <div role="tabpanel" id="panel-running" aria-labelledby="tab-running" style={{ display: "grid", gap: "var(--space-4)" }}>
          <BackgroundTasks view={tasks} />
          {running.length === 0 ? (
            <div className="kc-empty">
              <h2>No routines yet.</h2>
              <p>Choose Watch first on a proposal in Needs you.</p>
            </div>
          ) : (
            <ul className="kc-list" aria-label="Your routines">
              {shown.map((r) => (
                <li key={r.id}>
                  <RunningRow routine={r} open={openId === r.id} canRun onToggle={() => setOpenId(openId === r.id ? null : r.id)} onDecide={decide} onRun={onRun} />
                </li>
              ))}
            </ul>
          )}
          {running.length > shown.length && <div><button type="button" className="btn btn--secondary btn--sm" onClick={() => setLimit((n) => (n < 50 ? 50 : n + 50))}>{limit < 50 && running.length <= 50 ? `Show all ${running.length}` : limit < 50 ? "Show 50" : "Show 50 more"}</button></div>}
          <TurnedDown rows={turnedDown(rt.data)} onDecide={decide} />
        </div>
      ) : (
        <div role="tabpanel" id="panel-could-automate" aria-labelledby="tab-could-automate">
          <CouldAutomate win={win} setWin={setWin} r={rep} />
        </div>
      )}
    </div>
  );
}

/** What the worker said no to, one click from a yes. Behind one disclosure so Your routines stays short. */
function TurnedDown({ rows, onDecide }: { rows: ReturnType<typeof turnedDown>; onDecide: Decide }) {
  const [err, setErr] = useState<string | null>(null);
  if (rows.length === 0) return null;
  return (
    <Details summary={`Turned down (${rows.length})`}>
      <div>
        {rows.slice(0, 30).map((x) => (
          <div key={x.id} className="rt-more-row">
            <span>{plainWords(clip(x.title, 120)) || "A routine"} <span className="u-muted">({x.status === "never" ? "Never" : "Not now"})</span></span>
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => { setErr(null); onDecide(x, { mode: "shadow" }, "Set to watch first.").catch((e: unknown) => setErr(e instanceof ApiError ? e.message : "That did not save. Try again.")); }}>Watch first</button>
          </div>
        ))}
        {rows.length > 30 && <p className="kc-sub">{rows.length - 30} more turned down.</p>}
        {err && <p className="kc-error" role="alert">{err}</p>}
      </div>
    </Details>
  );
}

/* ================================================================================================ the repeated-work list */
function CouldAutomate({ win, setWin, r }: { win: Win; setWin: (w: Win) => void; r: ReturnType<typeof useLoad<import("../../components/repeats/types").HitlistWire>> }) {
  const toast = useToast();
  const later = useTimeout();
  const [undo, setUndo] = useState<{ id: string; label: string } | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const undoBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (undo) undoBtn.current?.focus(); }, [undo]);

  if (r.status === "error" && !r.data) return <ErrorState error={r.error} retry={r.reload} what="your repeated work" />;
  if (!r.data) return <Loading label="Loading your repeated work" />;
  const d = r.data;
  const source = r.source ?? "demo";
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
  const held = heldText(d.held_back, d.not_shown);

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }} aria-busy={r.status === "loading"}>
      <div className="rt-bar">
        <span />
        <div className="segmented" role="group" aria-label="Time window">
          {([7, 30] as Win[]).map((w) => (
            <button key={w} type="button" aria-pressed={win === w} onClick={() => { setWin(w); try { window.localStorage.setItem(KEY, String(w)); } catch { /* storage can be blocked */ } }}>{w} days</button>
          ))}
        </div>
      </div>

      {d.state === "ok" ? (
        <HitList rows={d.rows} windowDays={d.window_days} label={`Repeated work, last ${d.window_days} days`} onHide={hide}
          renderPeek={(row, close) => <Peek row={row} windowDays={d.window_days} source={source} close={close} onDone={r.reload} />} />
      ) : (
        <div className="kc-empty"><h2>{EMPTY_TITLE[d.state]}</h2><p>{d.message}</p></div>
      )}

      {undo && (
        <p className="rp-undo" role="status">
          <b>Hidden.</b> <span>“{undo.label}” comes back if you do it twice as often.</span>
          <button ref={undoBtn} type="button" className="btn btn--quiet btn--sm" onClick={() => void show(undo.id)}>Undo</button>
        </p>
      )}
      {err && <p className="kc-error" role="alert">{err}</p>}

      <Details summary="More">
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {d.hidden.length > 0 && (
            <div>
              <p className="kc-label">Hidden ({d.hidden.length})</p>
              {d.hidden.map((h) => (
                <div key={h.id} className="rt-more-row">
                  <span>{h.label} <span className="u-muted">({h.count} {h.count === 1 ? "time" : "times"}, back at {h.returns_at})</span></span>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => void show(h.id)}>Show again</button>
                </div>
              ))}
            </div>
          )}
          {d.automated.length > 0 && <HitList rows={[]} automated={d.automated} windowDays={d.window_days} />}
          {held && <p className="kc-sub">{held}</p>}
          <p className="kc-sub">Counts come from this device. Nothing runs unless you press Automate. Minutes are estimates with a 95% interval; a step appears once it has repeated three times.</p>
          {confirm ? (
            <div className="kc-confirm" role="group" aria-label="Start counting again">
              <p>Start counting again? This clears the counts on this list and any rows you hid. Your recordings, routines and memory file are not touched.</p>
              <div className="row">
                <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => void reset()}>Start counting again</button>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => setConfirm(false)}>Keep counting</button>
              </div>
            </div>
          ) : (
            <div><button type="button" className="btn btn--secondary btn--sm" onClick={() => setConfirm(true)}>Start counting again</button></div>
          )}
        </div>
      </Details>
    </div>
  );
}
