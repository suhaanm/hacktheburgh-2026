import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { HitListRow, type HitGlyph } from "../HitListRow";
import { fmtHours, fmtHoursRange, fmtMinutes, minutesExplained, moveIndex, peopleText, shownRows, splitKey, timesText } from "./model";
import type { Audience, FirmRow, HitRow } from "./types";
import "./repeats.css";

/**
 * The repeated-work hit list: one row per action, biggest first. Presentational, no routing and no fetching, so the Repeats page and the
 * Firm screen can both use it. The rows are the design system's `HitListRow`.
 *
 *   worker: rows are `HitRow`. Each row has a small glyph, the action in plain words with its key part in bold, a count in brackets, and
 *           the minutes it could save a week at the right edge (the interval is behind a Hint). "Automate" and "Not this one" show on
 *           hover or focus (always on a touch screen) and only when `renderPeek` / `onHide` are given.
 *   admin:  rows are `FirmRow` (an action in one role across the firm). People and hours a week replace the count and the minutes, the
 *           interval is printed, and there are no actions. People are counted here, never named.
 *
 * Keyboard: arrow keys, Home and End move between rows (one tab stop for the whole list); Enter on a row opens its Automate peek; Escape
 * closes it. At most `limit` rows (7) show until "Show all".
 */
export interface HitListProps {
  audience?: Audience;
  rows: HitRow[] | FirmRow[];
  /** Rows already automated, shown folded under the list (worker only). */
  automated?: HitRow[];
  /** The window the counts come from, for the words in the hint. */
  windowDays?: number;
  limit?: number;
  /** Opens inside the list, under the row, when Automate is pressed. Without it there is no Automate button. */
  renderPeek?: (row: HitRow, close: () => void) => ReactNode;
  onHide?: (row: HitRow) => void | Promise<void>;
  /** Accessible name of the list. */
  label?: string;
}

const CHIP_MODE: Record<string, string> = { proposed: "none", learning: "shadow", running: "approval", automated: "unattended" };
const CHIP_TEXT: Record<string, string> = { proposed: "proposed", learning: "learning", running: "running", automated: "automated" };

function Chip({ status }: { status: string }) {
  if (!CHIP_TEXT[status]) return null;
  return (
    <span className="pill pill--consent hl-chip" data-mode={CHIP_MODE[status]}>
      <span className="pill__glyph" aria-hidden="true" />
      {CHIP_TEXT[status]}
    </span>
  );
}

const glyphOf = (f: HitRow["family"]): HitGlyph => f;          // the family names are the design system's glyph names

function Label({ label, keyPart }: { label: string; keyPart: string | null }) {
  const [a, k, b] = splitKey(label, keyPart);
  return <>{a}{k && <b>{k}</b>}{b}</>;
}

