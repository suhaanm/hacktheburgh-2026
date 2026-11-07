// The one origin badge a Track C screen shows (docs/KNACK_UX.md section 5: one badge per screen, sentence case; the sentence behind it is in a Hint,
// the badge itself is the printed fact, and an engine error is printed as a line because an error is never only in a Hint).
import type { Fallback } from "../../lib/fallback";
import type { AnalyticMeta } from "../../types";
import { SourceNote } from "../common";

export interface Source { meta?: AnalyticMeta | null; why?: Fallback | null }
export interface OriginInfo { text: string; data: "example" | "synthetic" | "mixed"; why: Fallback | null }

/**
 * What the one badge says. Two different facts, kept apart:
 *   - a source that FELL BACK to the built-in sample (the engine did not answer, or the layer is off) is "Example data";
 *   - a source the engine DID answer, whose own meta says the numbers are synthetic (a sandbox firm), is "Synthetic firm".
 * Every source one way is the plain word; a mix is "Some example data" or "Some synthetic data". Real data from a live engine carries no badge.
 * A source with no meta of its own (the memory file) says nothing either way.
 */
export function originOf(sources: Source[]): OriginInfo | null {
  const fell = sources.filter((s) => s.why);
  const why = fell[0]?.why ?? null;
  if (fell.length > 0) return fell.length === sources.length ? { text: "Example data", data: "example", why } : { text: "Some example data", data: "mixed", why };
  const metas = sources.map((s) => s.meta).filter((m): m is AnalyticMeta => !!m);
  const off = metas.filter((m) => m.origin !== "real");
  if (off.length === 0) return null;
  return off.length === metas.length ? { text: "Synthetic firm", data: "synthetic", why: null } : { text: "Some synthetic data", data: "mixed", why: null };
}

export function OriginBadge({ sources }: { sources: Source[] }) {
  const o = originOf(sources);
  if (!o) return null;
  return <span className="kc-badges"><span className="pill pill--origin" data-origin={o.data}>{o.text}</span></span>;
}

/**
 * Why a screen shows example data: the shared one plain line, and under it the engine's own sentence (the flag that switches the layer on, or the
 * error) in a closed "Details". The instruction is one tap away and printed once opened; it is never only in a Hint (D45). An engine error keeps the
 * warning look so it is read. Nothing when the data is the engine's own.
 */
export function OriginDetails({ sources }: { sources: Source[] }) {
  const why = sources.find((s) => s.why)?.why;
  return why ? <SourceNote why={why} /> : null;
}

