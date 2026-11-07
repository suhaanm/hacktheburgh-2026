// The guided tour, pure: the steps for each view and the small rules around them. The copy is fixed (no numbers are typed into it).
// Worker view: six steps. Admin view: those six plus the Firm overview and Roles, eight in all. The last step is always the stop button.
import type { Screen } from "../../router";
import type { ViewRole } from "./viewAs";

export interface TourStep {
  id: string;
  /** The title on the card. */
  title: string;
  /** One sentence. */
  text: string;
  /** The hash route to show, or null to stay where the person is (the stop button is on every screen). */
  route: string | null;
  /** The menu link to ring, by screen id; null when the step points at something else. */
  nav: Screen | null;
  /** The element to ring instead of a menu link (a CSS selector). */
  selector: string | null;
  /** Only in the Admin view. */
  admin: boolean;
}

const STEPS: TourStep[] = [
  { id: "home", title: "Your week", text: "Start here: a few pointers for your week, and nothing at all when nothing stands out.", route: "/home", nav: "home", selector: null, admin: false },
  { id: "repeats", title: "Repeats", text: "Repeats lists what you do again and again, so you can choose what to hand over.", route: "/repeats", nav: "repeats", selector: null, admin: false },
  { id: "growth", title: "Growth", text: "Growth shows how much less help you need over time, not how expert you are.", route: "/growth", nav: "growth", selector: null, admin: false },
  { id: "genome", title: "Details: Genome", text: "Under Details, Genome shows where your time goes compared with an expert's.", route: "/genome", nav: "genome", selector: null, admin: false },
  { id: "privacy", title: "Privacy", text: "Privacy lists what was sent to a model and what was blocked.", route: "/privacy", nav: "privacy", selector: null, admin: false },
  { id: "firm", title: "Firm overview", text: "The Firm screen gives the few things worth knowing across the firm, with the numbers behind each.", route: "/firm", nav: "firm", selector: null, admin: true },
  { id: "roles", title: "Firm roles", text: "Roles puts experts and juniors side by side, and says so plainly when it cannot tell yet.", route: "/firm/roles", nav: "firm", selector: null, admin: true },
  { id: "stop", title: "Stop everything", text: "This button is on every screen, and one press stops every agent and routine.", route: null, nav: null, selector: ".kill", admin: false },
];

/** The steps for a view, in order. The stop step comes last in both. */
export function tourSteps(view: ViewRole): TourStep[] {
  return STEPS.filter((s) => !s.admin || view === "admin");
}

export const stepCount = (view: ViewRole): number => tourSteps(view).length;

/** Keep a step number inside the list. */
export function clampStep(i: number, n: number): number {
  if (n <= 0) return 0;
  return Math.min(n - 1, Math.max(0, Math.floor(Number.isFinite(i) ? i : 0)));
}

/** The CSS selector of the element a step rings: the menu link for its screen, or the step's own selector. Null when there is nothing to ring. */
export function anchorSelector(step: TourStep): string | null {
  if (step.selector) return step.selector;
  return step.nav ? `nav#nav a[href="#/${step.nav}"]` : null;
}

/** "Step 3 of 6". */
export const progressText = (step: number, n: number): string => `Step ${step + 1} of ${n}`;

/** The step's number as a share of the whole, for the thin progress line (the last step is 100%). */
export const progressShare = (step: number, n: number): number => (n <= 0 ? 0 : (clampStep(step, n) + 1) / n);

export const wordCount = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;

/**
 * After the view changes mid-tour: the same step in the new list if it is still there, else null (the tour ends).
 * Going from Admin to Worker on the Firm steps ends it; going to Admin keeps the step by its id, so the position stays right.
 */
export function stepAfterViewChange(oldView: ViewRole, step: number, newView: ViewRole): number | null {
  const cur = tourSteps(oldView)[step];
  if (!cur) return null;
  const idx = tourSteps(newView).findIndex((s) => s.id === cur.id);
  return idx < 0 ? null : idx;
}

/** Is a rectangle on screen and big enough to ring? A hidden menu (display: none) has no rectangles; an off-canvas one is outside the viewport. */
export function ringable(rect: { left: number; top: number; right: number; bottom: number; width: number; height: number } | null, viewport: { width: number; height: number }): boolean {
  if (!rect || rect.width <= 0 || rect.height <= 0) return false;
  return rect.right > 0 && rect.bottom > 0 && rect.left < viewport.width && rect.top < viewport.height;
}

export type Rect = { left: number; top: number; width: number; height: number };
/** The ring: the element's rectangle grown by a few pixels, kept inside the viewport. */
export function ringBox(rect: Rect, pad: number, viewport: { width: number; height: number }): Rect {
  const left = Math.max(0, rect.left - pad);
  const top = Math.max(0, rect.top - pad);
  const right = Math.min(viewport.width, rect.left + rect.width + pad);
  const bottom = Math.min(viewport.height, rect.top + rect.height + pad);
  return { left, top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}