export function HitList({ audience = "worker", rows, automated = [], windowDays = 7, limit = 7, renderPeek, onHide, label = "Repeated work" }: HitListProps) {
  const uid = useId();
  const admin = audience === "admin";
    const [showAll, setShowAll] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  const all = rows as (HitRow & FirmRow)[];
  const shown = shownRows(all, showAll, limit);
  useEffect(() => { if (active > shown.length - 1) setActive(Math.max(0, shown.length - 1)); }, [shown.length, active]);
  useEffect(() => { if (openId && !all.some((r) => r.id === openId)) setOpenId(null); }, [all, openId]);

  const focusRow = useCallback((i: number) => { setActive(i); refs.current[i]?.focus(); }, []);
  const close = useCallback((i?: number) => { setOpenId(null); if (i !== undefined) refs.current[i]?.focus(); }, []);

  const onKey = (e: KeyboardEvent<HTMLLIElement>, i: number, r: HitRow & FirmRow) => {
    if (e.key === "Escape" && openId === r.id) { e.preventDefault(); e.stopPropagation(); close(i); return; }
    if (e.target !== refs.current[i]) return;                     // keys pressed on a button or a link inside the row are theirs
    const next = moveIndex(i, e.key, shown.length);
    if (next !== null) { e.preventDefault(); focusRow(next); return; }
    if (e.key === "Enter" && !admin && renderPeek && r.actions?.can_automate) { e.preventDefault(); setOpenId(openId === r.id ? null : r.id); }
  };

  const items: ReactNode[] = [];
  shown.forEach((r, i) => {
    const open = openId === r.id;
    const peekId = `${uid}-p-${i}`;
    const tab = i === active ? 0 : -1;
    const canAutomate = !admin && !!renderPeek && !!r.actions?.can_automate;
    const sub = admin
      ? `${r.role.replace(/-/g, " ")}. ${fmtHoursRange(r.hours_per_week)} a week (95% interval), ${r.count.toLocaleString("en-GB")} times in ${windowDays} days.`
      : r.overlaps?.length
        ? r.overlaps.map((o) => (o.relation === "includes" ? `Includes the steps of “${o.label}”` : `Its steps are part of “${o.label}”`)).join(". ")
        : undefined;
    items.push(
      <HitListRow
        key={r.id}
        liRef={(el) => { refs.current[i] = el; }}
        tabIndex={tab}
        onFocus={(e) => { if (e.target === e.currentTarget) setActive(i); }}
        onKeyDown={(e) => onKey(e, i, r)}
        onClick={(e) => { if (!(e.target as HTMLElement).closest("button, a, .hint")) { setActive(i); setPicked((p) => (p === r.id ? null : r.id)); } }}
        picked={picked === r.id}
        hintTab={tab === 0 ? 0 : -1}
        glyph={glyphOf(r.family)}
        label={<Label label={r.label} keyPart={r.key} />}
        sub={sub}
        count={admin ? peopleText(r.people) : timesText(r.count)}
        chip={admin ? undefined : <Chip status={r.status} />}
        value={admin ? `${fmtHours(r.hours_per_week.point)} a week` : <>{fmtMinutes(r.minutes_per_week.point)}<span className="u-sr-only"> a week</span></>}
        valueHint={admin ? undefined : minutesExplained(r, windowDays)}
        open={open}
        actions={!admin && (canAutomate || onHide) ? (
          <>
            {canAutomate && (
              <button type="button" className="btn btn--secondary btn--sm" tabIndex={tab} aria-expanded={open} aria-controls={open ? peekId : undefined}
                onClick={() => setOpenId(open ? null : r.id)}>Automate</button>
            )}
            {onHide && <button type="button" className="btn btn--quiet btn--sm" tabIndex={tab} onClick={() => void onHide(r)}>Not this one</button>}
          </>
        ) : undefined}
      />,
    );
    if (open && renderPeek) {
      items.push(
        <li key={`${r.id}-peek`} className="hl-peek" id={peekId} aria-label={`Automate: ${r.label}`} onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(i); } }}>
          {renderPeek(r, () => close(i))}
        </li>,
      );
    }
  });

  return (
    <div className="hl" data-audience={audience}>
      {shown.length > 0 && (
        <ul className="hitlist" aria-label={label}>
          {items}
          {all.length > limit && (
            <li className="hl-morerow">
              <button type="button" className="hl-more" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
                {showAll ? "Show fewer" : `Show all ${all.length}`}
              </button>
            </li>
          )}
        </ul>
      )}
      {!admin && automated.length > 0 && <Automated rows={automated} windowDays={windowDays} />}
    </div>
  );
}

/** Rows that already do the work for the worker: folded away, no actions. */
function Automated({ rows, windowDays }: { rows: HitRow[]; windowDays: number }) {
  return (
    <details className="evidence hl-fold">
      <summary>Already automated <span className="num">({rows.length})</span></summary>
      <ul className="hitlist hl-fold__list" aria-label="Already automated">
        {rows.map((r) => (
          <HitListRow key={r.id} glyph={glyphOf(r.family)} label={<Label label={r.label} keyPart={r.key} />} count={`${timesText(r.count)} in ${windowDays} days`}
            chip={<Chip status={r.status} />} value={fmtMinutes(r.minutes_per_week.point)} />
        ))}
      </ul>
    </details>
  );
}
