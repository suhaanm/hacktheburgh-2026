import type { HTMLAttributes, ReactNode, Ref } from "react";
import { Hint } from "./Hint";

/** The cog families a repeated action can belong to. One shape each, never colour. */
export type HitGlyph = "open" | "read" | "enter" | "copy" | "check" | "run" | "search";

const GLYPH_PATH: Record<HitGlyph, string> = {
  open: "M8 4H4v12h12v-4 M11 4h5v5 M16 4l-7 7",
  read: "M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5z M10 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4",
  enter: "M3 5h14v10H3z M7 8v4",
  copy: "M7 7h9v9H7z M4 13V4h9",
  check: "M4 10l4 4 8-8",
  run: "M6 4l10 6-10 6z",
  search: "M9 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12z M14 14l4 4",
};

export function HitGlyphIcon({ glyph }: { glyph: HitGlyph }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true"><path d={GLYPH_PATH[glyph]} /></svg>
  );
}

export interface HitListRowProps extends Omit<HTMLAttributes<HTMLLIElement>, "children"> {
  glyph: HitGlyph | ReactNode;
  /** Plain words; put the key part in <b>, e.g. Enter the <b>household</b> into three calculators. */
  label: ReactNode;
  /** An optional second line, only for "includes X" or "stops before: submit". */
  sub?: ReactNode;
  /** "12 times" (the brackets are added). */
  count?: ReactNode;
  /** The figure at the right edge, with its unit: "14 min". */
  value: ReactNode;
  /** One or two sentences behind a Hint beside the figure, e.g. "9 to 19 min a week, 95% interval". Leave empty on the admin view, which prints it. */
  valueHint?: ReactNode;
  /** A status chip (a .pill with a shape glyph), only when something is already happening. */
  chip?: ReactNode;
  /** Quiet actions. They show on hover or focus-within and always on touch. */
  actions?: ReactNode;
  open?: boolean;
  liRef?: Ref<HTMLLIElement>;
}

const KNOWN: HitGlyph[] = ["open", "read", "enter", "copy", "check", "run", "search"];

/** One row of the Repeats list. Presentational: roving tabindex, Enter and Escape belong to the list that renders it. Wrap rows in <ul className="hitlist">. */
export function HitListRow({ glyph, label, sub, count, value, valueHint, chip, actions, open, liRef, className, ...rest }: HitListRowProps) {
  const g = typeof glyph === "string" && (KNOWN as string[]).includes(glyph) ? <HitGlyphIcon glyph={glyph as HitGlyph} /> : glyph;
  return (
    <li ref={liRef} className={className ? `hitrow ${className}` : "hitrow"} data-open={open || undefined} {...rest}>
      <span className="hitrow__glyph">{g}</span>
      <span className="hitrow__main">
        <span className="hitrow__line">
          <span className="hitrow__label">{label}</span>
          {chip}
        </span>
        {sub && <span className="hitrow__sub">{sub}</span>}
      </span>
      <span className="hitrow__count">{count != null && <>({count})</>}</span>
      <span className="hitrow__value">
        {value}
        {valueHint && <Hint label="About this figure">{valueHint}</Hint>}
      </span>
      <span className="hitrow__actions">{actions}</span>
    </li>
  );
}
