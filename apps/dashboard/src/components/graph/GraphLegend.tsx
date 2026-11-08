// The key to a graph: pictures only, behind a small "What are these?" disclosure. Each picture is a button; its name and one short line open in the same
// card the canvas uses, on hover, on focus and on a tap, and close on Escape or a tap elsewhere. Every entry also carries its words in an aria-label.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NODE_BLURB, NODE_KINDS, NODE_NAME } from "../../lib/nodeIcons";
import { Details } from "../ui";
import { KindChip } from "./Glyph";
import "../../styles/graph.css";

export interface LegendEntry {
  id: string;
  name: string;
  note: string;
  /** the picture: a kind chip or a small drawing of an encoding */
  graphic: ReactNode;
  /** entries of one group sit together; a hairline falls between groups */
  group: "kind" | "mark";
}

const sw = { width: 30, height: 20, viewBox: "0 0 30 20", "aria-hidden": true as const, focusable: false as const };

/** The marks of the work graph, drawn the way the canvas draws them: size, fade with a dashed ring for lapsed, a hairline link, a dashed envelope. */
const MARKS: LegendEntry[] = [
  { id: "size", name: "Size", note: "Minutes a week for routines, memory and automations; mastery for skills.", group: "mark",
    graphic: <svg {...sw}><circle cx="8" cy="10" r="4" className="gk-fill" /><circle cx="21" cy="10" r="7" className="gk-fill" /></svg> },
  { id: "fade", name: "Faded", note: "Weaker, and fading with disuse. A dashed ring means it has lapsed.", group: "mark",
    graphic: <svg {...sw}><circle cx="8" cy="10" r="5.5" className="gk-fill" /><circle cx="22" cy="10" r="5.5" className="gk-fill" opacity="0.3" /><circle cx="22" cy="10" r="7" className="gk-dash" /></svg> },
  { id: "link", name: "Linked", note: "Often seen together.", group: "mark",
    graphic: <svg {...sw}><circle cx="5" cy="10" r="3" className="gk-fill" /><circle cx="25" cy="10" r="3" className="gk-fill" /><path d="M8 10h14" className="gk-hair" /></svg> },
  { id: "combined", name: "Combined", note: "Routines that always run together.", group: "mark",
    graphic: <svg {...sw}><rect x="1.5" y="3.5" width="27" height="13" rx="6.5" className="gk-env" /><circle cx="9" cy="10" r="3.2" className="gk-fill" /><circle cx="21" cy="10" r="3.2" className="gk-fill" /></svg> },
];

/** The work graph's key: the four kinds with their icons, then the four marks. */
export const WORK_LEGEND: LegendEntry[] = [
  ...NODE_KINDS.map((k): LegendEntry => ({ id: k, name: NODE_NAME[k], note: NODE_BLURB[k], group: "kind", graphic: <KindChip kind={k} size={24} /> })),
  ...MARKS,
];

export function GraphLegend({ entries, summary = "What are these?", label = "How to read the graph" }: { entries: LegendEntry[]; summary?: string; label?: string }) {
  const [pinned, setPinned] = useState<string | null>(null);
  const root = useRef<HTMLUListElement>(null);
  // A tap elsewhere closes a pinned card (a touch screen has no hover and may give a button no focus).
  useEffect(() => {
    if (!pinned) return;
    const down = (e: Event) => { if (!root.current?.contains(e.target as Node)) setPinned(null); };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [pinned]);
  return (
    <Details summary={summary}>
      <ul ref={root} className="gkey" aria-label={label} onKeyDown={(e) => { if (e.key === "Escape" && pinned) { setPinned(null); e.stopPropagation(); } }}>
        {entries.map((e, i) => (
          <li key={e.id} className="gkey__li" data-first-of-group={i === 0 || entries[i - 1].group !== e.group ? "true" : undefined}>
            <button type="button" className="gkey__item" aria-label={`${e.name}: ${e.note}`} aria-expanded={pinned === e.id} data-open={pinned === e.id || undefined}
              onClick={() => setPinned((p) => (p === e.id ? null : e.id))}>
              {e.graphic}
            </button>
            <span className="gkey__card" role="note" aria-hidden="true">
              <b>{e.name}</b>
              <span>{e.note}</span>
            </span>
          </li>
        ))}
      </ul>
    </Details>
  );
}
