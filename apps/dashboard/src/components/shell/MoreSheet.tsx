// More: a sheet of at most ten one-line rows (docs/KNACK_UX.md section 3). No hints here (they live in the palette). On a narrow window the first
// row is Search, because the sidebar no longer has a button for it. The rows are links, so Cmd-click and the keyboard work as on any link.
import { useId } from "react";
import { groupOf, moreFor, type MoreRow } from "../home/navModel";
import { openPalette } from "../home/overlayStore";
import { isApple, shortcutLabel } from "../home/Overlays";
import { useViewRole } from "../home/viewAs";
import { Icon } from "./icons";
import { usePinnedViews } from "./pinned";
import { usePopover } from "./usePopover";

/** Consecutive rows under the same heading. */
function sections(rows: MoreRow[]): { title: string; rows: MoreRow[] }[] {
  const out: { title: string; rows: MoreRow[] }[] = [];
  for (const r of rows) {
    const last = out[out.length - 1];
    if (last && last.title === r.section) last.rows.push(r); else out.push({ title: r.section, rows: [r] });
  }
  return out;
}

/** On a narrow window the Admin destinations have no sidebar, so the sheet leads with them (Admin view only). */
const adminRows = (view: "worker" | "admin"): MoreRow[] => groupOf(view, "admin").map((e) => ({ id: e.id, label: e.label, path: `/${e.id}`, section: "Admin" }));

export function MoreSheet({ current, placement = "side" }: { current: string; placement?: "side" | "bottom" }) {
  const { open, btn, pop, close, toggle } = usePopover();
  const view = useViewRole();
  const [pinned] = usePinnedViews();
  const rows = placement === "bottom" ? [...adminRows(view), ...moreFor(view, pinned)] : moreFor(view, pinned);
  const uid = useId();
  const here = rows.some((r) => r.id === current);
  return (
    <div className="more" data-placement={placement}>
      <button
        ref={btn}
        type="button"
        className="more__btn nav__link"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="More"
        aria-current={here ? "page" : undefined}
        onClick={() => toggle(false)}
        onKeyDown={(e) => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); toggle(true); } }}
      >
        <Icon name="more" />
        <span>More</span>
      </button>
      {open && (
        <div ref={pop} className="popover more__sheet" role="menu" aria-label="More">
          <button type="button" role="menuitem" className="popover__item popover__item--row more__search" onClick={() => { close(false); openPalette(); }}>
            <span className="popover__lead"><Icon name="search" />Search</span><kbd>{isApple() ? "⌘K" : shortcutLabel()}</kbd>
          </button>
          {sections(rows).map((g) => (
            <div key={g.title} role="group" aria-labelledby={`${uid}-${g.title}`}>
              <p className="popover__group" id={`${uid}-${g.title}`}>{g.title}</p>
              {g.rows.map((r) => (
                <a key={r.id} role="menuitem" className="popover__item popover__item--row" href={`#${r.path}`} aria-current={r.id === current ? "page" : undefined} onClick={() => close(false)}>{r.label}</a>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
