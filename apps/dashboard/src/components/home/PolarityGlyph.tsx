/** The three shapes the design system draws for a pointer: an arrow for "going well", a triangle for "worth a look", a ring for a trade-off or a note. */
export type Look = "positive" | "negative" | "neutral";
const PATH: Record<Look, string> = {
  positive: "M4 16l5-5 4 4 7-8M15 7h5v5",
  negative: "M12 4l9 16H3z M12 10v4 M12 17v.01",
  neutral: "M8.5 12a3.5 3.5 0 1 0 7 0 3.5 3.5 0 0 0-7 0",
};
export const lookOfPolarity = (p: string): Look => (p === "positive" ? "positive" : p === "attention" ? "negative" : "neutral");
export function PolarityGlyph({ look }: { look: Look }) {
  return (
    <span className="insight__glyph" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d={PATH[look]} /></svg>
    </span>
  );
}
