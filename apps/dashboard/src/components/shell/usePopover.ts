// A small popover behaviour for the account menu and the More sheet: open and close, close on an outside press or Escape (focus goes back to
// the button), arrow keys move between items, and the first item takes focus when it opens by keyboard. Kept free of any library.
import { useCallback, useEffect, useRef, useState } from "react";

const ITEMS = '[role="menuitem"],[role="menuitemradio"],[role="menuitemcheckbox"]';

export function usePopover() {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const byKey = useRef(false);

  const close = useCallback((restore = true) => { setOpen(false); if (restore) btn.current?.focus(); }, []);
  const toggle = useCallback((fromKey = false) => { byKey.current = fromKey; setOpen((o) => !o); }, []);

  useEffect(() => {
    if (!open) return;
    if (byKey.current) pop.current?.querySelector<HTMLElement>(ITEMS)?.focus();
    const down = (e: MouseEvent) => {
      const t = e.target as Node;
      if (pop.current?.contains(t) || btn.current?.contains(t)) return;
      setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); close(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Home" && e.key !== "End") return;
      const items = Array.from(pop.current?.querySelectorAll<HTMLElement>(ITEMS) ?? []);
      if (!items.length) return;
      e.preventDefault();
      const at = items.indexOf(document.activeElement as HTMLElement);
      const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : e.key === "ArrowDown" ? (at + 1) % items.length : (at <= 0 ? items.length - 1 : at - 1);
      items[next].focus();
    };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key, true);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key, true); };
  }, [open, close]);

  return { open, btn, pop, close, toggle, setOpen };
}
