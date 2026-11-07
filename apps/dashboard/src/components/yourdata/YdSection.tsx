import type { ReactNode } from "react";
import { Glyph } from "../needsyou/Glyph";

/**
 * One section of Your data: a title and, while it is closed, a few words about it (never a sentence). The whole line opens it; the control has no words
 * of its own (its name is the section's), so the line reads as one row. Sections open in place and stay where they are.
 */
export function YdSection({ id, title, fact, open, onToggle, children }: { id: string; title: string; fact: string; open: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <section className="yd-section" id={`yd-${id}`} data-open={open}>
      <h2 className="yd-section__h">
        <span className="yd-section__line">
          <span className="yd-section__title">{title}</span>
          {!open && fact && <span className="yd-section__fact">{fact}</span>}
          <Glyph name="chevron" className="kc-glyph yd-section__chev" />
          <button type="button" className="yd-section__open" aria-expanded={open} aria-controls={`yd-${id}-body`} aria-label={`${title}: ${open ? "close" : "open"}`} onClick={onToggle} />
        </span>
      </h2>
      {open && <div id={`yd-${id}-body`}>{children}</div>}
    </section>
  );
}
