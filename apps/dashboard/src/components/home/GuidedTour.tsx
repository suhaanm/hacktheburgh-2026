import { useCallback, useEffect, useRef, useState } from "react";
import { navigate, useRoute } from "../../router";
import { endTour, getOverlay, setTourStep, takeTourReturn, useOverlay } from "./overlayStore";
import { anchorSelector, clampStep, progressShare, progressText, ringBox, ringable, stepAfterViewChange, tourSteps, type Rect } from "./tour";
import { useViewRole } from "./viewAs";
import "./tour.css";

/** The guided tour: a short card and a thin ring. It never starts by itself and is always skippable. Mount once (see Overlays). */
export function GuidedTour() {
  const { tour } = useOverlay();
  return tour ? <TourCard step={tour.step} /> : null;
}

const RING_PAD = 4;
const isEditable = (t: EventTarget | null): boolean => {
  const el = t as HTMLElement | null;
  return !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
};
const sameBox = (a: Rect | null, b: Rect | null): boolean => (a === b) || (!!a && !!b && a.left === b.left && a.top === b.top && a.width === b.width && a.height === b.height);

function TourCard({ step }: { step: number }) {
  const view = useViewRole();
  const route = useRoute();
  const steps = tourSteps(view);
  const idx = clampStep(step, steps.length);
  const s = steps[idx];
  const last = idx === steps.length - 1;
  const primary = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLElement>(null);
  const [box, setBox] = useState<Rect | null>(null);

  // The view can change under the tour (the palette's switch). Keep the same step by its id, or end the tour if the step is gone.
  const prevView = useRef(view);
  useEffect(() => {
    if (prevView.current === view) return;
    const mapped = stepAfterViewChange(prevView.current, step, view);
    prevView.current = view;
    if (mapped === null) endTour(); else setTourStep(mapped);
  }, [view, step]);

  // Each step shows its screen. Only on a step change: if the person goes somewhere else themselves, the tour does not drag them back.
  const routePath = useRef(route.path);
  routePath.current = route.path;
  useEffect(() => { if (s?.route && routePath.current !== s.route) navigate(s.route); }, [s?.id, s?.route]);

  // The ring: only around something that is on screen. A closed menu or a folded group has nothing to ring, and the card stands alone.
  const measure = useCallback(() => {
    const sel = s ? anchorSelector(s) : null;
    const el = sel ? document.querySelector(sel) : null;
    if (!el || el.getClientRects().length === 0 || getComputedStyle(el).visibility === "hidden") { setBox((b) => (b ? null : b)); return; }
    const r = el.getBoundingClientRect();
    const vp = { width: window.innerWidth, height: window.innerHeight };
    const next = ringable(r, vp) ? ringBox({ left: r.left, top: r.top, width: r.width, height: r.height }, RING_PAD, vp) : null;
    setBox((b) => (sameBox(b, next) ? b : next));
  }, [s]);
  useEffect(() => {
    measure();
    const frames = [requestAnimationFrame(() => requestAnimationFrame(measure))];
    const timers = [window.setTimeout(measure, 250), window.setTimeout(measure, 900)]; // lazy screens and the menu settle after the route changes
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    window.addEventListener("hashchange", measure);
    return () => {
      frames.forEach(cancelAnimationFrame);
      timers.forEach(window.clearTimeout);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("hashchange", measure);
    };
  }, [measure]);

  const next = useCallback(() => { if (last) endTour(); else setTourStep(idx + 1); }, [last, idx]);
  const back = useCallback(() => { if (idx > 0) setTourStep(idx - 1); }, [idx]);

  // Focus: the primary button, on open and on each step (unless the person has moved focus somewhere else on purpose).
  const opened = useRef(false);
  useEffect(() => {
    const a = document.activeElement;
    if (!opened.current || !a || a === document.body || card.current?.contains(a)) primary.current?.focus({ preventScroll: true });
    opened.current = true;
  }, [idx]);
  // Back to where it was, once the tour is really over (not on a development double-mount).
  useEffect(() => () => {
    window.setTimeout(() => {
      if (getOverlay().tour) return;
      const el = takeTourReturn();
      if (el && el.isConnected) el.focus({ preventScroll: true });
    }, 0);
  }, []);

  // Keys: Escape skips, Left and Right move, Enter moves on when focus is on nothing in particular.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (getOverlay().palette || e.defaultPrevented) return;
      if (e.key === "Escape" && !e.shiftKey) { e.preventDefault(); endTour(); return; } // Shift+Escape stays the stop shortcut
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || isEditable(e.target)) return;
      if (e.key === "ArrowRight") { e.preventDefault(); next(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); back(); }
      else if (e.key === "Enter" && (!document.activeElement || document.activeElement === document.body)) { e.preventDefault(); next(); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [next, back]);

  if (!s) return null;
  const share = progressShare(idx, steps.length);
  return (
    <>
      {box && <div className="tour__ring" aria-hidden="true" style={{ left: box.left, top: box.top, width: box.width, height: box.height }} />}
      <section ref={card} className="tour" role="dialog" aria-modal="false" aria-labelledby="tour-title" aria-describedby="tour-text">
        <div
          className="progress-line" role="progressbar" aria-label="Tour progress" aria-valuemin={1} aria-valuemax={steps.length} aria-valuenow={idx + 1}
          aria-valuetext={progressText(idx, steps.length)} style={{ ["--p" as string]: `${Math.round(share * 100)}%` }}
        ><i /></div>
        <p className="t-label">{progressText(idx, steps.length)}</p>
        <h2 id="tour-title" className="tour__title">{s.title}</h2>
        <p id="tour-text" className="tour__text">{s.text}</p>
        <div className="tour__actions">
          <button type="button" className="btn btn--quiet btn--sm" onClick={endTour}>Skip tour</button>
          <span className="tour__push" />
          <button type="button" className="btn btn--secondary btn--sm" onClick={back} disabled={idx === 0}>Back</button>
          <button ref={primary} type="button" className="btn btn--primary btn--sm" onClick={next}>{last ? "Done" : "Next"}</button>
        </div>
        <p className="u-sr-only" role="status" aria-live="polite">{`${progressText(idx, steps.length)}. ${s.title}. ${s.text}`}</p>
      </section>
    </>
  );
}
