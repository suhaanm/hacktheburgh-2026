import { useState } from "react";
import { ApiError, api, refreshQueueBadge } from "../api";
import { useLoad } from "../hooks";
import { ConsentPill, EmptyState, ErrorState, Loading, OriginBadge, PageHead, Range, RungPill } from "../components/common";
import { Ladder } from "../components/Ladder";
import { Hint } from "../components/Hint";
import { Brief, Details } from "../components/ui";
import { useToast } from "../components/Toasts";
import { fmtNum } from "../lib/format";
import type { Routine } from "../types";
import { APP_NAME } from "../brand";

export default function Routines() {
  const r = useLoad(() => api.routines(), []);
  const toast = useToast();
  const [leaving, setLeaving] = useState<string | null>(null);

  if (r.status === "error" && !r.data) return <div className="page"><ErrorState error={r.error} retry={r.reload} what="your routines" /></div>;
  if (!r.data) return <div className="page"><Loading label="Loading routines" /></div>;
  const proposals = r.data.filter((x) => x.status === "proposed");
  const active = r.data.filter((x) => ["shadow", "approval", "unattended"].includes(x.status));
  const closed = r.data.filter((x) => ["declined", "never"].includes(x.status));

  const decide = async (routine: Routine, body: Parameters<typeof api.setConsent>[1], done: string) => {
    await api.setConsent(routine.id, body);
    setLeaving(routine.id);
    window.setTimeout(() => { setLeaving(null); r.reload(); void refreshQueueBadge(); }, 380);
    toast({ tone: "success", text: done, detail: "You can change this any time from this page." });
  };

  return (
    <div className="page">
      <PageHead
        eyebrow="Routines"
        title={proposals.length ? (proposals.length === 1 ? "One routine is waiting for your decision" : `${proposals.length} routines are waiting for your decision`) : "Nothing is waiting for your decision"}
        lede="Suggested between tasks. Nothing runs until you say so."
        aside={<OriginBadge meta={r.meta} />}
      />

      {proposals.length ? (
        <section className="stack" aria-label="Proposed routines" style={{ gap: "var(--space-6)" }}>
          {proposals.map((p) => <Proposal key={p.id} routine={p} leaving={leaving === p.id} onDecide={decide} />)}
        </section>
      ) : (
        <EmptyState title="No new proposals" body={`When ${APP_NAME} sees the same steps three or more times, a proposal card appears here between tasks. You can say no, never, or watch first.`} />
      )}

      {active.length > 0 && (
        <section className="section" aria-labelledby="mine-h">
          <div className="section__head">
            <h2 id="mine-h" className="section__title">Your routines</h2>
            <p className="section__sub">Revoke stops a routine at once and sends it back to not now.</p>
          </div>
          <div>
            {active.map((x) => <RoutineRow key={x.id} routine={x} onRevoke={() => decide(x, { mode: "not_now" }, `${x.title} is revoked.`)} onChange={decide} />)}
          </div>
        </section>
      )}

      {closed.length > 0 && (
        <section className="section" aria-labelledby="closed-h">
          <h2 id="closed-h" className="section__title">Turned down</h2>
          <div>
            {closed.map((x) => (
              <div key={x.id} className="routine-row">
                <div className="routine-row__head">
                  <span className="routine-row__title">{x.title}</span>
                  <span className="routine-row__meta"><ConsentPill mode={x.status === "never" ? "never" : "not_now"} /></span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

type Decide = (routine: Routine, body: Parameters<typeof api.setConsent>[1], done: string) => Promise<void>;

interface Gate { mode: string; done: string; message: string }

/** The skill gate says the worker's own skill on this routine's steps is below level 4: coach it first, unless they say they know it. */
/** "coach first: ENTER_HOUSEHOLD at L1. Coach it first, ..." becomes a sentence; anything else is shown as the engine wrote it. */
function plainGate(message: string): string {
  const m = /coach first:\s*([A-Z_]+)\s+at\s+L(\d)/i.exec(message);
  if (!m) return message;
  return `Your skill at ${m[1].toLowerCase().replace(/_/g, " ")} is at level ${m[2]}. Automating starts at level 4.`;
}

function SkillGate({ gate, busy, onOverride, onDismiss }: { gate: Gate; busy: boolean; onOverride: () => void; onDismiss: () => void }) {
  return (
    <div className="note note--warn stack" role="alert" style={{ gap: "var(--space-3)" }}>
      <p><b>{APP_NAME} would rather coach you on this one first.</b> {plainGate(gate.message)}</p>
      <p>If you already know it well, say so. That is written into your memory file, and the routine still starts at the lowest rung.</p>
      <div className="row">
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={onOverride}>I already know this one</button>
        <button type="button" className="btn btn--quiet btn--sm" onClick={onDismiss}>Keep coaching me</button>
      </div>
    </div>
  );
}

function Proposal({ routine: p, leaving, onDecide }: { routine: Routine; leaving: boolean; onDecide: Decide }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const go = async (mode: string, done: string, override = false) => {
    setBusy(mode); setErr(null); setGate(null);
    try { await onDecide(p, { mode, ...(override ? { skill_override: true } : {}) }, done); }
    catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate({ mode, done, message: e.message });
      else setErr(e instanceof ApiError ? e.message : "That did not save. Try again.");
    } finally { setBusy(null); }
  };
  const [lo, hi] = p.value.hours_saved;
  const sentences = p.proposal.what.split(/(?<=[.!?])\s+/);
  const whatFirst = sentences[0] ?? p.proposal.what;
  const whatRest = sentences.slice(1).join(" ");
  const horizon = p.value.horizon_weeks ? ` over ${p.value.horizon_weeks} weeks` : "";
  return (
    <article className={`proposal ${leaving ? "proposal--leaving" : "proposal--arriving"}`} aria-labelledby={`pt-${p.id}`}>
      <div className="proposal__head">
        <h2 className="proposal__title" id={`pt-${p.id}`}>{p.title}</h2>
        {p.rung !== "A0" && <RungPill rung={p.rung} />}
      </div>
      <p className="proposal__what">{whatFirst}</p>
      <dl className="proposal__facts">
        <div><dt>How often<Hint label="About how often">About {p.minutes_per_week} minutes a week.</Hint></dt><dd>{p.proposal.how_often}</dd></div>
        <div>
          <dt>Hours saved</dt>
          <dd><span className="stat__value tabular" style={{ fontSize: "var(--text-2xl)" }}>{fmtNum(lo, 1)} to {fmtNum(hi, 1)}</span> <span className="u-muted">h{horizon}</span><Hint label="About the hours saved">95% interval. About £{p.value.net_gbp[0]} to £{p.value.net_gbp[1]} net of set-up.</Hint></dd>
          <dd><Range lo={lo} hi={hi} pt={(lo + hi) / 2} min={0} max={Math.ceil(hi * 1.3)} /></dd>
        </div>
      </dl>
      <div className="stack" style={{ gap: "var(--space-1)" }}>
        <Brief lead="It touches" items={p.proposal.touches} show={2} />
        <Brief lead="It will never" items={p.proposal.never} show={p.proposal.never.length} />
      </div>
      <div className="choices" role="group" aria-label="Your choice">
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => go("not_now", "Okay, not now.")}>Not now</button><p>Ask me again later.</p></div>
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => go("never", "Okay. This will not be suggested again.")}>Never for this</button><p>Stop suggesting this.</p></div>
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => go("shadow", "Watching first.")}>Watch first</button><p>It practises beside you. Nothing is saved or sent.</p></div>
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => go("approval", "Set to run with your approval.")}>Run with my approval</button><p>It works in the background and asks before anything outward.</p></div>
      </div>
      <Details summary="Why this?">
        {whatRest && <p>{whatRest}</p>}
        <p>Whatever you choose, it starts at {p.rung} and moves up only as its record earns it. Rung A2 needs 20 shadow runs and a lower bound of 0.80.</p>
      </Details>
      {gate && <SkillGate gate={gate} busy={!!busy} onOverride={() => go(gate.mode, gate.done, true)} onDismiss={() => setGate(null)} />}
      {err && <p className="field__error" role="alert">{err}</p>}
      <Away routine={p} onDecide={onDecide} />
    </article>
  );
}

/** "Run while I'm away" is its own opt-in. Irreversible classes need an explicit second opt-in. */
function Away({ routine: p, onDecide }: { routine: Routine; onDecide: Decide }) {
  const classes = p.irreversible_classes ?? [];
  const [on, setOn] = useState(p.status === "unattended");
  const [allowed, setAllowed] = useState<string[]>(p.consent.irreversible_unattended ?? []);
  const [typed, setTyped] = useState("");
  const [ack, setAck] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [busy, setBusy] = useState(false);
  const model = p.driver === "model";
  const irreversible = allowed.length > 0;
  const ready = on && (!irreversible || (model ? typed === p.id : ack));

  const save = async (override = false) => {
    setBusy(true); setErr(null); setGate(null);
    const done = "Set to run while you are away.";
    try { await onDecide(p, { mode: "unattended", irreversible_unattended: allowed, typed_confirm: typed, ...(override ? { skill_override: true } : {}) }, done); }
    catch (e) {
      if (e instanceof ApiError && e.code === "skill_gate") setGate({ mode: "unattended", done, message: e.message });
      else setErr(e instanceof ApiError ? e.message : "That did not save. Try again.");
    }
    finally { setBusy(false); }
  };

  return (
    <details className="away">
      <summary className="why" style={{ cursor: "pointer" }}><span className="t-label">Separate choice</span> <b>Run while I'm away</b> <span className="u-muted">(off)</span></summary>
      <div className="stack" style={{ marginTop: "var(--space-4)" }}>
        <p className="note">Off by default. It runs only in away windows, never in quiet hours, and stops within a second of you touching the keyboard.</p>
        <label className="toggle">
          <input type="checkbox" role="switch" checked={on} onChange={(e) => setOn(e.target.checked)} />
          <span className="toggle__track" />
          <span className="toggle__text">Let this routine run while I'm away</span>
        </label>
        {on && classes.length > 0 && (
          <fieldset style={{ border: 0, padding: 0, margin: 0 }} className="stack">
            <legend className="field__label">Steps that cannot be undone</legend>
            <p className="note">By default these wait in your morning queue for a click. Allow one only if you are sure.</p>
            {classes.map((c) => (
              <label key={c} className="toggle">
                <input type="checkbox" role="switch" checked={allowed.includes(c)} onChange={(e) => setAllowed((a) => (e.target.checked ? [...a, c] : a.filter((x) => x !== c)))} />
                <span className="toggle__track" />
                <span className="toggle__text">Allow “{c}” without asking me</span>
              </label>
            ))}
          </fieldset>
        )}
        {on && irreversible && (
          <div className="stack">
            <div className="banner" role="note"><span className="banner__mark" aria-hidden="true" />
              <p>{model ? "This routine is driven by a model, which can misread a page. An irreversible step could go wrong with nobody watching." : "This is a recorded script. It repeats exactly what you did, so an irreversible step cannot be taken back."}</p>
            </div>
            {model ? (
              <div className="field">
                <label className="field__label" htmlFor={`tc-${p.id}`}>Type <code>{p.id}</code> to confirm</label>
                <input id={`tc-${p.id}`} className="input" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} aria-invalid={typed.length > 0 && typed !== p.id} />
              </div>
            ) : (
              <label className="toggle"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /><span className="toggle__track" /><span className="toggle__text">I understand this cannot be undone</span></label>
            )}
          </div>
        )}
        {gate && <SkillGate gate={gate} busy={busy} onOverride={() => save(true)} onDismiss={() => setGate(null)} />}
        {err && <p className="field__error" role="alert">{err}</p>}
        <div className="row"><button type="button" className="btn btn--secondary" disabled={!ready || busy} onClick={() => save()}>Allow while I'm away</button></div>
      </div>
    </details>
  );
}

function RoutineRow({ routine: x, onRevoke, onChange }: { routine: Routine; onRevoke: () => Promise<void>; onChange: Decide }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="routine-row">
      <div className="routine-row__head">
        <span className="routine-row__title">{x.title}</span>
        <span className="routine-row__meta"><ConsentPill mode={x.status} /><RungPill rung={x.rung} /></span>
      </div>
      <p className="note">{x.proposal.how_often}. It touches {x.touches.join(", ")}. It will never {x.never.join(" or ")}.</p>
      <Details summary="Autonomy and record" defaultOpen={x.status === "shadow"} wide>
        <Ladder routine={x} />
        <div style={{ marginTop: "var(--space-5)" }}><Away routine={x} onDecide={onChange} /></div>
      </Details>
      <div className="row">
        <button type="button" className="btn btn--danger btn--sm" disabled={busy} onClick={async () => { setBusy(true); try { await onRevoke(); } finally { setBusy(false); } }}>Revoke</button>
      </div>
    </div>
  );
}
