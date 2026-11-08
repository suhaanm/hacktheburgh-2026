// The one origin badge a Track C screen shows (docs/KNACK_UX.md section 5: one badge per screen, sentence case; the sentence behind it is in a Hint,
// the badge itself is the printed fact, and an engine error is printed as a line because an error is never only in a Hint).
import type { Fallback, FallbackKind } from "../../lib/fallback";
import type { AnalyticMeta } from "../../types";
import { Hint } from "../Hint";

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

/** One short sentence for why a screen shows example data. The engine's own sentence (the flag that switches the layer on, or the error) is in the Hint beside it. */
export const SHORT_WHY: Record<FallbackKind, string> = {
  offline: "The engine is not answering.",
  extension_off: "This feature is off in the engine.",
  missing: "The engine does not have this yet.",
  error: "The engine could not answer.",
};

/** One kind of reason: the short sentence, and in a Hint the engine's own words (all the different ones of that kind). An error keeps the warning look so it is read. */
function Why({ ws }: { ws: Fallback[] }) {
  const kind = ws[0].kind;
  return (
    <p className={`kc-origin${kind === "error" ? " note note--warn" : " note"}`} data-kind={kind} role={kind === "error" ? "status" : undefined}>
      {SHORT_WHY[kind]}
      <Hint label="Why this is example data">{ws.map((w, i) => <span key={w.message} data-testid="source-detail">{i > 0 ? " " : ""}{w.message}</span>)}</Hint>
    </p>
  );
}

/**
 * Why a screen shows example data: one short sentence per kind of reason, and the engine's own sentence in the Hint beside it (it holds the flag that
 * switches a layer on). Nothing when the data is the engine's own.
 */
export function OriginDetails({ sources }: { sources: Source[] }) {
  const byKind = new Map<string, Fallback[]>();
  for (const w of distinctWhys(sources)) byKind.set(w.kind, [...(byKind.get(w.kind) ?? []), w]);
  return <>{[...byKind.values()].map((ws) => <Why key={ws[0].kind} ws={ws} />)}</>;
}

/** Each different reason once (at most three), in the order the sources are given: two sources that fell back for the same reason say it once. */
export function distinctWhys(sources: Source[]): Fallback[] {
  const seen = new Set<string>();
  const out: Fallback[] = [];
  for (const s of sources) if (s.why && !seen.has(s.why.message)) { seen.add(s.why.message); out.push(s.why); }
  return out.slice(0, 3);
}

/** One section's own reason, printed inside that section: a screen made of several sources must not blame them all on the first one that failed. */
export function SectionSource({ why }: { why: Fallback | null | undefined }) {
  return why ? <div className="yd-body" style={{ paddingBottom: 0 }}><Why ws={[why]} /></div> : null;
}
