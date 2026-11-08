// The sidebar: the lockup, five destinations for a worker (eight in the Admin view, with More behind them), a status line, the account button and a
// labelled Stop button. No folds, no hints, no search button (Search is Cmd-K and the first row of More on narrow windows). At 390 px it is a top bar
// (lockup, Stop, account) over a bottom bar of five items, with More (and the Admin rows that do not fit) in the top bar. Rows are 32 px; the current row has the panel colour and a 2 px accent edge.
import { DEFAULT_SCREEN, type Screen } from "../../router";
import { useAppState } from "../../store";
import { compactFor, sidebarFor, type NavEntry } from "../home/navModel";
import { useViewRole } from "../home/viewAs";
import { Lockup } from "../Lockup";
import { AccountMenu } from "./AccountMenu";
import { Icon } from "./icons";
import { MoreSheet } from "./MoreSheet";
import { StatusLine } from "./StatusLine";
import { StopButton } from "./StopControl";

function Item({ n, current, pending }: { n: NavEntry; current: string; pending: number }) {
  const count = n.id === "needs-you" && pending > 0 ? pending : 0;
  return (
    <a href={`#/${n.id}`} className="navitem" aria-current={current === n.id ? "page" : undefined}>
      {n.icon && <Icon name={n.icon} />}
      <span className="navitem__label">{n.label}</span>
      {count > 0 && <span className="navitem__count" aria-label={`${count} waiting`}>{count}</span>}
    </a>
  );
}

/** The wide sidebar. The first 40 px are the drag strip when the page is the desktop window (traffic lights sit there). */
export function Sidebar({ current }: { current: Screen | "unknown" }) {
  const view = useViewRole();
  const pending = useAppState().pendingQueue;
  const m = sidebarFor(view);
  return (
    <aside className="side" aria-label="Knack">
      <div className="side__drag" aria-hidden="true" />
      <Lockup size="sidebar" href={`#/${DEFAULT_SCREEN}`} label="Knack home" className="side__lockup" />
      <nav id="nav" aria-label="Screens" className="nav">
        {m.main.map((n) => <Item key={n.id} n={n} current={current} pending={pending} />)}
        {m.more.length > 0 && <MoreSheet current={current} />}
      </nav>
      <div className="side__status"><StatusLine /></div>
      <div className="side__foot">
        <AccountMenu placement="up" />
        <StopButton />
      </div>
    </aside>
  );
}

/** Narrow windows: a thin top bar and a bottom bar of five items. Stop is always in the top bar. An admin's other three rows and the More rows are in the top bar's sheet. */
export function CompactBars({ current }: { current: Screen | "unknown" }) {
  const view = useViewRole();
  const pending = useAppState().pendingQueue;
  const { bar: five, overflow } = compactFor(view);
  const hasSheet = overflow.length > 0 || sidebarFor(view).more.length > 0;
  return (
    <>
      <header className="topbar">
        <Lockup size="sidebar" href={`#/${DEFAULT_SCREEN}`} label="Knack home" />
        <div className="topbar__right">
          <StopButton compact />
          {hasSheet && <MoreSheet current={current} placement="bottom" />}
          <AccountMenu placement="down" />
        </div>
      </header>
      <nav className="bottombar" aria-label="Screens">
        {five.map((n) => {
          const count = n.id === "needs-you" && pending > 0 ? pending : 0;
          return (
            <a key={n.id} href={`#/${n.id}`} aria-current={current === n.id ? "page" : undefined}>
              {n.icon && <Icon name={n.icon} />}
              <span>{n.label}</span>
              {count > 0 && <span className="bottombar__count" aria-label={`${count} waiting`}>{count}</span>}
            </a>
          );
        })}
      </nav>
    </>
  );
}
