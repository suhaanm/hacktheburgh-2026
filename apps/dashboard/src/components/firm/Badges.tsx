import type { AnalyticMeta } from "../../types";

/** Said once, at the top of every Firm view, in the synthetic badge area: the firm is generated and so are the names. */
export const SYNTHETIC_NOTE = "Names are made up. This firm is synthetic.";

/** "synthetic firm" on every card of the Firm screen: the whole firm is generated, never measured from real people. */
export function FirmBadge({ meta, label }: { meta?: (AnalyticMeta & { badge?: string }) | null; label?: string }) {
  const origin = meta?.origin ?? "synthetic";
  const text = label ?? meta?.badge ?? (origin === "real" ? "live" : "synthetic firm");
  return <span className="pill pill--origin" data-origin={origin}>{text}</span>;
}

/** "22 people", "1 approval": the unit agrees with the number. */
export function nWord(n: number, unit: string): string {
  const one: Record<string, string> = { people: "person", approvals: "approval", occurrences: "occurrence", pointers: "pointer", runs: "run", users: "user" };
  return `${n.toLocaleString("en-GB")} ${n === 1 ? one[unit] ?? unit.replace(/s$/, "") : unit}`;
}
