// The one card a graph shows a name in. It appears beside a node on hover, on keyboard focus, and on a click, where it stays until Escape or another
// click (lib/graph.ts tipFor). It uses the design system's card for a note, the same as the Hint: panel surface, hairline, small radius, one soft shadow.
// It is never the only copy of the name: the node carries it in its aria-label, so the card is hidden from screen readers to avoid a double reading.
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { tipPlace } from "../../lib/graph";

export interface TipProps {
  /** where the node is, in the stage's own pixels */
  anchor: { x: number; y: number; r: number };
  stage: { w: number; h: number };
  /** the chip at the card's start */
  chip: ReactNode;
  /** the name, in full: long names wrap to three lines, then end in an ellipsis */
  name: string;
  /** one short line under it: the kind, and a state in words when there is one */
  meta?: string;
  pinned?: boolean;
  id?: string;
}

export function GraphTip({ anchor, stage, chip, name, meta, pinned = false, id }: TipProps) {
  const el = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  // Measure the card before paint, then place it from its real box.
  useLayoutEffect(() => {
    if (el.current) setSize({ w: el.current.offsetWidth, h: el.current.offsetHeight });
  }, [name, meta, stage.w, stage.h]);
  const at = size ? tipPlace(anchor, size, stage) : null;
  return (
    <div ref={el} id={id} className="gtip" data-pinned={pinned || undefined} data-side={at?.side} aria-hidden="true"
      style={{ left: at ? at.x : 0, top: at ? at.y : 0, visibility: at ? "visible" : "hidden" }}>
      {chip}
      <span className="gtip__text">
        <span className="gtip__name">{name}</span>
        {meta && <span className="gtip__meta">{meta}</span>}
      </span>
    </div>
  );
}
