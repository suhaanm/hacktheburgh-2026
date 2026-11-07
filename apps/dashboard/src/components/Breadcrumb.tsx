// The breadcrumb that replaces the "These are the detailed numbers" frame note (KNACK_UX section 2, offender 3): a screen says where it sits instead
// of apologising for being detailed. Items before the last are links; the last is the current page.
import { Fragment } from "react";

export interface Crumb { label: string; href?: string }

export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <p className="crumb">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <Fragment key={`${c.label}-${i}`}>
              {i > 0 && <span className="crumb__sep" aria-hidden="true">/</span>}
              {last || !c.href ? <span aria-current={last ? "page" : undefined}>{c.label}</span> : <a href={c.href}>{c.label}</a>}
            </Fragment>
          );
        })}
      </p>
    </nav>
  );
}
