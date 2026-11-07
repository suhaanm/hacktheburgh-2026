// The small inline icons Track C's rows use (16 px grid, 1.5 px stroke, currentColor, no dependency): the docs/KNACK_UX.md icon rules.
// A glyph beside a row says its kind; it never sits inside a primary button and it is never the only carrier of meaning (the title says it too).
export type GlyphName = "alert" | "decision" | "routine" | "paused" | "chevron" | "check";

const PATH: Record<GlyphName, string> = {
  alert: "M8 2.5 14 13H2L8 2.5ZM8 6.5v3M8 11.2v.1",
  decision: "M8 2.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM8 6.6a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8Z",
  routine: "M3 6h9l-2.5-2.5M13 10H4l2.5 2.5",
  paused: "M5.5 3.5v9M10.5 3.5v9",
  chevron: "M6 3.5 10.5 8 6 12.5",
  check: "M3.5 8.5 6.5 11.5 12.5 4.5",
};

export function Glyph({ name, className = "kc-glyph" }: { name: GlyphName; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d={PATH[name]} />
    </svg>
  );
}
