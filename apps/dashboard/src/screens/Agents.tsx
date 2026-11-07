import { useEffect, useReducer, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { CheckChip, EmptyState, ErrorState, ExampleBadge, Loading, Note, OriginBadge, PageHead, SourceNote, StatePill } from "../components/common";
import { Facts } from "../components/Facts";
import { useToast } from "../components/Toasts";
import { KIND_DOES, budgetBars, childResults, countStates, falseClaim, fmtClock, isActive, kindLabel, leaseLeft, resultWithoutSteps, runActive, stateTone, stepsOf, stopReason, verifiedTally } from "../lib/agents";
import { fmtDateTime } from "../lib/format";
import type { AgentKind, AgentNode, AgentRun, SpawnKind } from "../types";

const POLL_MS = 3000;

export default function Agents() {
  const runs = useLoad(() => api.agentsRuns(), []);
  const loadedAt = useRef(Date.now());
  const [, tick] = useReducer((n: number) => n + 1, 0);

  useEffect(() => { loadedAt.current = Date.now(); }, [runs.data]);
  const anyActive = !!runs.data?.some(runActive);
  // While anything is running, refresh every 3 s and tick the lease clocks every second.
  useEffect(() => {
    if (!anyActive) return;
    const a = window.setInterval(() => runs.reload(), POLL_MS);
    const b = window.setInterval(() => tick(), 1000);
    return () => { window.clearInterval(a); window.clearInterval(b); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyActive]);

  if (runs.status === "error" && !runs.data) return <div className="page"><ErrorState error={runs.error} retry={runs.reload} what="background agents" /></div>;
  if (!runs.data) return <div className="page"><Loading label="Loading background agents" /></div>;
  const list = runs.data;
  const n = countStates(list);
  const elapsed = (Date.now() - loadedAt.current) / 1000;

  return (
    <div className="page">
      <PageHead
        eyebrow="Agents"
        title={n.active > 0 ? `${n.active} background ${n.active === 1 ? "run is" : "runs are"} working` : "No background run is working"}
        lede="A planner splits a job into a few small helpers. Each helper has a budget, a short lease on a few tools, and a workspace of its own. You can stop any run, or end one helper, at once."
        aside={<><OriginBadge meta={runs.meta} /><ExampleBadge why={runs.why} /></>}
      />
      <SourceNote why={runs.why} />
      {runs.why && <Note>These are example runs. Stop, Revoke and Run in background here only change this screen: nothing is started or stopped for real.</Note>}

      {list.length === 0 ? (
        <EmptyState title="No background runs yet" body="Start one below. It works in an isolated copy, reports what it found, and never applies a change without your approval." />
      ) : (
        <section className="stack" aria-label="Runs" style={{ gap: "var(--space-5)" }}>
          {list.map((r) => <Run key={r.run_id} run={r} elapsed={elapsed} onChanged={runs.reload} />)}
        </section>
      )}

      <hr className="rule" />
      <Spawn onStarted={runs.reload} example={!!runs.why} />
    </div>
  );
}

/** A budget bar turns red only when a run that is still going, or that failed, has used it all: a run that finished within budget is not in trouble. */
function Bars({ b, s, state }: { b: AgentNode["budget"]; s: AgentNode["spent"]; state: string }) {
  const finishedWell = state === "done" || state === "completed";
  return (
    <div className="budgets">
      {budgetBars(b, s).map((x) => (
        <div key={x.key} className="budget" data-over={x.over && !finishedWell}>
          <span className="budget__label">{x.label}</span>
          <span className="budget__track" role="img" aria-label={`${x.label}: ${x.text}${x.over && !finishedWell ? ", all spent" : ""}`}><i style={{ width: `${x.frac * 100}%` }} /></span>
          <span className="budget__text tabular">{x.text}</span>
        </div>
      ))}
    </div>
  );
}

function Run({ run: r, elapsed, onChanged }: { run: AgentRun; elapsed: number; onChanged: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
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
          <span className="t-data u-muted">{r.run_id} · started {fmtDateTime(r.started)}</span>
        </div>
        <div className="row">
          <span className="pill">{r.mode === "nightly" ? "Nightly" : "Foreground"}</span>
          <StatePill state={r.state} tone={stateTone(r.state)} />
          {active && <button type="button" className="btn btn--danger btn--sm" disabled={!!busy} onClick={() => act("stop", () => api.agentsStop(r.run_id), "Stop sent.")}>{busy === "stop" ? "Stopping" : "Stop"}</button>}
        </div>
      </div>

      <ul className="tree" aria-label="Planner and helpers">
        <li className="tree__node tree__node--parent">
          <div className="tree__row">
            <span className="tree__role">{r.parent.role}</span>
            <StatePill state={r.parent.state} tone={stateTone(r.parent.state)} />
          </div>
          <Bars b={r.parent.budget} s={r.parent.spent} state={r.parent.state} />
          <ul className="tree__children">
            {r.children.map((c) => <Child key={c.id} runId={r.run_id} c={c} elapsed={elapsed} onChanged={onChanged} />)}
          </ul>
        </li>
      </ul>

      {err && <p className="field__error" role="alert">{err}</p>}
      <details className="details-lite" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
        <summary>Artifacts and result</summary>
        {open && <Detail id={r.run_id} />}
      </details>
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
        {live && l && (
          <button type="button" className="btn btn--quiet btn--sm" disabled={busy} aria-label={`Revoke the lease of ${c.role}`}
            onClick={async () => { setBusy(true); setErr(null); try { await api.agentsRevoke(runId, c.id); toast({ tone: "success", text: `Revoked: ${c.role}.`, detail: "That helper ended at once." }); onChanged(); } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not revoke. Try again."); } finally { setBusy(false); } }}>
            {busy ? "Revoking" : "Revoke"}
          </button>
        )}
      </div>
      <Bars b={c.budget} s={c.spent} state={c.state} />
      {l && (
        <p className="lease" data-revoked={revoked}>
          <span className="t-label">Lease</span>{" "}
          {revoked ? <b>revoked, no tools in scope</b> : <>
            <b className="tabular">{live ? `${fmtClock(left)} left` : stopReason(l.stop_reason) ? `ended: ${stopReason(l.stop_reason)}` : "ended"}</b> · <span className="tabular">{l.steps_left} {l.steps_left === 1 ? "step" : "steps"} left</span> · tools: {l.tools.length ? l.tools.map((t) => <code key={t}>{t}</code>) : "none"}
          </>}
        </p>
      )}
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
  return (
    <div className="stack">
      <div className="stack" style={{ gap: "var(--space-1)" }}>
        <span className="t-label">Artifacts</span>
        {d.data.artifacts.length === 0 ? <p className="note">None yet.</p> : (
          <ul className="plain-list">{d.data.artifacts.map((a) => <li key={`${a.name}-${a.path_ref}`} className="note"><b>{a.name}</b> <span className="pill">{a.kind}</span> <code>{a.path_ref}</code></li>)}</ul>
        )}
      </div>
      {tally && <p className="note" data-testid="tally">{tally}.</p>}
      {kids.map((k) => (
        <div key={k.id} className="stack child-result" data-claim={falseClaim(k) ? "false" : "ok"}>
          <div className="row">
            <b>{k.role.replace(/_/g, " ")}</b>
            <StatePill state={k.status} tone={stateTone(k.status)} />
            {k.verified === true && <span className="pill"><span className="pill__glyph-char" aria-hidden="true">✓</span>checked by code</span>}
            {k.verified === false && <span className="pill pill--blocked"><span className="pill__glyph-char" aria-hidden="true">✕</span>did not check out</span>}
          </div>
          {falseClaim(k) && <p className="field__error" role="alert">This helper said it succeeded, but the checks below do not back that up. Do not rely on its output.</p>}
          {k.checks.length > 0 && (
            <ul className="plain-list">{k.checks.map((c) => <li key={c.name} className="note"><span aria-hidden="true">{c.ok ? "✓" : "✕"}</span> {c.name}{c.ok ? "" : " failed"}{c.detail ? <span className="u-muted"> ({c.detail})</span> : null}</li>)}</ul>
          )}
          {k.steps.length > 0 && (
            <details className="details-lite"><summary>{k.steps.length} steps, each checked by code afterwards</summary>
              <ol className="steps">{k.steps.map((s, i) => <li key={i}><span>{s.label}</span>{s.check ? <CheckChip check={s.check} /> : <span className="pill">not checked</span>}</li>)}</ol>
            </details>
          )}
          {k.output != null && <Facts title="What it found" v={k.output} />}
        </div>
      ))}
      {steps.length > 0 && (
        <div className="stack" style={{ gap: "var(--space-1)" }}>
          <span className="t-label">Steps, each checked by code afterwards</span>
          <ol className="steps">{steps.map((s, i) => <li key={i}><span>{s.label}</span>{s.check ? <CheckChip check={s.check} /> : <span className="pill">not checked</span>}</li>)}</ol>
        </div>
      )}
      {d.data.result == null ? <p className="note">No result yet.</p> : <Facts title="Result" v={rest} />}
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
    try { const r = await api.agentsSpawn(kind, mode); toast({ tone: "success", text: "Started in the background.", detail: `${kindLabel(kind)} · ${r.run_id}` }); onStarted(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not start it. Try again."); }
    finally { setBusy(false); }
  };
  return (
    <section className="section" aria-labelledby="spawn-h">
      <div className="section__head">
        <h2 className="section__title" id="spawn-h">Run in background</h2>
        <p className="section__sub">Pick a job. It runs in an isolated workspace on sample data, within its budgets.</p>
      </div>
      <div className="spawn">
        <div className="field">
          <label className="field__label" htmlFor="spawn-kind">Job</label>
          <select id="spawn-kind" className="select" value={kind} onChange={(e) => setKind(e.target.value as SpawnKind)}>
            {list.map((k) => <option key={k.kind} value={k.kind}>{k.title || kindLabel(k.kind)}</option>)}
          </select>
          <span className="field__hint">{current?.describe ?? KIND_DOES[kind] ?? ""}{current?.roles?.length ? ` Helpers: ${current.roles.map((r) => r.replace(/_/g, " ")).join(", ")}.` : ""}</span>
        </div>
        <div className="field">
          <span className="field__label" id="spawn-mode">When</span>
          <div className="segmented" role="group" aria-labelledby="spawn-mode">
            <button type="button" aria-pressed={mode === "foreground"} onClick={() => setMode("foreground")}>Foreground</button>
            <button type="button" aria-pressed={mode === "nightly"} onClick={() => setMode("nightly")}>Nightly</button>
          </div>
          <span className="field__hint">{mode === "foreground" ? "Works while you work, steps aside the moment you touch the keyboard, and reports at a natural break." : "Waits for a quiet window when you are away, using the same start-or-wait rule as your other routines."}</span>
        </div>
        {err && <p className="field__error" role="alert">{err}</p>}
        <div className="row"><button type="button" className="btn btn--primary" disabled={busy || !current} onClick={go}>{busy ? "Starting" : "Run in background"}</button>{example && <span className="note">Example mode: this adds a pretend run to the list above.</span>}</div>
      </div>
    </section>
  );
}
