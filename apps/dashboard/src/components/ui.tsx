// The design system's small components as React (packages/design/components.css is the source of truth; these emit its markup).
// Rules for new components: packages/design/README.md. Detail goes behind <Details> or a <Hint>, never printed by default.
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Hint } from "./Hint";
import { Icon, type IconName } from "./Icon";

/** The one disclosure: "Why this?", "Details". Opens in place. */
export function Details({ summary, children, defaultOpen = false, onToggle, className, wide = false }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean; onToggle?: (open: boolean) => void; className?: string; wide?: boolean }) {
  return (
    <details className={className ? `details ${className}` : "details"} open={defaultOpen || undefined} onToggle={onToggle ? (e) => onToggle((e.currentTarget as HTMLDetailsElement).open) : undefined}>
      <summary>{summary}</summary>
      <div className={wide ? "details__body details__body--wide" : "details__body"}>{children}</div>
    </details>
  );
}

/** Words in a piece of copy (a token with a letter or a digit is a word). */
export const wordCount = (t: string): number => t.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;

/** The rows of a label and value list that read at a glance, and the rows whose value is a sentence or more (those go behind one closed "More"). */
export function splitRows(rows: [string, ReactNode][], maxWords = 8): { short: [string, ReactNode][]; long: [string, ReactNode][] } {
  const short: [string, ReactNode][] = [];
  const long: [string, ReactNode][] = [];
  for (const r of rows) (typeof r[1] === "string" && wordCount(r[1]) > maxWords ? long : short).push(r);
  return { short, long };
}

