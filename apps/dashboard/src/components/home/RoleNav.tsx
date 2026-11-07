import { useEffect, useState } from "react";
import { groupOf, inGroup, type NavEntry, type NavGroup } from "./navModel";
import { useViewRole } from "./viewAs";
import type { Screen } from "../../router";

/** The menu, built from navModel.ts and the demo view. Same classes as before; the quieter screens fold away until asked for. */
function Link({ n, current, pending }: { n: NavEntry; current: string; pending: number }) {
  return (
    <a href={`#/${n.id}`} className="nav__link" aria-current={current === n.id ? "page" : undefined}>
      <span className="nav__label">{n.label}</span>
      {n.id === "queue" && pending > 0 && <span className="nav__count" aria-label={`${pending} waiting`}>{pending}</span>}
      <span className="nav__hint">{n.hint}</span>
    </a>
  );
}

const read = (key: string): boolean => { try { return window.localStorage.getItem(key) === "1"; } catch { return false; } };
const write = (key: string, v: boolean): void => { try { window.localStorage.setItem(key, v ? "1" : "0"); } catch { /* storage can be blocked */ } };

/** A folded group. It opens by itself when you are on one of its screens, and remembers what you chose. */
function Fold({ id, title, hint, group, current, pending, storageKey }: { id: string; title: string; hint: string; group: NavGroup; current: string; pending: number; storageKey: string }) {
  const view = useViewRole();
  const items = groupOf(view, group);
  const inside = inGroup(current as Screen, group);
  const [open, setOpen] = useState<boolean>(() => read(storageKey));
  useEffect(() => { if (inside) setOpen(true); }, [inside]);
  const toggle = () => { const v = !open; setOpen(v); write(storageKey, v); };
  return (
    <div className="nav__more">
      <button type="button" className="nav__morebtn" aria-expanded={open} aria-controls={id} onClick={toggle}>
        <span className="nav__label">{title}</span>
        <span className="nav__chev" aria-hidden="true" data-open={open} />
        {!open && <span className="nav__hint">{hint}</span>}
      </button>
      <div id={id} className="nav__morelist" hidden={!open}>
        {items.map((n) => <Link key={n.id} n={n} current={current} pending={pending} />)}
      </div>
    </div>
  );
}

export function RoleNav({ current, pending }: { current: string; pending: number }) {
  const view = useViewRole();
  return (
    <>
      {groupOf(view, "main").map((n) => <Link key={n.id} n={n} current={current} pending={pending} />)}
      <Fold id="nav-details" title="Details" hint="Genome, Presence, Graph, Week and more" group="details" current={current} pending={pending} storageKey="understudy-nav-details" />
      <Fold id="nav-more" title="More" hint="Today, Memory, Notices, Briefing and more" group="more" current={current} pending={pending} storageKey="understudy-nav-more" />
      {groupOf(view, "reviewers").map((n) => <Link key={n.id} n={n} current={current} pending={pending} />)}
    </>
  );
}
