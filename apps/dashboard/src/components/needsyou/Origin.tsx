// The one origin badge a Track C screen shows (docs/KNACK_UX.md section 5: one badge per screen, sentence case; the sentence behind it is in a Hint,
// the badge itself is the printed fact, and an engine error is printed as a line because an error is never only in a Hint).
import { EXAMPLE_LINE, type Fallback } from "../../lib/fallback";
import type { AnalyticMeta } from "../../types";
import { Hint } from "../Hint";

export interface Source { meta?: AnalyticMeta | null; why?: Fallback | null }
export interface OriginInfo { text: string; data: "example" | "synthetic" | "mixed"; why: Fallback | null }

/** Example data when any source fell back to the built-in sample; the data's own origin when it is not real; nothing when everything is real. */
export function originOf(sources: Source[]): OriginInfo | null {
  const why = sources.find((s) => s.why)?.why ?? null;
  if (why) return { text: "Example data", data: "example", why };
  const meta = sources.map((s) => s.meta).find((m) => m && m.origin !== "real");
  if (!meta) return null;
  if (meta.origin === "mixed") return { text: "Some example data", data: "mixed", why: null };
  return { text: "Example data", data: "synthetic", why: null };
}

export function OriginBadge({ sources }: { sources: Source[] }) {
  const o = originOf(sources);
  if (!o) return null;
  return (
    <span className="kc-badges">
      <span className="pill pill--origin" data-origin={o.data}>{o.text}</span>
      {o.why && <Hint label="Why this is example data">{EXAMPLE_LINE[o.why.kind]}</Hint>}
    </span>
  );
}

/** An engine error is printed, not tucked away: the screen shows example data and says the engine could not answer. */
export function OriginError({ sources }: { sources: Source[] }) {
  const why = sources.find((s) => s.why?.kind === "error")?.why;
  if (!why) return null;
  return <p className="note note--warn" role="status">{EXAMPLE_LINE.error} Nothing was changed.</p>;
}
