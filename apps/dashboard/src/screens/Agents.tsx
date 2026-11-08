import { useEffect, useReducer, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { useViewRole } from "../components/home/viewAs";
import { useLoad } from "../hooks";
import { useLive, useRegisteredStreams } from "../lib/live";
import { anyActiveRun } from "../lib/tasks";
import { CheckChip, EmptyState, ErrorState, Loading, PageHead, SourceNote, StatePill } from "../components/common";
import { OriginBadge } from "../components/needsyou/Origin";
import { Hint } from "../components/Hint";
import { Details } from "../components/ui";
import { Facts } from "../components/Facts";
import { KV } from "../components/needsyou/KV";
import "../components/kc.css";
import { useToast } from "../components/Toasts";
import { KIND_DOES, budgetBars, childResults, countStates, falseClaim, fmtClock, isActive, kindLabel, leaseLeft, resultWithoutSteps, runActive, stateTone, stepsOf, stopReason, verifiedTally } from "../lib/agents";
import { fmtDateTime } from "../lib/format";
import type { AgentKind, AgentNode, AgentRun, SpawnKind } from "../types";

/**
 * Background runs: the technical view of what ran in the background (helpers, leases, budgets, run ids). It is the admin's: a worker sees their own
 * tasks in Routines, one line each. A worker who arrives here by an address sees the one gate sentence and nothing else (docs/knack-ux/views.md).
 */
export default function Agents() {
  const role = useViewRole();
  if (role === "worker") return <div className="page page--read kc-page"><p className="kc-row__body" data-testid="admin-gate">Switch to Admin to see this.</p></div>;
  return <BackgroundRuns />;
}

function BackgroundRuns() {
  const runs = useLoad(() => api.agentsRuns(), []);
  const loadedAt = useRef(Date.now());
  const [, tick] = useReducer((n: number) => n + 1, 0);
  const [allRuns, setAllRuns] = useState(false);

  useEffect(() => { loadedAt.current = Date.now(); }, [runs.data]);
  const anyActive = anyActiveRun(runs.data);        // a record a dead process left 'running' does not make this page ask every 2 s
  // Refresh by itself (every 2 s while anything runs, every 15 s otherwise, on focus) and tick the lease clocks every second while one runs.
  useLive(runs.reload, anyActive, useRegisteredStreams());
  useEffect(() => {
    if (!anyActive) return;
    const b = window.setInterval(() => tick(), 1000);
    return () => window.clearInterval(b);
  }, [anyActive]);

  if (runs.status === "error" && !runs.data) return <div className="page page--read kc-page"><ErrorState error={runs.error} retry={runs.reload} what="background agents" /></div>;
  if (!runs.data) return <div className="page page--read kc-page"><Loading label="Loading background agents" /></div>;
  const list = runs.data;
  const n = countStates(list);
  const elapsed = (Date.now() - loadedAt.current) / 1000;

  return (
    <div className="page page--read kc-page">
      <PageHead
        title={n.active > 0 ? `${n.active} background ${n.active === 1 ? "run is" : "runs are"} working` : "No background run is working"}
        lede="A planner splits a job into helpers."
        aside={<OriginBadge sources={[runs]} />}
      />
      <SourceNote why={runs.why} also={runs.why ? "These are example runs. Stop, Revoke and Run in background here only change this screen: nothing is started or stopped for real." : undefined} />

      {list.length === 0 ? (
        <EmptyState title="No background runs yet" body="A run works in an isolated copy and never applies a change without your approval." />
      ) : (
        <section className="stack" aria-label="Runs" style={{ gap: "var(--space-5)" }}>
          {(allRuns ? list : list.slice(0, 3)).map((r) => <Run key={r.run_id} run={r} elapsed={elapsed} onChanged={runs.reload} />)}
          {list.length > 3 && !allRuns && <div><button type="button" className="btn btn--secondary btn--sm" onClick={() => setAllRuns(true)}>Show all {list.length}</button></div>}
        </section>
      )}

      <Spawn onStarted={runs.reload} example={!!runs.why} />
    </div>
  );
}

/** A budget bar turns red only when a run that is still going, or that failed, has used it all: a run that finished within budget is not in trouble. */
function Bars({ b, s, state, only }: { b: AgentNode["budget"]; s: AgentNode["spent"]; state: string; only?: string }) {
  const finishedWell = state === "done" || state === "completed";
  return (
    <div className="budgets">
      {budgetBars(b, s).filter((x) => !only || x.key === only).map((x) => (
        <div key={x.key} className="budget" data-over={x.over && !finishedWell}>
          <span className="budget__label">{x.label}</span>
          <span className="budget__track" role="img" aria-label={`${x.label}: ${x.text}${x.over && !finishedWell ? ", all spent" : ""}`}><i style={{ width: `${x.frac * 100}%` }} /></span>
          <span className="budget__text tabular">{x.text}</span>
        </div>
      ))}
    </div>
  );
}

/** Everything about a node's limits sits behind one closed "More": every budget bar and, for a helper, its lease and tools. */
function More({ b, s, state, extra }: { b: AgentNode["budget"]; s: AgentNode["spent"]; state: string; extra?: React.ReactNode }) {
  return (
    <Details summary="More">
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <Bars b={b} s={s} state={state} />
        {extra}
      </div>
    </Details>
  );
}

/** True when a node that is still going has used a whole budget: the one thing about limits worth a word on the line itself. */
const spentUp = (b: AgentNode["budget"], s: AgentNode["spent"], state: string): boolean => !(state === "done" || state === "completed") && budgetBars(b, s).some((x) => x.over);

function Run({ run: r, elapsed, onChanged }: { run: AgentRun; elapsed: number; onChanged: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [allKids, setAllKids] = useState(false);
  const active = runActive(r);

  const act = async (what: string, fn: () => Promise<unknown>, done: string) => {
    setBusy(what); setErr(null);
    try { await fn(); toast({ tone: "success", text: done }); onChanged(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "That did not go through. Try again."); }
    finally { setBusy(null); }
  };

  return (
    <article className="run card card__pad" aria-labelledby={`run-${r.run_id}`}>
      <div className="run__head">
        <div className="stack" style={{ gap: "var(--space-1)" }}>
          <h2 className="run__title" id={`run-${r.run_id}`}>{kindLabel(r.kind)}</h2>
          <span className="t-data u-muted">{r.mode === "nightly" ? "Nightly" : "Foreground"} · started {fmtDateTime(r.started)}</span>
        </div>
        <div className="row">
          <span className="run__state" data-tone={stateTone(r.state)}>{r.state}</span>
          {active && <button type="button" className="btn btn--danger btn--sm" disabled={!!busy} onClick={() => act("stop", () => api.agentsStop(r.run_id), "Stop sent.")}>{busy === "stop" ? "Stopping" : "Stop"}</button>}
        </div>
      </div>

      {err && <p className="field__error" role="alert">{err}</p>}
      <Details summary="Helpers and result" onToggle={setOpen} wide>
      <ul className="tree" aria-label="Planner and helpers">
        <li className="tree__node tree__node--parent">
          <div className="tree__row">
            <span className="tree__role">{r.parent.role}</span>
            <StatePill state={r.parent.state} tone={stateTone(r.parent.state)} />
            {spentUp(r.parent.budget, r.parent.spent, r.parent.state) && <span className="u-muted">a budget is used up</span>}
          </div>
          <More b={r.parent.budget} s={r.parent.spent} state={r.parent.state} />
          <ul className="tree__children">
            {(allKids ? r.children : r.children.slice(0, 5)).map((c) => <Child key={c.id} runId={r.run_id} c={c} elapsed={elapsed} onChanged={onChanged} />)}
          </ul>
          {r.children.length > 5 && !allKids && <div><button type="button" className="btn btn--quiet btn--sm" onClick={() => setAllKids(true)}>Show all {r.children.length} helpers</button></div>}
        </li>
      </ul>

        {open && <Detail id={r.run_id} />}
      </Details>
    </article>
  );
}

function Child({ runId, c, elapsed, onChanged }: { runId: string; c: AgentNode; elapsed: number; onChanged: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const l = c.lease;
  const revoked = c.state === "revoked" || !!l?.revoked;
  const left = l ? leaseLeft(l, isActive(c.state) ? elapsed : l.remaining_s) : 0;
  const live = isActive(c.state) && !revoked;
  return (
    <li className="tree__node">
      <div className="tree__row">
        <span className="tree__role">{c.role}</span>
        <StatePill state={revoked ? "revoked" : c.state} tone={revoked ? "bad" : stateTone(c.state)} />
        {spentUp(c.budget, c.spent, c.state) && <span className="u-muted">a budget is used up</span>}
        {live && l && (
          <button type="button" className="btn btn--quiet btn--sm" disabled={busy} aria-label={`Revoke the lease of ${c.role}`}
            onClick={async () => { setBusy(true); setErr(null); try { await api.agentsRevoke(runId, c.id); toast({ tone: "success", text: `Revoked: ${c.role}.`, detail: "That helper ended at once." }); onChanged(); } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not revoke. Try again."); } finally { setBusy(false); } }}>
            {busy ? "Revoking" : "Revoke"}
          </button>
        )}
      </div>
      <More b={c.budget} s={c.spent} state={c.state} extra={l ? (
        <p className="lease" data-revoked={revoked}>
          <span className="t-label">Lease</span>{" "}
          {revoked ? <b>revoked, no tools in scope</b> : <>
            <b className="tabular">{live ? `${fmtClock(left)} left` : stopReason(l.stop_reason) ? `ended: ${stopReason(l.stop_reason)}` : "ended"}</b> · <span className="tabular">{l.steps_left} {l.steps_left === 1 ? "step" : "steps"} left</span> · tools: {l.tools.length ? l.tools.map((t) => <code key={t}>{t}</code>) : "none"}
          </>}
        </p>
      ) : undefined} />
      {revoked && <p className="note" data-testid="revoked-note">Revoked: this helper has no tools in scope.</p>}
      {err && <p className="field__error" role="alert">{err}</p>}
    </li>
  );
}

function Detail({ id }: { id: string }) {
  const d = useLoad(() => api.agentsRunDetail(id), [id]);
  if (d.status === "error" && !d.data) return <ErrorState error={d.error} retry={d.reload} what="this run's result" />;
  if (!d.data) return <Loading label="Loading the result" />;
  const steps = stepsOf(d.data.result);
  const kids = childResults(d.data.result);
  const rest = resultWithoutSteps(d.data.result);
  const tally = verifiedTally(d.data.result);
  const artifacts = Array.isArray(d.data.artifacts) ? d.data.artifacts : [];
  return (
    <div className="stack">
      <p className="note" data-testid="tally">{tally ? `${tally}.` : d.data.result == null ? "No result yet." : "Finished. The result is under More."}</p>
      {kids.map((k) => (
        <div key={k.id} className="stack child-result" data-claim={falseClaim(k) ? "false" : "ok"} style={{ gap: "var(--space-1)" }}>
          <div className="row">
            <b>{k.role.replace(/_/g, " ")}</b>
            <StatePill state={k.status} tone={stateTone(k.status)} />
            {k.verified === true && <span className="pill"><span className="pill__glyph-char" aria-hidden="true">✓</span>checked by code</span>}
            {k.verified === false && <span className="pill pill--blocked"><span className="pill__glyph-char" aria-hidden="true">✕</span>did not check out</span>}
          </div>
          {falseClaim(k) && <p className="field__error" role="alert">This helper said it succeeded, but the checks do not back that up. Do not rely on its output.</p>}
        </div>
      ))}
      <Details summary="More">
        <div className="stack">
          <KV label="This run" rows={[["Artifacts", artifacts.length === 0 ? "None yet" : String(artifacts.length)]]} />
          {artifacts.length > 0 && <ul className="plain-list">{artifacts.map((a) => <li key={`${a.name}-${a.path_ref}`} className="note"><b>{a.name}</b> <span className="pill">{a.kind}</span> <code>{a.path_ref}</code></li>)}</ul>}
          {kids.map((k) => (
            <div key={k.id} className="stack" style={{ gap: "var(--space-1)" }}>
              <span className="t-label">{k.role.replace(/_/g, " ")}</span>
              {k.checks.length > 0 && <ul className="plain-list">{k.checks.map((c) => <li key={c.name} className="note"><span aria-hidden="true">{c.ok ? "✓" : "✕"}</span> {c.name}{c.ok ? "" : " failed"}{c.detail ? <span className="u-muted"> ({c.detail})</span> : null}</li>)}</ul>}
              {k.steps.length > 0 && <ol className="steps">{k.steps.map((x, i) => <li key={i}><span>{x.label}</span>{x.check ? <CheckChip check={x.check} /> : <span className="pill">not checked</span>}</li>)}</ol>}
              {k.output != null && <Facts title="What it found" v={k.output} />}
            </div>
          ))}
          {steps.length > 0 && (
            <div className="stack" style={{ gap: "var(--space-1)" }}>
              <span className="t-label">Steps, each checked by code afterwards</span>
              <ol className="steps">{steps.map((x, i) => <li key={i}><span>{x.label}</span>{x.check ? <CheckChip check={x.check} /> : <span className="pill">not checked</span>}</li>)}</ol>
            </div>
          )}
          {d.data.result != null && <Facts title="Result" v={rest} />}
        </div>
      </Details>
    </div>
  );
}

function Spawn({ onStarted, example }: { onStarted: () => void; example: boolean }) {
  const toast = useToast();
  const kinds = useLoad(() => api.agentsKinds(), []);
  const list: AgentKind[] = kinds.data ?? [];
  const [kind, setKind] = useState<SpawnKind>("programming.commit_analyst");
  const current = list.find((k) => k.kind === kind) ?? list[0];
  useEffect(() => { if (list.length && !list.some((k) => k.kind === kind)) setKind(list[0].kind); }, [list, kind]);
  const [mode, setMode] = useState<"foreground" | "nightly">("foreground");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try { await api.agentsSpawn(kind, mode); toast({ tone: "success", text: "Started in the background.", detail: kindLabel(kind) }); onStarted(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not start it. Try again."); }
    finally { setBusy(false); }
  };
  return (
    <Details summary="Start a background run" wide>
      <div className="spawn">
        <div className="field">
          <label className="field__label" htmlFor="spawn-kind">Job</label>
          <select id="spawn-kind" className="select" value={kind} onChange={(e) => setKind(e.target.value as SpawnKind)}>
            {list.map((k) => <option key={k.kind} value={k.kind}>{k.title || kindLabel(k.kind)}</option>)}
          </select>
        </div>
        <p className="note" data-testid="spawn-describe">{current?.describe ?? KIND_DOES[kind] ?? ""}{current?.roles?.length ? ` Helpers: ${current.roles.map((r) => r.replace(/_/g, " ")).join(", ")}.` : ""} It runs in an isolated workspace on sample data.</p>
        <div className="field">
          <span className="field__label" id="spawn-mode">When<Hint label="What each choice does">{mode === "foreground" ? "Works while you work, steps aside the moment you touch the keyboard, and reports at a natural break." : "Waits for a quiet window when you are away, using the same start-or-wait rule as your other routines."}</Hint></span>
          <div className="segmented" role="group" aria-labelledby="spawn-mode">
            <button type="button" aria-pressed={mode === "foreground"} onClick={() => setMode("foreground")}>Foreground</button>
            <button type="button" aria-pressed={mode === "nightly"} onClick={() => setMode("nightly")}>Nightly</button>
          </div>
        </div>
        {err && <p className="field__error" role="alert">{err}</p>}
        <div className="row"><button type="button" className="btn btn--primary" disabled={busy || !current} onClick={go}>{busy ? "Starting" : "Run in background"}</button>{example && <span className="note">Example mode: this adds a pretend run to the list above.</span>}</div>
      </div>
    </Details>
  );
}
