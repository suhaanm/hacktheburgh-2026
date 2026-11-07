import { useState } from "react";
import type { WirePointer, WireWhy } from "../firm/wire";
import { Details } from "../ui";
import { loadWhy, sendFeedback, type FeedbackEvent } from "../../screens/Home/data";
import type { Loaded } from "../../api";
import { PolarityGlyph, lookOfPolarity } from "./PolarityGlyph";
import { APP_NAME } from "../../brand";

/** The link a pointer's one action opens. */
export const pointerHref = (a: NonNullable<WirePointer["action"]>): string => `#/${a.to}${a.query ? `?${a.query}` : ""}`;

export const lookOf = lookOfPolarity;
const LABEL: Record<WirePointer["polarity"], string> = { positive: "Going well", attention: "Worth a look", tradeoff: "Trade-off", note: "Note" };

/** The reason behind one pointer, read when the worker opens it, with the three ways to tell Understudy how it landed. Every one only makes things quieter. */
function Why({ p, person, onGone }: { p: WirePointer; person: string | null; onGone: (id: string) => void }) {
  const [state, setState] = useState<{ status: "idle" | "loading" | "ready" | "error"; why: Loaded<WireWhy> | null }>({ status: "idle", why: null });
  const [said, setSaid] = useState<string | null>(null);
  const open = (o: boolean) => {
    if (!o || state.status !== "idle") return;
    setState({ status: "loading", why: null });
    loadWhy(p, person).then((why) => setState({ status: "ready", why }), () => setState({ status: "error", why: null }));
  };
  const tell = async (event: FeedbackEvent | "hide_kind", words: string) => {
    try {
      await sendFeedback(p.id, event as FeedbackEvent, person);
      setSaid(words);
      if (event === "not_useful" || event === "hide_kind") window.setTimeout(() => onGone(p.id), 900);
    } catch {
      setSaid("That did not save. Nothing changed.");
    }
  };
  const why = state.why?.data;
  return (
    <Details summary="Why am I seeing this?" onToggle={open} wide>
      {state.status === "loading" && <p>Reading the reason.</p>}
      {state.status === "error" && <p>The reason could not be loaded. The pointer itself is unchanged.</p>}
      {why && (
        <div className="home__why">
          {why.reason_text && <p>{why.reason_text}</p>}
          {why.because.length > 0 && <ul>{why.because.map((b) => <li key={b}>{b}</li>)}</ul>}
          {why.sources.length > 0 && <p className="home__source">Source: {why.sources.map((s) => s.label).join(", ")}</p>}
          {why.limits.length > 0 && <ul className="home__limits">{why.limits.map((l) => <li key={l}>{l}</li>)}</ul>}
          <div className="home__tell" role="group" aria-label={`Tell ${APP_NAME} how this landed`}>
            {said ? <p role="status" className="home__said">{said}</p> : (
              <>
                <button type="button" className="btn btn--quiet btn--sm" onClick={() => tell("useful", "Noted. This kind of pointer stays.")}>Useful</button>
                <button type="button" className="btn btn--quiet btn--sm" onClick={() => tell("not_useful", "Noted. You will see this less.")}>Not useful</button>
                <button type="button" className="btn btn--quiet btn--sm" onClick={() => tell("hide_kind", "Noted. This kind of pointer is hidden.")}>Hide this kind</button>
              </>
            )}
          </div>
        </div>
      )}
    </Details>
  );
}

/** One pointer: how it looks (word and shape, never colour alone), one sentence, at most one action, and the reason behind it one click away. */
export function PointerCard({ p, person, onGone }: { p: WirePointer; person: string | null; onGone: (id: string) => void }) {
  const look = lookOf(p.polarity);
  const label = p.polarity_label ?? LABEL[p.polarity];
  return (
    <article className="insight home__card" data-polarity={look} aria-label={p.a11y_label ?? `${label}: ${p.headline}`}>
      <PolarityGlyph look={look} />
      <div className="insight__head">
        <span className="insight__label">{label}{p.badge ? <> <span aria-hidden="true">·</span> {p.badge}</> : null}</span>
        <h3 className="insight__title">{p.headline}</h3>
      </div>
      {p.detail && <p className="insight__text">{p.detail}</p>}
      {p.action && <div className="insight__action"><a className="btn btn--secondary btn--sm" href={pointerHref(p.action)}>{p.action.label}</a></div>}
      {p.details_available && <div className="home__card-why"><Why p={p} person={person} onGone={onGone} /></div>}
    </article>
  );
}
