import { useState } from "react";
import { ApiError, api } from "../../api";
import { checkedNote, cleanPrepared, expiresIn, firedText, preparedDirty, rankingParts } from "../../lib/briefing";
import { consequence, leadAndRest, plainWords } from "../../screens/NeedsYou/model";
import type { BriefingCard, Prepared } from "../../types";
import { useToast } from "../Toasts";
import { Details } from "../ui";
import { Glyph } from "./Glyph";

type Fired = { queue_id?: string; run_id?: string };

/** About one row per 80 characters, never fewer than `min` or more than 10, so the whole text is visible while editing. */
const rowsFor = (t: string, min: number) => Math.min(10, Math.max(min, Math.ceil(t.length / 80) + 1));

/** What pressing "Approve and run" does, in one printed line, by the card's fire type. Stated before the press, so there is no surprise. */
export function fireLine(fireType: string | undefined): string {
  switch (fireType) {
    case "queue": return "Creates an item here for your approval. Nothing runs until you approve it.";
    case "draft": return "Saves a local draft and creates an item here for your approval.";
    case "agent": return "Starts a background run that only reads.";
    default: return "Creates an item for your approval, or starts a read-only run.";
  }
}

/**
 * A prepared action (a briefing card) as one row: why, what pressing does, its consequence, three choices of one size. What will happen is one click away,
 * editable, and what runs is exactly what is shown. Never more than three of these are prepared a day.
 */
export function PreparedRow({ card: c, onFired, onDismissed, onChanged }: { card: BriefingCard; onFired: (f: Fired, title: string) => void; onDismissed: (mode: "not_now" | "never") => void; onChanged: () => void }) {
  const toast = useToast();
  const [draft, setDraft] = useState<Prepared>({ text: c.prepared.text, steps: c.prepared.steps ? [...c.prepared.steps] : undefined, artifact_ref: c.prepared.artifact_ref });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const dirty = preparedDirty(draft, c.prepared);
  const hasSteps = Array.isArray(draft.steps);
  const hasText = typeof draft.text === "string";
  const checked = checkedNote(c);
  const parts = rankingParts(c.ranking);
  const cons = consequence(c.risk_class);
  const { lead } = leadAndRest(c.why);

  const save = async () => { await api.briefingEdit(c.id, cleanPrepared(draft)); };
  const run = async (what: string, fn: () => Promise<void>) => {
    setBusy(what); setErr(null);
    try { await fn(); }
    catch (e) {
      setErr(e instanceof ApiError ? e.message : "That did not go through. Nothing was changed. Try again.");
      // A card that went out of date was dropped by the engine: show the list as it is now.
      if (e instanceof ApiError && (e.status === 409 || e.status === 410)) onChanged();
    } finally { setBusy(null); }
  };

  return (
    <article className="kc-row" data-kind="prepared" data-cls="2" data-risk={c.risk_class} aria-labelledby={`ny-${c.id}`}>
      <h3 className="kc-row__title" id={`ny-${c.id}`}>
        <Glyph name="decision" />
        <span>{plainWords(c.title)}</span>
        <span className="kc-row__when">{expiresIn(c.expires_at) === "expired" ? "expired" : `expires ${expiresIn(c.expires_at)}`}</span>
      </h3>
      <p className="kc-row__body">{lead}</p>
      <p className="kc-row__meta">{fireLine(c.fire_type)}</p>
      {cons && <p className="kc-row__cons" data-testid="consequence">{cons} It stops here for your own click first.</p>}
      {err && <p className="kc-error" role="alert">{err}</p>}
      <div className="kc-row__actions" role="group" aria-label="Your choice">
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void run("fire", async () => {
          if (dirty) await save(); // what runs is what you see
          const r = await api.briefingFire(c.id);
          toast({ tone: "success", text: "Done.", detail: firedText(r) });
          onFired(r, c.title);
        })}>{busy === "fire" ? "Working" : "Approve and run"}</button>
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void run("later", async () => { await api.briefingDismiss(c.id, "not_now"); toast({ tone: "plain", text: "Okay, not now." }); onDismissed("not_now"); })}>Not now</button>
        <button type="button" className="btn btn--secondary" disabled={!!busy} onClick={() => void run("never", async () => { await api.briefingDismiss(c.id, "never"); toast({ tone: "plain", text: "Okay. This will not be suggested again." }); onDismissed("never"); })}>Never</button>
        <button type="button" className="kc-link" data-toggle aria-expanded={open} aria-controls={`pv-${c.id}`} onClick={() => setOpen((v) => !v)}>What will happen<Glyph name="chevron" /></button>
      </div>
      {open && (
        <div className="kc-panel" id={`pv-${c.id}`}>
          {checked && <p data-testid="checked">{checked}</p>}
          <div className="row row--between">
            <p className="kc-label">{editing ? "Prepared for you. Edit it if you like." : "Prepared for you"}</p>
            {!editing && <button type="button" className="btn btn--secondary btn--sm" onClick={() => setEditing(true)}>Edit what will happen</button>}
          </div>
          {!editing && (
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
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
              {dirty && <button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => void run("save", async () => { await save(); toast({ tone: "success", text: "Your edit is saved." }); setEditing(false); onChanged(); })}>{busy === "save" ? "Saving" : "Save my edit"}</button>}
              {dirty && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setDraft({ text: c.prepared.text, steps: c.prepared.steps ? [...c.prepared.steps] : undefined })}>Undo my edit</button>}
              {!dirty && <button type="button" className="btn btn--quiet btn--sm" onClick={() => setEditing(false)}>Done editing</button>}
            </div>
          )}
          <p className="kc-sub" data-testid="card-from">From {c.sources.join(", ")}.{c.wording === "model" ? " Reworded by a model from safe numbers." : ""}{c.edited ? " Edited by you." : ""}</p>
          {parts.length > 0 && (
            <Details summary={`How this was chosen${typeof c.ranking?.score === "number" ? `: score ${c.ranking.score.toFixed(2)}` : ""}${c.ranking?.rank ? `, rank ${c.ranking.rank}` : ""}`} wide>
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Part</th><th className="num">Weight</th><th className="num">Added to the score</th></tr></thead>
                <tbody>{parts.map((p) => <tr key={p.key}><td>{p.label}</td><td className="num">{p.weight > 0 ? "+" : "−"}{Math.abs(p.weight).toFixed(2)}</td><td className="num">{p.contribution >= 0 ? "+" : "−"}{Math.abs(p.contribution).toFixed(3)}</td></tr>)}</tbody>
              </table></div>
              <p className="kc-sub">Code adds these up. A card shows only if its score clears {c.ranking?.min_score ?? "the minimum"}, and no model decides.</p>
            </Details>
          )}
        </div>
      )}
    </article>
  );
}
