import { useEffect, useState, type ReactNode } from "react";
import type { AnalyticMeta, Rung } from "../types";
import { ApiError } from "../api";
import { EXAMPLE_LINE, FALLBACK_LABEL, type Fallback } from "../lib/fallback";
import { AboutData, Details } from "./ui";
import { Hint } from "./Hint";

const UNIT: Record<string, [string, string]> = {
  people: ["person", "people"],
  personas: ["persona", "personas"],
  households: ["household", "households"],
  episodes: ["episode", "episodes"],
  days: ["day", "days"],
};

export function nUnit(meta: AnalyticMeta): string {
  const [one, many] = UNIT[meta.n_unit] ?? [meta.n_unit, meta.n_unit];
  return `${meta.n.toLocaleString("en-GB")} ${meta.n === 1 ? one : many}`;
}

/** Origin badge: dashed and hatched means "not real". Shown whenever origin is not "real". */
export function OriginBadge({ meta, always = false }: { meta: AnalyticMeta | null; always?: boolean }) {
  if (!meta) return null;
  if (meta.origin === "real" && !always) return null;
  return (
    <span className="pill pill--origin" data-origin={meta.origin}>
      {meta.origin}
      <span className="u-sr-only">{meta.origin === "real" ? ", measured from real people" : ", not measured from real people"}</span>
    </span>
  );
}

/** "Example data": this screen is showing a built-in sample, not what the engine holds. Dashed like the synthetic badge; the reason is in the tooltip and printed by <SourceNote>. */
export function ExampleBadge({ why }: { why: Fallback | null | undefined }) {
  if (!why) return null;
  return (
    <span className="pill pill--origin" data-origin="example">
      example data
      <span className="u-sr-only">{`. ${FALLBACK_LABEL[why.kind]}`}</span>
    </span>
  );
}

/**
 * One plain line saying the screen shows example data (the shared EXAMPLE_LINE). The engine's own sentence, with the flag name that starts a layer or the
 * error text, sits in a closed "Details" disclosure under it: on the page and one tap away (D45, a Hint never holds the only copy of an instruction or an
 * error), but not the first thing a worker reads. An engine error keeps the warning look so it is still seen.
 */
export function SourceNote({ why, also, alsoInline = false }: { why: Fallback | null | undefined; also?: ReactNode; alsoInline?: boolean }) {
  if (!why) return null;
  // `also` is the screen's second sentence about example data ("A button here only changes this screen"): behind a Hint of its own, or printed in the
  // same line with `alsoInline` for a sentence that must always be readable (an honesty statement about what example data is).
  return (
    <div className="sourcenote" data-kind={why.kind}>
      <Note tone={why.kind === "error" ? "warn" : "plain"}>
        {EXAMPLE_LINE[why.kind]}
        {also && (alsoInline ? <> {also}</> : <Hint label="About example data">{also}</Hint>)}
      </Note>
      <Details summary="Details"><p className="note" data-testid="source-detail">{why.message}</p></Details>
    </div>
  );
}

/** Footer printed under every chart: n, unit, split, interval level, origin. */
/** `brief` leaves out the long note, for a second and third chart on a page that already printed it once. */
/**
 * `variant="about"` is the worker view (D45): the origin badge stays visible and everything else (n, split, interval level, the note) sits in one
 * "About this data" disclosure. The default prints it all, which admin screens, the Evidence page and reviewers keep.
 */
export function ChartFoot({ meta, extra, brief = false, variant = "full" }: { meta: AnalyticMeta | null; extra?: ReactNode; brief?: boolean; variant?: "full" | "about" }) {
  if (variant === "about") {
    const rows: [string, ReactNode][] = meta
      ? [["n", nUnit(meta)], ...(meta.split ? ([["split", meta.split]] as [string, ReactNode][]) : []), ["intervals", `${Math.round(meta.interval_level * 100)}%`], ["origin", meta.origin], ...(extra ? ([["also", extra]] as [string, ReactNode][]) : []), ...(meta.note && !brief ? ([["note", meta.note]] as [string, ReactNode][]) : [])]
      : [["n", "not reported by the service"]];
    return (
      <div className="chart__foot chart__foot--about">
        <OriginBadge meta={meta} always />
        <AboutData rows={rows} />
      </div>
    );
  }
  if (!meta) {
    return (
      <div className="chart__foot">
        <span>n not reported by the service</span>
        {extra}
      </div>
    );
  }
  return (
    <div className="chart__foot">
      <span>
        n = <b>{nUnit(meta)}</b>
      </span>
      {meta.split && (
        <span>
          split: <b>{meta.split}</b>
        </span>
      )}
      <span>
        intervals: <b>{Math.round(meta.interval_level * 100)}%</b>
      </span>
      <OriginBadge meta={meta} always />
      {extra}
      {meta.note && !brief && <span className="chart__note">{meta.note}</span>}
    </div>
  );
}

