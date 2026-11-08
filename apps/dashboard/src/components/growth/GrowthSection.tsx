import type { ReactNode } from "react";
import { ApiError } from "../../api";
import { Details } from "../ui";

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
    <section id={`gr-${id}`} className="gr-sec" aria-label={title} aria-busy={busy || undefined} style={{ scrollMarginTop: "var(--space-5)" }}>
      <p className="gr-sec__title" aria-hidden="true">{title}</p>
      <h2 id={`gr-${id}-h`} className="gr-sec__headline">{headline}</h2>
      {children != null && <Details key={open ? "open" : "closed"} summary={summary} wide defaultOpen={open}>{children}</Details>}
    </section>
  );
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
