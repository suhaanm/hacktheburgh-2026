import { useState } from "react";
import { ApiError, api, refreshQueueBadge } from "../api";
import { useLoad } from "../hooks";
import { EmptyState, ErrorState, Loading, OriginBadge, PageHead } from "../components/common";
import { useToast } from "../components/Toasts";
import { KIND_LABEL, RISK_LABEL, cleanPrepared, expiresIn, firedText, preparedDirty } from "../lib/briefing";
import type { BriefingCard, Prepared } from "../types";

export default function Briefing() {
  const b = useLoad(() => api.briefing(), []);
  if (b.status === "error" && !b.data) return <div className="page"><ErrorState error={b.error} retry={b.reload} what="your briefing" /></div>;
  if (!b.data) return <div className="page"><Loading label="Loading your briefing" /></div>;
  const cap = b.data.cap ?? 3;
  const cards = b.data.cards;
  const ready = cards.filter((c) => c.status === "ready").slice(0, cap);
  const stale = cards.filter((c) => c.status === "stale");
  const done = cards.filter((c) => c.status === "fired" || c.status === "dismissed");

  return (
    <div className="page">
      <PageHead
        eyebrow="Briefing"
        title={ready.length === 0 ? "Nothing worth your time today" : ready.length === 1 ? "One thing worth your time today" : `${ready.length} things worth your time today`}
        lede={`At most ${cap} cards, and fewer is normal. Each one is prepared for you to edit. Nothing happens until you press a button.`}
        aside={<OriginBadge meta={b.meta} />}
      />

      {ready.length === 0 ? (
        <EmptyState title="Nothing worth your time today" body={`Understudy only shows a card when it is clearly worth it, and never more than ${cap}. Check back tomorrow.`} />
      ) : (
        <section className="stack" aria-label="Today's cards" style={{ gap: "var(--space-6)" }}>
          {ready.map((c) => <Card key={c.id} card={c} onChanged={() => { b.reload(); void refreshQueueBadge(); }} />)}
        </section>
      )}

      {stale.length > 0 && (
        <section className="section" aria-labelledby="stale-h">
          <h2 className="section__title" id="stale-h">Out of date</h2>
          <p className="note">These were dropped because the situation changed since they were prepared.</p>
          {stale.map((c) => <p key={c.id} className="note"><b>{c.title}</b></p>)}
        </section>
      )}

      {done.length > 0 && (
        <section className="section" aria-labelledby="done-h">
          <h2 className="section__title" id="done-h">Done today</h2>
          <div>
            {done.map((c) => (
              <div key={c.id} className="routine-row">
                <div className="routine-row__head"><span className="routine-row__title">{c.title}</span><span className="pill">{c.status === "fired" ? "Pressed" : "Dismissed"}</span></div>
                {c.status === "fired" && <p className="note" data-testid="fired">{firedText(c.fired)}</p>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Card({ card: c, onChanged }: { card: BriefingCard; onChanged: () => void }) {
  const toast = useToast();
  const [draft, setDraft] = useState<Prepared>({ text: c.prepared.text, steps: c.prepared.steps ? [...c.prepared.steps] : undefined, artifact_ref: c.prepared.artifact_ref });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const dirty = preparedDirty(draft, c.prepared);
  const hasSteps = Array.isArray(draft.steps);
  const hasText = typeof draft.text === "string";

  const save = async () => { await api.briefingEdit(c.id, cleanPrepared(draft)); };
  const run = async (what: string, fn: () => Promise<void>) => {
    setBusy(what); setErr(null);
    try { await fn(); } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not go through. Try again."); } finally { setBusy(null); }
  };

  return (
    <article className="proposal" aria-labelledby={`bc-${c.id}`}>
      <div className="proposal__head">
        <h2 className="proposal__title" id={`bc-${c.id}`}>{c.title}</h2>
        <span className="pill" data-risk={c.risk_class} style={c.risk_class === "irreversible" ? { borderColor: "var(--bad)" } : undefined}>{RISK_LABEL[c.risk_class] ?? c.risk_class}</span>
        <span className="pill">{KIND_LABEL[c.kind] ?? c.kind}</span>
      </div>
      <div className="stack">
        <p className="t-label">Why this</p>
        <p className="proposal__what">{c.why}</p>
      </div>

      <div className="stack prepared">
        <p className="t-label">Prepared for you. Edit it if you like.</p>
        {hasText && (
          <div className="field">
            <label className="u-sr-only" htmlFor={`pt-${c.id}`}>Prepared text</label>
            <textarea id={`pt-${c.id}`} className="textarea" rows={3} value={draft.text ?? ""} onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
          </div>
        )}
        {hasSteps && (
          <ol className="prepared__steps">
            {(draft.steps ?? []).map((s, i) => (
              <li key={i}>
                <label className="u-sr-only" htmlFor={`ps-${c.id}-${i}`}>Step {i + 1}</label>
                <input id={`ps-${c.id}-${i}`} className="input" value={s} onChange={(e) => setDraft({ ...draft, steps: (draft.steps ?? []).map((x, j) => (j === i ? e.target.value : x)) })} />
                <button type="button" className="btn btn--quiet btn--sm" aria-label={`Remove step ${i + 1}`} onClick={() => setDraft({ ...draft, steps: (draft.steps ?? []).filter((_, j) => j !== i) })}>Remove</button>
              </li>
            ))}
            <li className="prepared__add"><button type="button" className="btn btn--quiet btn--sm" onClick={() => setDraft({ ...draft, steps: [...(draft.steps ?? []), ""] })}>Add a step</button></li>
          </ol>
        )}
        {dirty && (
          <div className="row">
            <button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => run("save", async () => { await save(); toast({ tone: "success", text: "Your edit is saved." }); onChanged(); })}>{busy === "save" ? "Saving" : "Save my edit"}</button>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setDraft({ text: c.prepared.text, steps: c.prepared.steps ? [...c.prepared.steps] : undefined })}>Undo my edit</button>
          </div>
        )}
      </div>

      <dl className="proposal__facts">
        <div><dt>Comes from</dt><dd className="row" style={{ gap: "var(--space-1)" }}>{c.sources.map((s) => <span key={s} className="pill">{s}</span>)}</dd></div>
        <div><dt>Expires</dt><dd>{expiresIn(c.expires_at)}</dd></div>
      </dl>

      <div className="choices" role="group" aria-label="Your choice">
        <div className="choice"><button type="button" className="btn btn--primary" disabled={!!busy} onClick={() => run("fire", async () => {
          if (dirty) await save(); // what runs is what you see
          const r = await api.briefingFire(c.id);
          toast({ tone: "success", text: "Done.", detail: firedText(r) });
          onChanged();
        })}>{busy === "fire" ? "Working" : "Approve and run"}</button><p>Nothing happens until you press this. It either creates an approval item for you to confirm, or starts a background run, and this card will say which.{dirty ? " Your edit is saved first." : ""}</p></div>
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => run("later", async () => { await api.briefingDismiss(c.id, "not_now"); toast({ tone: "plain", text: "Okay, not now." }); onChanged(); })}>Not now</button><p>Put this away. It may come back if it is still worth it.</p></div>
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => run("never", async () => { await api.briefingDismiss(c.id, "never"); toast({ tone: "plain", text: "Okay. This will not be suggested again." }); onChanged(); })}>Never for this</button><p>Do not suggest this again.</p></div>
      </div>
      {err && <p className="field__error" role="alert">{err}</p>}
    </article>
  );
}
