import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

/**
 * A hairline list with one tab stop for the rows themselves: the arrow keys, Home and End move focus between rows, and Space or Enter on a row opens its
 * evidence. Keys on a button inside a row belong to that button. NO key ever approves, rejects or chooses anything: the only thing a row's key does is
 * open or close a panel, and a decision is always a click on its own button.
 */
export function RowList({ label, rows }: { label: string; rows: { key: string; node: ReactNode }[] }) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLLIElement | null)[]>([]);
  const focusRow = (i: number) => { setActive(i); refs.current[i]?.focus(); };
  const onKey = (e: KeyboardEvent<HTMLLIElement>, i: number) => {
    if (e.target !== e.currentTarget) return;
    const n = rows.length;
    const next = e.key === "ArrowDown" ? Math.min(n - 1, i + 1) : e.key === "ArrowUp" ? Math.max(0, i - 1) : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : null;
    if (next !== null) { e.preventDefault(); focusRow(next); return; }
    if (e.key === " " || e.key === "Spacebar" || e.key === "Enter") {
      const t = e.currentTarget.querySelector<HTMLButtonElement>("[data-toggle]");
      if (t) { e.preventDefault(); t.click(); }
    }
  };
  return (
    <ul className="kc-list" aria-label={label}>
      {rows.map((r, i) => (
        <li key={r.key} ref={(el) => { refs.current[i] = el; }} tabIndex={i === Math.min(active, rows.length - 1) ? 0 : -1}
          onFocus={(e) => { if (e.target === e.currentTarget) setActive(i); }} onKeyDown={(e) => onKey(e, i)}>
          {r.node}
        </li>
      ))}
    </ul>
  );
}
