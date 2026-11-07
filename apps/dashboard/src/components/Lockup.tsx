// The Knack mark: a solid disc (the worker) with a ring offset behind it (the understudy, shadowing).
// Geometry is packages/design/brand/knack-glyph.svg cropped to its own box (viewBox 28 30 78 72). In the UI the disc is --fg and the ring is
// --accent, both at full strength; the `mono` tone is the single-colour variant for surfaces that cannot carry two colours.
// Rules: docs/knack-ux/knack-brand-sheet.svg. The disc is as tall as the capital K, the gap is about one disc radius, clear space is one K.
// Never recolour the ring for status, never add a gradient or glow, never set the word in capitals, never put the mark in a tile.
import type { CSSProperties } from "react";

/** Sizes where the mark appears, in px of glyph width (brand sheet, section D). */
export const LOCKUP_SIZES = {
  /** Corner pill: glyph alone. */
  pill: 14,
  /** Favicon: the currentColor glyph. */
  favicon: 16,
  /** Sidebar top: glyph 20 px, word 17.5 px. */
  sidebar: 20,
  /** Landing and large lockups. */
  large: 44,
  /** First run: glyph alone above the question. */
  firstRun: 56,
} as const;
export type LockupSize = keyof typeof LOCKUP_SIZES;

/** Minimums from the brand sheet: glyph 12 px, lockup word 14 px. */
export const GLYPH_MIN = 12;
export const WORD_MIN = 14;

/** The word is 0.875 of the glyph width (17.5 px against 20 px). */
const WORD_RATIO = 17.5 / 20;
/** Glyph height over width: the cropped box is 78 by 72. */
const HEIGHT_RATIO = 72 / 78;

/** Word size in px for a glyph of this width, never below the minimum. */
export function wordSize(glyph: number): number {
  return Math.max(WORD_MIN, Math.round(glyph * WORD_RATIO * 10) / 10);
}

function px(size: number | LockupSize): number {
  const v = typeof size === "number" ? size : LOCKUP_SIZES[size];
  return Math.max(GLYPH_MIN, v);
}

/** Glyph only. Decorative when `label` is omitted (the word or a nearby label names it), else an image with that name. */
export function Glyph({ size = "sidebar", tone = "ui", label, className }: {
  size?: number | LockupSize;
  /** `ui`: disc --fg, ring --accent. `mono`: currentColor, ring at 62% (menu bar, favicon, print). */
  tone?: "ui" | "mono";
  label?: string;
  className?: string;
}) {
  const w = px(size);
  const h = Math.round(w * HEIGHT_RATIO * 10) / 10;
  const a11y = label ? { role: "img" as const, "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg className={`glyph glyph--${tone}${className ? ` ${className}` : ""}`} width={w} height={h} viewBox="28 30 78 72" focusable="false" {...a11y}>
      <circle className="glyph__ring" cx="76" cy="72" r="22" fill="none" strokeWidth="7" />
      <circle className="glyph__disc" cx="54" cy="56" r="22" />
    </svg>
  );
}

/** Glyph plus the word Knack. `href` makes it a link (the sidebar top); `wordless` draws the glyph alone, named for assistive tech. */
export function Lockup({ size = "sidebar", tone = "ui", href, wordless = false, label = "Knack", className }: {
  size?: number | LockupSize;
  tone?: "ui" | "mono";
  href?: string;
  wordless?: boolean;
  /** Accessible name of the whole lockup (a link names its destination, for example "Knack home"). */
  label?: string;
  className?: string;
}) {
  const w = px(size);
  const style = { "--lockup-glyph": `${w}px`, "--lockup-word": `${wordSize(w)}px` } as CSSProperties;
  const cls = `lockup${wordless ? " lockup--glyph" : ""}${className ? ` ${className}` : ""}`;
  const inner = wordless
    ? <Glyph size={w} tone={tone} />
    : <><Glyph size={w} tone={tone} /><span className="lockup__word">Knack</span></>;
  if (href) return <a className={cls} style={style} href={href} aria-label={label}>{inner}</a>;
  return <span className={cls} style={style} role={wordless ? "img" : undefined} aria-label={wordless ? label : undefined}>{inner}</span>;
}
