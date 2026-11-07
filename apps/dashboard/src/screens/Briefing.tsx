import { useState } from "react";
import { ApiError, api, refreshQueueBadge } from "../api";
import { useLoad } from "../hooks";
import { useAppState } from "../store";
import { EmptyState, ErrorState, ExampleBadge, Loading, OriginBadge, PageHead, SourceNote } from "../components/common";
import { Hint } from "../components/Hint";
import { Details } from "../components/ui";
import { useToast } from "../components/Toasts";
import { KIND_LABEL, RISK_LABEL, checkedNote, cleanPrepared, expiresIn, fireRisk, fireWhat, firedText, preparedDirty, rankingParts } from "../lib/briefing";
import type { BriefingCard, Prepared } from "../types";
import { APP_NAME } from "../brand";

const DEMO_PERSON = "p_ninetofive";
/** About one row per 80 characters, never fewer than `min` or more than 10, so the whole text is visible while editing. */
const rowsFor = (t: string, min: number) => Math.min(10, Math.max(min, Math.ceil(t.length / 80) + 1));
type Fired = { queue_id?: string; run_id?: string };

export default function Briefing() {
  const me = useAppState().person;
  const person = me ?? DEMO_PERSON;
  const b = useLoad(() => api.briefing(person), [person]);
  // What this visit pressed, kept here so the confirmation stays even when the engine drops a fired card from its next list.
  const [pressed, setPressed] = useState<Record<string, { title: string; fired: Fired }>>({});
  const [dismissedHere, setDismissedHere] = useState<Record<string, string>>({});
  if (b.status === "error" && !b.data) return <div className="page"><ErrorState error={b.error} retry={b.reload} what="your briefing" /></div>;
  if (!b.data) return <div className="page"><Loading label="Loading your briefing" /></div>;
  const cap = b.data.cap ?? 3;
  const cards = b.data.cards;
  const ready = cards.filter((c) => c.status === "ready" && !pressed[c.id] && !dismissedHere[c.id]).slice(0, cap);
  const stale = cards.filter((c) => c.status === "stale");
  const doneServer = cards.filter((c) => (c.status === "fired" || c.status === "dismissed") && !pressed[c.id] && !dismissedHere[c.id]);
  const example = !!b.why;

  return (
    <div className="page">
      <PageHead
        eyebrow="Briefing"
        title={ready.length === 0 ? "Nothing worth your time today" : ready.length === 1 ? "One thing worth your time today" : `${ready.length} things worth your time today`}
        lede={`Up to ${cap} cards. Nothing happens until you press a button.`}
        aside={<><OriginBadge meta={b.meta} /><ExampleBadge why={b.why} /></>}
      />
      <SourceNote why={b.why} also={example ? "These are example cards. A button here only changes this screen, and nothing is created in the Queue or started as a run." : undefined} />

      {ready.length === 0 ? (
        <EmptyState title="Nothing worth your time today" body={`${APP_NAME} only shows a card when it is clearly worth it, and never more than ${cap}. Check back tomorrow.`} />
      ) : (
        <section className="stack" aria-label="Today's cards" style={{ gap: "var(--space-6)" }}>
          {ready.map((c) => (
            <Card key={c.id} card={c} person={person}
              onFired={(f) => { setPressed((p) => ({ ...p, [c.id]: { title: c.title, fired: f } })); void refreshQueueBadge(); }}
              onDismissed={(mode) => setDismissedHere((d) => ({ ...d, [c.id]: mode }))}
              onChanged={() => { b.reload(); void refreshQueueBadge(); }} />
          ))}
        </section>
      )}

      {stale.length > 0 && (
        <section className="section" aria-labelledby="stale-h">
          <h2 className="section__title" id="stale-h">Out of date</h2>
          <p className="note">These were dropped because the situation changed since they were prepared.</p>
          {stale.map((c) => <p key={c.id} className="note"><b>{c.title}</b>{c.verify_note ? ` — ${c.verify_note}` : ""}</p>)}
        </section>
      )}

      {(Object.keys(pressed).length > 0 || Object.keys(dismissedHere).length > 0 || doneServer.length > 0) && (
        <section className="section" aria-labelledby="done-h">
          <h2 className="section__title" id="done-h">Done today</h2>
          <div>
            {Object.entries(pressed).map(([id, p]) => (
              <div key={id} className="routine-row">
                <div className="routine-row__head"><span className="routine-row__title">{p.title}</span><span className="pill">Pressed</span></div>
                <p className="note" data-testid="fired">{firedText(p.fired)} {p.fired.queue_id && <a href="#/queue">Open the Queue</a>}{p.fired.run_id && <a href="#/agents">Open Agents</a>}</p>
              </div>
            ))}
            {Object.entries(dismissedHere).map(([id, mode]) => (
              <div key={id} className="routine-row">
                <div className="routine-row__head"><span className="routine-row__title">{cards.find((c) => c.id === id)?.title ?? id}</span><span className="pill">{mode === "never" ? "Never for this" : "Not now"}</span></div>
              </div>
            ))}
            {doneServer.map((c) => (
              <div key={c.id} className="routine-row">
                <div className="routine-row__head"><span className="routine-row__title">{c.title}</span><span className="pill">{c.status === "fired" ? "Pressed" : c.dismissed?.mode === "never" ? "Never for this" : "Dismissed"}</span></div>
                {c.status === "fired" && <p className="note" data-testid="fired">{firedText(c.fired ?? undefined)}</p>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Card({ card: c, person, onFired, onDismissed, onChanged }: { card: BriefingCard; person: string; onFired: (f: Fired) => void; onDismissed: (mode: "not_now" | "never") => void; onChanged: () => void }) {
  void person;
  const toast = useToast();
  const [draft, setDraft] = useState<Prepared>({ text: c.prepared.text, steps: c.prepared.steps ? [...c.prepared.steps] : undefined, artifact_ref: c.prepared.artifact_ref });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const dirty = preparedDirty(draft, c.prepared);
  const hasSteps = Array.isArray(draft.steps);
  const hasText = typeof draft.text === "string";
  const checked = checkedNote(c);
  const parts = rankingParts(c.ranking);

  const save = async () => { await api.briefingEdit(c.id, cleanPrepared(draft)); };
  const run = async (what: string, fn: () => Promise<void>) => {
    setBusy(what); setErr(null);
    try { await fn(); }
    catch (e) {
      setErr(e instanceof ApiError ? e.message : "That did not go through. Try again.");
      // A card that went out of date was dropped by the engine: show the list as it is now.
      if (e instanceof ApiError && (e.status === 409 || e.status === 410)) onChanged();
    } finally { setBusy(null); }
  };

  return (
    <article className="proposal" aria-labelledby={`bc-${c.id}`}>
      <div className="proposal__head">
        <h2 className="proposal__title" id={`bc-${c.id}`}>{c.title}</h2>
        {c.risk_class !== "normal" && <span className="pill" data-risk={c.risk_class} style={c.risk_class === "irreversible" ? { borderColor: "var(--bad)" } : undefined}>{RISK_LABEL[c.risk_class] ?? c.risk_class}</span>}
        {c.edited && <span className="pill">edited by you</span>}
      </div>
      <div className="stack">
        <p className="t-label">Why this</p>
        <p className="proposal__what">{c.why}</p>
        {checked && <p className="note" data-testid="checked">{checked}</p>}
      </div>

      <div className="stack prepared">
        <div className="row row--between">
          <p className="t-label">{editing ? "Prepared for you. Edit it if you like." : "Prepared for you"}</p>
          {!editing && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setEditing(true)}>Edit what will happen</button>}
        </div>
        {!editing && (
          <div className="stack" style={{ gap: "var(--space-2)" }}>
            {hasText && <p className="prepared__text">{draft.text}</p>}
            {hasSteps && (draft.steps ?? []).length > 0 && <ol className="prepared__read">{(draft.steps ?? []).map((st, i) => <li key={i}>{st}</li>)}</ol>}
          </div>
        )}
        {editing && hasText && (
          <div className="field">
            <label className="u-sr-only" htmlFor={`pt-${c.id}`}>Prepared text</label>
            <textarea id={`pt-${c.id}`} className="textarea" rows={rowsFor(draft.text ?? "", 3)} value={draft.text ?? ""} onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
          </div>
        )}
        {editing && hasSteps && (
          <ol className="prepared__steps">
            {(draft.steps ?? []).map((st, i) => (
              <li key={i}>
                <label className="u-sr-only" htmlFor={`ps-${c.id}-${i}`}>Step {i + 1}</label>
                <textarea id={`ps-${c.id}-${i}`} className="textarea" rows={rowsFor(st, 2)} value={st} onChange={(e) => setDraft({ ...draft, steps: (draft.steps ?? []).map((x, j) => (j === i ? e.target.value : x)) })} />
                <button type="button" className="btn btn--quiet btn--sm" aria-label={`Remove step ${i + 1}`} onClick={() => setDraft({ ...draft, steps: (draft.steps ?? []).filter((_, j) => j !== i) })}>Remove</button>
              </li>
            ))}
            <li className="prepared__add"><button type="button" className="btn btn--quiet btn--sm" onClick={() => setDraft({ ...draft, steps: [...(draft.steps ?? []), ""] })}>Add a step</button></li>
          </ol>
        )}
        {editing && (
          <div className="row">
            {dirty && <button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => run("save", async () => { await save(); toast({ tone: "success", text: "Your edit is saved." }); setEditing(false); onChanged(); })}>{busy === "save" ? "Saving" : "Save my edit"}</button>}
            {dirty && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setDraft({ text: c.prepared.text, steps: c.prepared.steps ? [...c.prepared.steps] : undefined })}>Undo my edit</button>}
            {!dirty && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setEditing(false)}>Done editing</button>}
          </div>
        )}
      </div>

      <p className="note" data-testid="card-from">{KIND_LABEL[c.kind] ?? c.kind} from {c.sources.join(", ")}, {expiresIn(c.expires_at) === "expired" ? "expired" : `expires ${expiresIn(c.expires_at)}`}.{c.wording === "model" ? " Reworded by a model from safe numbers." : ""}</p>

      {parts.length > 0 && (
        <Details summary={`How this card was chosen${typeof c.ranking?.score === "number" ? `: score ${c.ranking.score.toFixed(2)}` : ""}${c.ranking?.rank ? `, rank ${c.ranking.rank}` : ""}`} wide>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Part</th><th className="num">Weight</th><th className="num">Added to the score</th></tr></thead>
            <tbody>{parts.map((p) => <tr key={p.key}><td>{p.label}</td><td className="num">{p.weight > 0 ? "+" : "−"}{Math.abs(p.weight).toFixed(2)}</td><td className="num">{p.contribution >= 0 ? "+" : "−"}{Math.abs(p.contribution).toFixed(3)}</td></tr>)}</tbody>
          </table></div>
          <p className="note">Code adds these up. A card shows only if its score clears {c.ranking?.min_score ?? "the minimum"}, and no model decides.</p>
        </Details>
      )}

      <div className="choices" role="group" aria-label="Your choice">
        <div className="choice"><button type="button" className="btn btn--primary" disabled={!!busy} onClick={() => run("fire", async () => {
          if (dirty) await save(); // what runs is what you see
          const r = await api.briefingFire(c.id);
          toast({ tone: "success", text: "Done.", detail: firedText(r) });
          onFired(r);
        })}>{busy === "fire" ? "Working" : "Approve and run"}</button><p>Nothing happens until you press this.<Hint label="What pressing does">{fireWhat(c.fire_type)}{dirty ? " Your edit is saved first." : ""}</Hint>{fireRisk(c.risk_class) && <span className="choice__risk"> {fireRisk(c.risk_class)}</span>}</p></div>
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => run("later", async () => { await api.briefingDismiss(c.id, "not_now"); toast({ tone: "plain", text: "Okay, not now." }); onDismissed("not_now"); })}>Not now</button><p>Put this away. It may come back if it is still worth it.</p></div>
        <div className="choice"><button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => run("never", async () => { await api.briefingDismiss(c.id, "never"); toast({ tone: "plain", text: "Okay. This will not be suggested again." }); onDismissed("never"); })}>Never for this</button><p>Do not suggest this kind of card from these sources again.</p></div>
      </div>
      {err && <p className="field__error" role="alert">{err}</p>}
    </article>
  );
}
