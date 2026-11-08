import { TREND_GLYPH } from "./model";
import type { Trend } from "./wire";

/**
 * One stacked bar: how many people are in each trend class. Colour is never the only carrier: each class has its own fill pattern, its glyph and its
 * word with the count beside it, so the bar reads the same in greyscale and for colour-blind readers. A class with nobody in it is left out of the bar.
 */
export function MixBar({ title, parts, total }: { title: string; parts: { id: Trend; label: string; count: number }[]; total: number }) {
  const shown = parts.filter((p) => p.count > 0);
  const text = `${title}. ${parts.map((p) => `${p.label}: ${p.count}`).join(". ")}. Of ${total}.`;
  return (
    <figure className="mix">
      <div className="mix__bar" role="img" aria-label={text}>
        {shown.map((p) => <span key={p.id} className="mix__seg" data-trend={p.id} style={{ flexGrow: p.count }} />)}
      </div>
      <ul className="mix__legend">
        {parts.map((p) => (
          <li key={p.id} className="mix__item" data-trend={p.id} data-zero={p.count === 0 ? "true" : undefined}>
            <span className="mix__sw" data-trend={p.id} aria-hidden="true" />
            <span className="firm-trend__glyph" aria-hidden="true">{TREND_GLYPH[p.id]}</span>
            <span>{p.label}</span>
            <b className="tabular">{p.count.toLocaleString("en-GB")}</b>
          </li>
        ))}
      </ul>
    </figure>
  );
}
