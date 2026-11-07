// The one origin badge a Track C screen shows (docs/KNACK_UX.md section 5: one badge per screen, sentence case; the sentence behind it is in a Hint,
// the badge itself is the printed fact, and an engine error is printed as a line because an error is never only in a Hint).
import type { Fallback } from "../../lib/fallback";
import type { AnalyticMeta } from "../../types";
import { SourceNote } from "../common";

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

