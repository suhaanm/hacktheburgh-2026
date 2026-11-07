import { Range } from "../common";
import { Hint } from "../Hint";
import { pctBracket, type ComponentCard } from "./model";

/** The three things that matter, in plain words. Each has its value, its interval and the fact behind it; none stands alone. */
export function Cards({ cards, levelPct }: { cards: ComponentCard[]; levelPct: number }) {
  return (
    <div className="gr-comps">
      {cards.map((c) => (
        <section key={c.id} className="gr-comp" aria-labelledby={`gc-${c.id}`}>
          <h3 id={`gc-${c.id}`} className="gr-comp__title">{c.title}<Hint label={`What ${c.title.toLowerCase()} measures`}>{c.measure}</Hint></h3>
          <p className={`gr-comp__figure num${c.value == null ? " gr-comp__figure--none" : ""}`}>
            {c.display}
            {c.ci && c.value != null && <Hint label={`Interval for ${c.title.toLowerCase()}`}>{levelPct}% interval {pctBracket(c.ci)}. The bar runs {Math.round(c.scale[0] * 100)}% to {Math.round(c.scale[1] * 100)}%.</Hint>}
          </p>
          {c.ci && c.value != null ? <Range lo={c.ci[0]} hi={c.ci[1]} pt={c.value} min={c.scale[0]} max={c.scale[1]} /> : null}
          {c.sentence && <p className="gr-comp__fact">{c.sentence}</p>}
          {c.pending && <p className="gr-comp__pending">{c.pending}</p>}
        </section>
      ))}
    </div>
  );
}
