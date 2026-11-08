import { useEffect, useState, type ReactNode } from "react";
import type { AnalyticMeta, Rung } from "../types";
import { ApiError } from "../api";
import { AboutData } from "./ui";

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

/** Footer printed under every chart: n, unit, split, interval level. */
/** `brief` leaves out the long note, for a second and third chart on a page that already printed it once. */
/**
 * `variant="about"` is the worker view (D45): n, split, interval level and the note sit in one
 * "About this data" disclosure. The default prints it all, which admin screens, the Evidence page and reviewers keep.
 */
export function ChartFoot({ meta, extra, brief = false, variant = "full" }: { meta: AnalyticMeta | null; extra?: ReactNode; brief?: boolean; variant?: "full" | "about" }) {
  if (variant === "about") {
    const rows: [string, ReactNode][] = meta
      ? [["n", nUnit(meta)], ...(meta.split ? ([["split", meta.split]] as [string, ReactNode][]) : []), ["intervals", `${Math.round(meta.interval_level * 100)}%`], ...(extra ? ([["also", extra]] as [string, ReactNode][]) : []), ...(meta.note && !brief ? ([["note", meta.note]] as [string, ReactNode][]) : [])]
      : [["n", "not reported by the service"]];
    return (
      <div className="chart__foot chart__foot--about">
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
      {extra}
      {meta.note && !brief && <span className="chart__note">{meta.note}</span>}
    </div>
  );
}

/**
 * The head of a screen (KNACK_UX section 6): a title, at most one printed line (a real limit or a use rule, never a lede), and the badge.
 * No eyebrow: it repeated the sidebar label. `eyebrow` is still accepted so older call sites compile, and is not drawn.
 */
export function PageHead({ title, lede, aside, hero = false }: { eyebrow?: string; title: string; lede?: ReactNode; aside?: ReactNode; hero?: boolean }) {
  return (
    <header className="screenhead">
      <div className="screenhead__row">
        {hero ? <h1 className="hero-insight">{title}</h1> : <h1 className="screenhead__title">{title}</h1>}
        {aside && <div className="page__aside">{aside}</div>}
      </div>
      {lede && <p className="screenhead__limit">{lede}</p>}
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
      {slow && <p className="state__body">Starting Knack, about 20 seconds.</p>}
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
        {status === 0 ? " Check that the engine is running on port 7700." : ""}
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

/** A run or node state as a dot and a word, not a pill: a list of runs is rows, and one pill per screen is the origin badge. Shape-free tone, the word always travels with it. */
export function StateText({ state, tone }: { state: string; tone: "go" | "good" | "bad" | "muted" }) {
  return <span className="statetext" data-tone={tone}><span className="statetext__dot" aria-hidden="true" />{state}</span>;
}
