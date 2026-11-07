// The design system's small components as React (packages/design/components.css is the source of truth; these emit its markup).
// Rules for new components: packages/design/README.md. Detail goes behind <Details> or a <Hint>, never printed by default.
import { useId, useState, type ReactNode } from "react";
import { Hint } from "./Hint";

/** The one disclosure: "Why this?", "Details". Opens in place. */
export function Details({ summary, children, defaultOpen = false, onToggle, className, wide = false }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean; onToggle?: (open: boolean) => void; className?: string; wide?: boolean }) {
  return (
    <details className={className ? `details ${className}` : "details"} open={defaultOpen || undefined} onToggle={onToggle ? (e) => onToggle((e.currentTarget as HTMLDetailsElement).open) : undefined}>
      <summary>{summary}</summary>
      <div className={wide ? "details__body details__body--wide" : "details__body"}>{children}</div>
    </details>
  );
}

/** The one footnote under a worker chart: n, split, interval level, method, in a short key list. Admin and Evidence screens print their own footer instead. */
export function AboutData({ rows, summary = "About this data" }: { rows: [string, ReactNode][]; summary?: string }) {
  if (rows.length === 0) return null;
  return (
    <details className="details about">
      <summary>{summary}</summary>
      <div className="details__body">
        <dl className="about__list">
          {rows.map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
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