/** Label and value rows. A row is `label : value`; the label never restates the title above it. */
export function FactRows({ rows, className = "about__list" }: { rows: [string, ReactNode][]; className?: string }) {
  return (
    <dl className={className}>
      {rows.map(([k, v], i) => (
        <div key={`${i}:${k}`} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Split `items` into the ones that fit in `maxWords` words (at least one) and the rest. For a list of notes that is read in an opened block. */
export function fitItems<T extends string>(items: T[], maxWords = 48): { shown: T[]; rest: T[] } {
  const shown: T[] = [];
  let used = 0;
  for (const it of items) {
    const w = wordCount(it);
    if (shown.length > 0 && used + w > maxWords) break;
    shown.push(it);
    used += w;
  }
  return { shown, rest: items.slice(shown.length) };
}

/**
 * A list of short notes (limits, caveats) that reads in an opened block: the first ones that fit, then the rest behind one closed "More". Nothing is dropped;
 * the order is the order given. An empty list draws nothing.
 */
export function NoteList({ items, maxWords = 48, more = "More" }: { items: string[]; maxWords?: number; more?: string }) {
  if (items.length === 0) return null;
  const { shown, rest } = fitItems(items, maxWords);
  return (
    <>
      <ul className="plain-list">{shown.map((t) => <li key={t} className="note">{t}</li>)}</ul>
      {rest.length > 0 && <Details summary={`${more} (${rest.length})`}><ul className="plain-list">{rest.map((t) => <li key={t} className="note">{t}</li>)}</ul></Details>}
    </>
  );
}

/**
 * The one footnote under a worker chart: n, split, interval level, method, as label and value rows. A value that is a sentence goes behind one closed
 * "More" so the opened block stays a short list. Admin and Evidence screens print their own footer instead.
 */
export function AboutData({ rows, summary = "About this data" }: { rows: [string, ReactNode][]; summary?: string }) {
  if (rows.length === 0) return null;
  const { short, long } = splitRows(rows);
  return (
    <details className="details about">
      <summary>{summary}</summary>
      <div className="details__body">
        {short.length > 0 && <FactRows rows={short} />}
        {long.length > 0 && <Details summary="More"><FactRows rows={long} /></Details>}
      </div>
    </details>
  );
}

/** A label over a clear title, with one short helper line and an optional action at the right. */
export function SectionHeader({ label, title, helper, action, as: Tag = "h2" }: { label?: string; title: string; helper?: ReactNode; action?: ReactNode; as?: "h2" | "h3" }) {
  const text = (
    <div>
      {label && <span className="t-label">{label}</span>}
      <Tag>{title}</Tag>
      {helper && <p className="part__helper">{helper}</p>}
    </div>
  );
  if (!action) return <div className="part">{label && <span className="t-label">{label}</span>}<Tag>{title}</Tag>{helper && <p className="part__helper">{helper}</p>}</div>;
  return <div className="part part--row">{text}{action}</div>;
}

/**
 * One figure: label, value with its unit, one badge. `detail` is the interval, n and split. A worker sees it behind a Hint next to the label
 * (audience "worker"); an admin, the Evidence page and reviewers see it printed under the row (audience "admin").
 */
export function MetricRow({ label, value, unit, badge, detail, audience = "worker", tone }: { label: ReactNode; value: ReactNode; unit?: string; badge?: ReactNode; detail?: ReactNode; audience?: "worker" | "admin"; tone?: "bad" }) {
  const printed = audience === "admin" && detail;
  return (
    <li className={tone === "bad" ? "metric metric--bad" : "metric"} data-detail={detail ? (printed ? "shown" : "hint") : "none"}>
      <span className="metric__label">
        {label}
        {detail && !printed && <Hint label={`About ${typeof label === "string" ? label.toLowerCase() : "this figure"}`}>{detail}</Hint>}
      </span>
      <span className="metric__value num">
        {value}
        {unit && <span className="metric__unit">{unit}</span>}
      </span>
      <span className="metric__badge">{badge}</span>
      {printed && <span className="metric__interval">{detail}</span>}
    </li>
  );
}

/** Wrap MetricRows. */
export function Metrics({ children, label }: { children: ReactNode; label?: string }) {
  return <ul className="metrics" aria-label={label}>{children}</ul>;
}

/** One sentence, then "+N more" that opens the rest in place. Lists of three or fewer short items are printed whole instead. */
export function Brief({ lead, items, show = 2 }: { lead: string; items: string[]; show?: number }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const rest = items.length - show;
  if (rest <= 1) return <p className="brief"><span className="brief__lead">{lead}</span> {items.join(", ")}</p>;
  return (
    <>
      <p className="brief">
        <span className="brief__lead">{lead}</span> {items.slice(0, show).join(", ")}{" "}
        <button type="button" className="brief__more" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>+{rest} more</button>
      </p>
      <ul className="brief__list" id={id} hidden={!open}>
        {items.map((x) => <li key={x}>{x}</li>)}
      </ul>
    </>
  );
}

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.75, strokeLinecap: "round", strokeLinejoin: "round" } as const;
export type NoticeTone = "suggest" | "ask" | "stop" | "pause" | "report" | "rule";
const NOTICE_PATH: Record<NoticeTone, string> = {
  suggest: "M4 12a8 8 0 0 1 13.7-5.6M20 12a8 8 0 0 1-13.7 5.6M18 3v4h-4M6 21v-4h4",
  ask: "M4 4h16v16H4z M8 12l3 3 5-6",
  stop: "M8 3h8l5 5v8l-5 5H8l-5-5V8z M12 8v5 M12 16v.01",
  pause: "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z M10 8v8 M14 8v8",
  report: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
  rule: "M7 3h7l4 4v14H7z M14 3v4h4 M10 12h5 M10 16h5",
};

/**
 * The one place the interface asks for attention. The icon's shape and tint say what is being asked. Two choices of one size; "Not now" decides nothing.
 * `fixed` puts it in the bottom-right corner above Stop; `inline` fills a list. Safety and approvals are never hidden by the attention layer.
 */
export function NoticeCard({ tone = "suggest", title, lines, actions, children, live = false, fixed = false, inline = false, label }: { tone?: NoticeTone; title: string; lines?: ReactNode[]; actions?: ReactNode; children?: ReactNode; live?: boolean; fixed?: boolean; inline?: boolean; label?: string }) {
  const cls = ["alert", tone !== "suggest" && `alert--${tone}`, inline && "alert--inline", fixed && "alert--fixed", live && "alert--live"].filter(Boolean).join(" ");
  return (
    <section className={cls} aria-label={label ?? title} role={tone === "stop" ? "alert" : undefined}>
      <span className="alert__icon" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 24 24" {...stroke}><path d={NOTICE_PATH[tone]} /></svg>
      </span>
      <div className="alert__text">
        <h4 className="alert__title">{title}</h4>
        {lines?.map((l, i) => <p key={i} className="alert__body">{l}</p>)}
      </div>
      {children}
      {actions && <div className="alert__actions">{actions}</div>}
    </section>
  );
}

export type Polarity = "positive" | "negative" | "neutral";
const INSIGHT_PATH: Record<Polarity, string> = {
  positive: "M4 16l5-5 4 4 7-8M15 7h5v5",
  negative: "M12 4l9 16H3z M12 10v4 M12 17v.01",
  neutral: "M8.5 12a3.5 3.5 0 1 0 7 0 3.5 3.5 0 0 0-7 0",
};

/**
 * One pointer. Glyph and a word carry the polarity, never colour alone. A worker gets a sentence and one action, no statistics;
 * an admin also gets `stats` (interval, n, origin) printed.
 */
export function InsightCard({ polarity, label, title, text, action, stats }: { polarity: Polarity; label: string; title: string; text?: ReactNode; action?: ReactNode; stats?: ReactNode }) {
  return (
    <article className="insight" data-polarity={polarity}>
      <span className="insight__glyph" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" {...stroke} strokeWidth={1.9}><path d={INSIGHT_PATH[polarity]} /></svg>
      </span>
      <div className="insight__head">
        <span className="insight__label">{label}</span>
        <h4 className="insight__title">{title}</h4>
      </div>
      {text && <p className="insight__text">{text}</p>}
      {action && <div className="insight__action">{action}</div>}
      {stats && <p className="insight__stats">{stats}</p>}
    </article>
  );
}

/** Cue's one multiple-choice question. "Something else" is always last; Esc dismisses. */
export function QuestionCard({ question, options, other, chord = "⌥", onAnswer, onOther, onDismiss }: { question: string; options: { id: string; key: string; label: string }[]; other?: { key: string; label: string }; chord?: string; onAnswer?: (id: string) => void; onOther?: () => void; onDismiss?: () => void }) {
  return (
    <div className="qcard" role="dialog" aria-label={question}>
      <div className="qcard__head">
        <p className="qcard__q">{question}</p>
        <button type="button" className="qcard__esc" aria-label="Dismiss" onClick={onDismiss}>esc</button>
      </div>
      <div className="qcard__rows" role="group" aria-label="Options">
        {options.map((o) => (
          <button key={o.id} type="button" className="qcard__row" aria-keyshortcuts={`Alt+${o.key}`} onClick={() => onAnswer?.(o.id)}>
            <span className="qcard__cap">{chord}{o.key}</span>{o.label}
          </button>
        ))}
        {other && (
          <button type="button" className="qcard__row qcard__row--else" onClick={onOther}>
            <span className="qcard__cap">{chord}{other.key}</span>{other.label}
          </button>
        )}
      </div>
    </div>
  );
}

/** A list of rows: hairlines, not a stack of cards. Put <Row> inside. */
export function Rows({ children, label }: { children: ReactNode; label?: string }) {
  return <ul className="listrows" aria-label={label}>{children}</ul>;
}

/**
 * One 44 px row. A row that goes somewhere is a link (or a button) and the whole row is the target, with a chevron; a plain row may carry
 * `actions`, which appear on hover and focus and are always visible on touch. A link or button row cannot hold other buttons, so `actions`
 * only render on a plain row. Title is one line (12 words), the muted `meta` line at most 6.
 */
export function Row({ title, meta, icon, tone, href, onClick, chevron, end, actions, current, pressed, label }: {
  title: ReactNode;
  meta?: ReactNode;
  icon?: IconName;
  /** Colours the icon only; the title or the meta line always says the same thing in words. */
  tone?: "bad" | "good" | "warn";
  href?: string;
  onClick?: () => void;
  /** Shown automatically for a link or button row; pass false to hide. */
  chevron?: boolean;
  end?: ReactNode;
  actions?: ReactNode;
  current?: boolean;
  /** A button row that switches something on or off (a skill filtering a chart): drawn as a toggle button. */
  pressed?: boolean;
  label?: string;
}) {
  const inner = (
    <>
      {icon && <span className={`listrow__icon${tone ? ` listrow__icon--${tone}` : ""}`}><Icon name={icon} /></span>}
      <span className="listrow__text">
        <span className="listrow__title">{title}</span>
        {meta && <span className="listrow__meta">{meta}</span>}
      </span>
      {end && <span className="listrow__end">{end}</span>}
    </>
  );
  const goes = Boolean(href || onClick);
  const chev = chevron ?? goes;
  const chevNode = chev ? <span className="listrow__chev"><Icon name="chevron" /></span> : null;
  if (href) return <li><a className="listrow" href={href} aria-current={current ? "page" : undefined} aria-label={label}>{inner}{chevNode}</a></li>;
  if (onClick) return <li><button type="button" className="listrow" onClick={onClick} aria-current={current ? "true" : undefined} aria-pressed={pressed} aria-label={label}>{inner}{chevNode}</button></li>;
  return <li><div className="listrow" aria-label={label}>{inner}{actions && <span className="listrow__actions">{actions}</span>}{chevNode}</div></li>;
}

/**
 * The inline "Forget it / Keep" row that stands where a modal would. The consequence is printed (never only in a Hint), the safe choice
 * ("Keep") has the focus when the row opens, and Escape means Keep. Both choices are real clicks; no shortcut confirms.
 */
export function ConfirmRow({ question, consequence, confirmLabel, cancelLabel = "Keep", onConfirm, onCancel, busy = false }: {
  question: ReactNode;
  consequence?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  const keep = useRef<HTMLButtonElement>(null);
  useEffect(() => { keep.current?.focus(); }, []);
  return (
    <li>
      <div className="confirm-row" role="group" aria-label={typeof question === "string" ? question : "Confirm"} onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onCancel(); } }}>
        <span className="confirm-row__q">{question}</span>
        {consequence && <span className="confirm-row__why">{consequence}</span>}
        <span className="confirm-row__actions">
          <button type="button" className="btn btn--secondary btn--sm" ref={keep} onClick={onCancel}>{cancelLabel}</button>
          <button type="button" className="btn btn--danger btn--sm" onClick={onConfirm} disabled={busy}>{confirmLabel}</button>
        </span>
      </div>
    </li>
  );
}
