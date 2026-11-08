import type { AnalyticMeta } from "../../types";

/** The small tag at the foot of the printed brief: "live" for measured data, else the engine's own word for the firm (or just "firm"). Generated data carries no origin tag (D57). */
export function FirmBadge({ meta, label }: { meta?: (AnalyticMeta & { badge?: string }) | null; label?: string }) {
  const origin = meta?.origin ?? "mixed";
  const text = label ?? meta?.badge ?? (origin === "real" ? "live" : "firm");
  return <span className="pill pill--origin" data-origin={origin}>{text}</span>;
}

/** "22 people", "1 approval": the unit agrees with the number. */
export function nWord(n: number, unit: string): string {
  const one: Record<string, string> = { people: "person", approvals: "approval", occurrences: "occurrence", pointers: "pointer", runs: "run", users: "user" };
  return `${n.toLocaleString("en-GB")} ${n === 1 ? one[unit] ?? unit.replace(/s$/, "") : unit}`;
}
