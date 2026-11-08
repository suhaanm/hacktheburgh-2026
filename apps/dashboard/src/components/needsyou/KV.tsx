import type { ReactNode } from "react";

/**
 * Label and value, one pair to a line: how an expanded block lists facts so they can be scanned. A value is a short phrase, never a sentence that restates
 * the title; a pair with no value is left out, so a missing field leaves no hole and no "undefined".
 */
export function KV({ rows, label }: { rows: [string, ReactNode | null | undefined | false][]; label?: string }) {
  const shown = rows.filter(([, v]) => v !== null && v !== undefined && v !== false && v !== "");
  if (shown.length === 0) return null;
  return (
    <dl className="kc-kv" aria-label={label}>
      {shown.map(([k, v]) => (<div key={k} className="kc-kv__pair"><dt>{k}</dt><dd>{v}</dd></div>))}
    </dl>
  );
}
