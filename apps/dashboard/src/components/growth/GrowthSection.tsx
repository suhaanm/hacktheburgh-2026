import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError } from "../../api";
import { safeWhy } from "../../lib/voice";
import { Details } from "../ui";
import type { Fallback } from "../../lib/fallback";

/**
 * One section of the Growth page: a short title, ONE headline sentence from the data, and the numbers behind one closed disclosure
 * (docs/knack-ux/views.md: a worker sees only their own work and one experienced worker's way of doing the task).
 * The section opens by itself when the address names it (`?section=`).
 */
export function GrowthSection({ id, title, headline, children, open = false, summary = "See the numbers", busy = false }: {
  id: string;
  title: string;
  headline: ReactNode;
  children?: ReactNode;
  open?: boolean;
  summary?: string;
  busy?: boolean;
}) {
  return (
    <section id={`gr-${id}`} className="gr-sec" aria-labelledby={`gr-${id}-h`} aria-busy={busy || undefined} style={{ scrollMarginTop: "var(--space-5)" }}>
      <p className="gr-sec__title" aria-hidden="true">{title}</p>
      <h2 id={`gr-${id}-h`} className="gr-sec__headline"><span className="u-sr-only">{title}. </span>{headline}</h2>
      {children != null && <Details key={open ? "open" : "closed"} summary={summary} wide defaultOpen={open}>{children}</Details>}
    </section>
  );
}

/* -- One origin pill for the whole page -----------------------------------------------------------------------------------------
 * Each section loads its own data. The page head draws the one origin pill; when any section shows example data the pill says so
 * (and the section's own footer says where its numbers came from). A section reports what it is showing, the page reads the first. */
type Why = Fallback | null;
type Report = (id: string, why: Why) => void;
const ReportCtx = createContext<Report>(() => {});
const WhysCtx = createContext<Record<string, Why>>({});

export function SectionSources({ children }: { children: ReactNode }) {
  const [whys, setWhys] = useState<Record<string, Why>>({});
  const report = useMemo<Report>(() => (id, why) => setWhys((w) => (w[id] === why ? w : { ...w, [id]: why })), []);
  return <ReportCtx.Provider value={report}><WhysCtx.Provider value={whys}>{children}</WhysCtx.Provider></ReportCtx.Provider>;
}

/** A section calls this with the `why` of its data (null when the data is real). */
export function useReportSource(id: string, why: Why): void {
  const report = useContext(ReportCtx);
  useEffect(() => { report(id, why ?? null); return () => report(id, null); }, [report, id, why]);
}

/** The first section that shows example data, or null. */
export function useExampleSource(): Why {
  const whys = useContext(WhysCtx);
  return safeWhy(Object.values(whys).find((w) => w != null) ?? null);
}

/**
 * A section whose data could not be read. The engine's own message is never printed here: it can name other people ("Try one of: ...") or
 * the service's insides. An unknown worker or nothing recorded yet is a calm empty state; anything else says the read failed and offers to retry.
 */
export function SectionError({ error, retry, what, empty }: { error: Error; retry: () => void; what: string; empty: string }) {
  const none = error instanceof ApiError && (error.status === 404 || error.status === 422);
  return (
    <div className="state state--error" role={none ? "status" : "alert"}>
      <p className="state__body">{none ? empty : `Knack could not read ${what} just now.`}</p>
      {!none && <button type="button" className="btn btn--secondary btn--sm" onClick={retry}>Try again</button>}
    </div>
  );
}
