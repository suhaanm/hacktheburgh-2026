import type { ReactNode } from "react";
import type { AnalyticMeta, Rung } from "../types";
import { ApiError } from "../api";

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
    <span className="pill pill--origin" data-origin={meta.origin} title={meta.origin === "real" ? "Measured from real people" : "Not measured from real people"}>
      {meta.origin}
    </span>
  );
}

/** Footer printed under every chart: n, unit, split, interval level, origin. */
export function ChartFoot({ meta, extra }: { meta: AnalyticMeta | null; extra?: ReactNode }) {
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
  return (
    <div className="state state--loading" role="status" aria-live="polite">
      <span className="u-sr-only">{label}</span>
      <span className="skeleton skeleton--short" />
      <span className="skeleton" />
      <span className="skeleton skeleton--mid" />
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
        {status === 0 ? " Check that the engine is running on port 7700, or use the demo data." : ""}
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
    <span className="pill pill--rung" data-rung={rung} title={`Autonomy rung ${rung}`}>
      <span className="pill__ticks" aria-hidden="true">
        <i /><i /><i />
      </span>
      <b>{rung}</b>
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
    <span className="pill pill--tier" title={tier === 1 ? "Compiled script" : tier === 2 ? "Browser agent" : "Computer use"}>
      {step != null && <b>step {step}</b>}
      tier {tier}
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
