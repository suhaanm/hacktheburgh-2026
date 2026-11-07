import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import "./hint.css";

/**
 * A small accessible hint: an "i" button that opens a short popover on hover, focus or tap. Escape closes it, so does a click
 * elsewhere. It carries detail the screen can do without (an interval, a sample size, where a number comes from), never the
 * only copy of something the person must read. Local stand-in until the shared Hint from packages/design lands.
 */
export function Hint({ label, children, align = "start" }: { label: string; children: ReactNode; align?: "start" | "end" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLSpanElement>(null);
  const hover = useRef(false);
  const close = useCallback(() => { hover.current = false; setOpen(false); }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    const onDown = (e: PointerEvent) => { if (root.current && !root.current.contains(e.target as Node)) close(); };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onDown, true);
    return () => { document.removeEventListener("keydown", onKey, true); document.removeEventListener("pointerdown", onDown, true); };
  }, [open, close]);

  return (
    <span
      ref={root}
      className="hint"
      onPointerEnter={(e) => { if (e.pointerType === "mouse") { hover.current = true; setOpen(true); } }}
      onPointerLeave={(e) => { if (e.pointerType === "mouse" && hover.current) close(); }}
      onBlur={(e) => { if (!root.current?.contains(e.relatedTarget as Node | null)) close(); }}
    >
      <button type="button" className="hint__btn" aria-label={label} aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => { hover.current = false; setOpen((o) => !o); }}>
        <span aria-hidden="true">i</span>
      </button>
      {open && <span id={id} role="note" className="hint__pop" data-align={align}>{children}</span>}
    </span>
  );
}
