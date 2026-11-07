import { useState } from "react";
import type { WirePointer, WireWhy } from "../firm/wire";
import { Details } from "../ui";
import { loadWhy, sendFeedback, type FeedbackEvent } from "../../screens/Home/data";
import type { Loaded } from "../../api";

/** The link a pointer's one action opens. */
export const pointerHref = (a: NonNullable<WirePointer["action"]>): string => `#/${a.to}${a.query ? `?${a.query}` : ""}`;

/**
 * "Why this?": the method (fixed rules, not a model), the reason behind one pointer read when it is opened, its sources, the limits, the example
 * sentence when an example week stands in, and the three ways to tell Knack how it landed. Every one of those only makes things quieter.
 */
export function WhyThis({ p, person, note, onGone }: { p: Pick<WirePointer, "id" | "headline">; person: string | null; note: string | null; onGone: (id: string) => void }) {
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
    <Details summary="Why this?" onToggle={open} wide>
      <div className="home__reason">
        <p>Chosen by fixed rules, not by a model.</p>
        {note && <p className="home__limits">{note}</p>}
        {state.status === "loading" && <p>Reading the reason.</p>}
        {state.status === "error" && <p>The reason could not be loaded. The pointer itself is unchanged.</p>}
        {why && (
          <>
            {why.reason_text && <p>{why.reason_text}</p>}
            {why.because.length > 0 && <ul>{why.because.map((b) => <li key={b}>{b}</li>)}</ul>}
            {why.sources.length > 0 && <p className="home__source">Source: {why.sources.map((s) => s.label).join(", ")}</p>}
            {why.limits.length > 0 && <ul className="home__limits">{why.limits.map((l) => <li key={l}>{l}</li>)}</ul>}
            <div className="home__tell" role="group" aria-label="Tell Knack how this landed">
              {said ? <p role="status" className="home__said">{said}</p> : (
                <>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => tell("useful", "Noted. This kind of pointer stays.")}>Useful</button>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => tell("not_useful", "Noted. You will see this less.")}>Not useful</button>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => tell("hide_kind", "Noted. This kind of pointer is hidden.")}>Hide this kind</button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </Details>
  );
}