export function PageHead({ eyebrow, title, lede, aside }: { eyebrow: string; title: string; lede?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="page__head">
      <div className="page__head-text">
        <p className="t-label">{eyebrow}</p>
        <h1 className="page__title">{title}</h1>
        {lede && <p className="t-lede">{lede}</p>}
      </div>
      {aside && <div className="page__aside">{aside}</div>}
    </header>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = window.setTimeout(() => setSlow(true), 2000); return () => window.clearTimeout(t); }, []);
  return (
    <div className="state state--loading" role="status" aria-live="polite">
      <span className="u-sr-only">{label}</span>
      <span className="skeleton skeleton--short" />
      <span className="skeleton" />
      <span className="skeleton skeleton--mid" />
      {slow && <p className="state__body">{label}. The first request after the engine starts can take several seconds while it works the numbers out. Nothing is wrong.</p>}
    </div>
  );
}

export function ErrorState({ error, retry, what }: { error: Error; retry?: () => void; what: string }) {
  const status = error instanceof ApiError ? error.status : 0;
  return (
    <div className="state state--error" role="alert">
      <span className="state__mark" aria-hidden="true" />
      <h2 className="state__title">Could not load {what}</h2>
      <p className="state__body">
        {error.message}
        {status === 0 ? " Check that the engine is running on port 7700, or use the example data." : ""}
      </p>
      {retry && (
        <button type="button" className="btn btn--secondary" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <span className="state__mark" aria-hidden="true" />
      <h2 className="state__title">{title}</h2>
      <p className="state__body">{body}</p>
      {action}
    </div>
  );
}

export function RungPill({ rung }: { rung: Rung }) {
  return (
    <span className="pill pill--rung" data-rung={rung}>
      <span className="pill__ticks" aria-hidden="true">
        <i /><i /><i />
      </span>
      <b>{rung}</b>
      <span className="u-sr-only">, autonomy rung</span>
    </span>
  );
}

const CONSENT_LABEL: Record<string, string> = {
  none: "Not decided",
  not_now: "Not now",
  never: "Never",
  shadow: "Watching first",
  approval: "With my approval",
  unattended: "While I'm away",
  paused: "Paused",
};
export function ConsentPill({ mode }: { mode: string }) {
  const m = mode in CONSENT_LABEL ? mode : "none";
  return (
    <span className="pill pill--consent" data-mode={m}>
      <span className="pill__glyph" aria-hidden="true" />
      {CONSENT_LABEL[m]}
    </span>
  );
}

export function TierPill({ tier, step }: { tier: number; step?: number }) {
  return (
    <span className="pill pill--tier">
      {step != null && <b>step {step}</b>}
      tier {tier}
      <span className="u-sr-only">{tier === 1 ? ", compiled script" : tier === 2 ? ", browser agent" : ", computer use"}</span>
    </span>
  );
}

export function LegendItem({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <li className="legend__item">
      {swatch}
      {children}
    </li>
  );
}

/** A short notice that stays out of the way. */
export function Note({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "warn" }) {
  return (
    <p className={`note${tone === "warn" ? " note--warn" : ""}`} role={tone === "warn" ? "status" : undefined}>
      {children}
    </p>
  );
}

/** Dot and whisker row used for estimates with intervals. */
export function Range({ lo, hi, pt, min, max }: { lo: number; hi: number; pt: number; min: number; max: number }) {
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100))}%`;
  return (
    <span className="range" style={{ ["--lo" as string]: pos(lo), ["--hi" as string]: pos(hi), ["--pt" as string]: pos(pt) }} aria-hidden="true">
      <span className="range__band" />
      <span className="range__pt" />
    </span>
  );
}

/** The check run after a step: a glyph and a word, so it never rests on colour alone. */
export function CheckChip({ check }: { check: "verified" | "uncertain" | "failed" }) {
  const g = { verified: ["\u2713", "verified"], uncertain: ["?", "uncertain"], failed: ["\u2715", "failed"] }[check];
  return (
    <span className="pill pill--check" data-check={check}>
      <span className="pill__glyph-char" aria-hidden="true">{g[0]}</span>{g[1]}
      <span className="u-sr-only">{check === "verified" ? ": code confirmed the result of this step" : check === "uncertain" ? ": code could not read the result of this step" : ": code found this step did not do what it should"}</span>
    </span>
  );
}

/** A run or child state as a pill: a dot for running, plain words for the rest. */
export function StatePill({ state, tone }: { state: string; tone: "go" | "good" | "bad" | "muted" }) {
  return <span className="pill pill--state" data-tone={tone}><span className="pill__dot" aria-hidden="true" />{state}</span>;
}
