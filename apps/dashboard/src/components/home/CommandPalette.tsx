import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { navigate, screenOf, useRoute } from "../../router";
import type { WireOverview, WireWorker } from "../firm/wire";
import { DEFAULT_SCREEN, canView } from "./navModel";
import { closePalette, getOverlay, openAbout, openSettings, startTour, useOverlay } from "./overlayStore";
import { capsOf, getBridge } from "../shell/bridge";
import { useStop } from "../shell/StopControl";
import { useToast } from "../Toasts";
import { copyText, mondayNote } from "./monday";
import {
  KIND_LABEL, NO_RESULTS_HELP, askItem, buildItems, groupRows, isNavKey, moveIndex, resultsText, rowsFor, segments, type ExtraItems, type PaletteItem, type Row,
} from "./palette";
import { setViewRole, useViewRole, type ViewRole } from "./viewAs";
import "./palette.css";

/** Where the insight rows come from. Injected, so the palette never fetches on its own and a missing loader only means no insight rows. */
export interface PaletteLoaders {
  worker: () => Promise<WireWorker | null>;
  overview: () => Promise<WireOverview | null>;
}

/** What the last open saw, so the next open shows insight rows at once and refreshes them behind. Memory only. */
const cache: Partial<Record<ViewRole, ExtraItems>> = {};

/** Command palette: Cmd+K or Ctrl+K. A search over screens, Firm views, insights and a few actions. Mount once (see Overlays). */
export function CommandPalette({ loaders }: { loaders?: PaletteLoaders }) {
  const { palette } = useOverlay();
  return palette ? <PaletteDialog loaders={loaders} /> : null;
}

type Done = "opener" | "main" | "none";

