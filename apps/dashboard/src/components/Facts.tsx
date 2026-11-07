const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Humanise a key like `assisted_speed` or `mean_s`. */
export const nice = (k: string) => k.replace(/_/g, " ").replace(/\bs\b/, "(s)");

/** Show what the engine reports for a part of the study whose inner shape is not fixed: numbers and short text, one level deep. */
export function Facts({ title, v }: { title: string; v: unknown }) {
  if (v == null) return null;
  const rows: [string, string][] = [];
  const fmt = (x: unknown): string | null => (isNum(x) ? String(Math.round(x * 1000) / 1000) : typeof x === "string" && x.length < 90 ? x : Array.isArray(x) && x.every(isNum) ? `[${x.map((n) => Math.round((n as number) * 1000) / 1000).join(", ")}]` : null);
  if (typeof v === "object" && !Array.isArray(v)) {
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      const f = fmt(x);
      if (f != null) rows.push([nice(k), f]);
      else if (x && typeof x === "object" && !Array.isArray(x)) for (const [k2, y] of Object.entries(x as Record<string, unknown>)) { const g = fmt(y); if (g != null) rows.push([`${nice(k)}, ${nice(k2)}`, g]); }
    }
  } else { const f = fmt(v); if (f != null) rows.push([title, f]); }
  if (!rows.length) return null;
  return (
    <div className="stack" style={{ gap: "var(--space-1)" }}>
      <span className="t-label">{title}</span>
      <ul className="plain-list">{rows.map(([k, x]) => <li key={k} className="ev-note">{k}: <b className="tabular">{x}</b></li>)}</ul>
    </div>
  );
}