function PaletteDialog({ loaders }: { loaders?: PaletteLoaders }) {
  const view = useViewRole();
  const route = useRoute();
  const uid = useId();
  const listId = `${uid}-list`;
  const titleId = `${uid}-title`;
  const optId = (i: number) => `${uid}-opt-${i}`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [opener] = useState<Element | null>(() => (typeof document === "undefined" ? null : document.activeElement));
  const done = useRef<Done>("opener");

  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [active, setActive] = useState(0);
  const [extra, setExtra] = useState<ExtraItems>(() => cache[view] ?? {});

  // Insights load only now, after the palette first opens, and only through the injected loaders.
  useEffect(() => {
    if (!loaders) return;
    let alive = true;
    const take = (e: ExtraItems) => { cache[view] = e; if (alive) setExtra(e); };
    if (view === "worker") loaders.worker().then((w) => { if (w) take({ pointers: w.pointers }); }).catch(() => undefined);
    else loaders.overview().then((o) => { if (o) take({ insights: o.top }); }).catch(() => undefined);
    return () => { alive = false; };
  }, [loaders, view]);

  const caps = useMemo(() => capsOf(), []);
  const items = useMemo(() => buildItems(view, extra, caps), [view, extra, caps]);
  const result = useMemo(() => rowsFor(items, query, expanded), [items, query, expanded]);
  // What was typed matches nothing and the desktop app can take a question: the one row is "Ask Knack: <phrase>".
  const asking = result.rows.length === 0 && query.trim() !== "" && caps.ask;
  const rows: Row[] = asking ? [{ type: "item", item: askItem(query), positions: [] }] : result.rows;
  const total = asking ? 1 : result.total;
  const stop = useStop();
  const toast = useToast();
  // Headings only for the plain list. Search results are in order of relevance, not by group, and the kind label on each row says what it is.
  const groups = useMemo(() => groupRows(rows, query.trim() === ""), [rows, query]);
  const activeId = rows.length > 0 && active >= 0 && active < rows.length ? optId(active) : undefined;

  // Focus the field on open. On close, focus goes back to where it was (or to the screen, when the palette took the person somewhere).
  useEffect(() => {
    inputRef.current?.focus({ preventScroll: true });
    return () => {
      const how = done.current;
      if (how === "none") return;
      window.setTimeout(() => {
        if (getOverlay().palette) return; // a development double-mount, or the palette was opened again: leave focus where it is
        if (how === "main") document.getElementById("main")?.focus({ preventScroll: true });
        else if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
      }, 0);
    };
  }, [opener]);

  useEffect(() => { if (activeId) document.getElementById(activeId)?.scrollIntoView({ block: "nearest" }); }, [activeId]);

  const close = useCallback(() => { done.current = "opener"; closePalette(); }, []);

  const run = useCallback((item: PaletteItem) => {
    const t = item.target;
    if (t.type === "route") {
      done.current = "main";
      closePalette();
      navigate(t.path);
      return;
    }
    if (t.action === "tour") {
      // Give focus back first, so the tour remembers a real element to return to.
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
      done.current = "none";
      closePalette();
      startTour();
      return;
    }
    done.current = "opener";
    closePalette();
    if (t.action === "stop") { void stop.stop(); return; }
    if (t.action === "settings") { done.current = "none"; openSettings(); return; }
    if (t.action === "about") { done.current = "none"; openAbout(); return; }
    if (t.action === "monday") {
      void (async () => {
        const w = await loaders?.worker().catch(() => null);
        const note = w ? mondayNote(w) : null;
        if (!note) { toast({ tone: "plain", text: "Nothing to copy yet.", detail: "A week with no pointers has no note." }); return; }
        toast((await copyText(note)) ? { tone: "success", text: "Copied your Monday note." } : { tone: "error", text: "Your browser blocked copying.", detail: "Nothing was copied." });
      })();
      return;
    }
    const bridge = getBridge();
    if (t.action === "ask") { bridge.ask?.(t.phrase); return; }
    if (t.action === "pause") { bridge.pause?.(60); toast({ tone: "plain", text: "Paused for 1 hour." }); return; }
    if (t.action === "accessibility") { bridge.openSystemSettings?.("accessibility"); return; }
    if (t.action === "view_admin") { setViewRole("admin"); navigate("/firm"); } // an admin lands on Firm
    else {
      setViewRole("worker");
      // Leaving the Admin view on an admin screen goes to the home screen, never to a blank gate.
      if (!canView(screenOf(route), "worker")) navigate(`/${DEFAULT_SCREEN}`);
    }
  }, [opener, route, stop, toast, loaders]);

  const activate = useCallback((row: Row | undefined, index: number) => {
    if (!row) return;
    if (row.type === "more") { setExpanded(true); setActive(index); return; }
    run(row.item);
  }, [run]);

  const onKey = (e: ReactKeyboardEvent) => {
    if (e.key === "Escape") {
      // Shift+Escape is the stop-everything shortcut: leave it alone so it still reaches the window.
      if (e.shiftKey) return;
      e.preventDefault();
      e.stopPropagation();
      close();
      return;
    }
    if (e.key === "Tab") { e.preventDefault(); inputRef.current?.focus(); return; } // the field is the one control: focus stays in the dialog
    if (isNavKey(e.key)) {
      e.preventDefault();
      setActive((a) => moveIndex(a, e.key as Parameters<typeof moveIndex>[1], rows.length));
      return;
    }
    if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); activate(rows[active], active); }
  };

  const placeholder = view === "admin" ? "Go to a screen, an insight or an action" : "Go to a screen, a pointer or an action";

  return (
    <div className="palette">
      <div className="palette__scrim" aria-hidden="true" onMouseDown={close} />
      <div
        className="palette__box" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={onKey}
        onMouseDown={(e) => { if (e.target !== inputRef.current) e.preventDefault(); }}
      >
        <h2 id={titleId} className="u-sr-only">Search screens, insights and actions</h2>
        <div className="palette__field">
          <input
            ref={inputRef} className="palette__input" type="text" role="combobox" aria-label="Search" aria-autocomplete="list"
            aria-expanded={rows.length > 0} aria-controls={rows.length > 0 ? listId : undefined} aria-activedescendant={activeId}
            placeholder={placeholder} autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false}
            value={query} onChange={(e) => { setQuery(e.target.value); setExpanded(false); setActive(0); }}
          />
          <kbd className="palette__esc" aria-hidden="true">Esc</kbd>
        </div>
        {rows.length > 0 ? (
          <div id={listId} className="palette__list" role="listbox" aria-label="Results">
            {groups.map((g, gi) => (
              <div key={`${g.heading ?? "more"}-${gi}`} role={g.heading ? "group" : "presentation"} aria-labelledby={g.heading ? `${uid}-g${gi}` : undefined} className="palette__group">
                {g.heading && <p id={`${uid}-g${gi}`} className="palette__heading" role="presentation">{g.heading}</p>}
                {g.rows.map(({ row, index }) => (
                  <div
                    key={row.type === "item" ? row.item.id : "more"} id={optId(index)} role="option" aria-selected={index === active}
                    className="palette__opt" data-active={index === active} data-kind={row.type === "item" ? row.item.kind : "more"}
                    onMouseMove={() => { if (index !== active) setActive(index); }} onClick={() => activate(row, index)}
                  >
                    {row.type === "item" ? (
                      <>
                        <span className="palette__main">
                          <span className="palette__label">
                            {segments(row.item.label, row.positions).map((s, k) => (s.hit ? <mark key={k} className="palette__mark">{s.text}</mark> : <span key={k}>{s.text}</span>))}
                          </span>
                          <span className="palette__hint">{row.item.hint}</span>
                        </span>
                        <span className="palette__kind">{KIND_LABEL[row.item.kind]}</span>
                      </>
                    ) : (
                      <>
                        <span className="palette__main"><span className="palette__label">Show all {row.count}</span></span>
                        <span className="palette__kind">Enter</span>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="palette__empty">
            <p className="palette__none">Nothing matches &ldquo;{query.trim()}&rdquo;.</p>
            <p className="palette__try">{NO_RESULTS_HELP}</p>
          </div>
        )}
        <p className="palette__keys" aria-hidden="true">
          <span><kbd>&uarr;</kbd><kbd>&darr;</kbd> move</span>
          <span><kbd>Enter</kbd> open</span>
          <span><kbd>Esc</kbd> close</span>
        </p>
        <p className="u-sr-only" role="status" aria-live="polite">{resultsText(total)}</p>
      </div>
    </div>
  );
}
