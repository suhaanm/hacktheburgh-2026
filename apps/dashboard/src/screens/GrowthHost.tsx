import { lazy, Suspense, useEffect, useRef, useState, type ComponentType, type ReactNode } from "react";
import { Loading } from "../components/common";
import { GROWTH_SECTIONS, GROWTH_SECTION_LABEL, growthPath, growthSectionOf, type GrowthSection } from "../components/home/navModel";
import { useViewRole } from "../components/home/viewAs";
import { cohortHits } from "../lib/cohortRules";
import { navigate, useRoute } from "../router";
import { useAppState } from "../store";

/**
 * Growth is one page with five sections (docs/knack-ux/views.md): My progress, Where my time goes, My steps, How my routines connect, My commits.
 * `?section=progress|time|steps|map|commits` picks one. Track D draws the page; until its Growth module says it draws the sections itself (it exports
 * `handlesSections = true`), this host draws D's page for My progress and the screen that used to hold each other section, under one switch, so a worker
 * never loses a view while the page is being rebuilt. Nothing here reads a number: each screen loads its own data.
 *
 * One guard stands over the older screens: a worker sees their own work and one experienced worker's way, never other people. If a section being bridged
 * draws a string that breaks that rule (an average over all novices, a count of people, another person's id), the section is not drawn at all and says it
 * is being rebuilt. The Admin view is not guarded: an admin may see the firm.
 */
type GrowthModule = { default: ComponentType; handlesSections?: boolean };
const loadGrowth = (): Promise<GrowthModule> => import("./Growth") as Promise<GrowthModule>;

const Progress = lazy(loadGrowth);
const Week = lazy(() => import("./Week"));
const Presence = lazy(() => import("./Presence"));
const Genome = lazy(() => import("./Genome"));
const Graph = lazy(() => import("./Graph"));
const Git = lazy(() => import("./Git"));

const LEGACY: Record<Exclude<GrowthSection, "progress">, ComponentType[]> = {
  time: [Week, Presence],
  steps: [Genome],
  map: [Graph],
  commits: [Git],
};

export const REBUILT_TITLE = "This section is being rebuilt";
export const REBUILT_BODY = "It will show only your own work.";

/** Draws its children, and takes them away the moment what they drew breaks the cohort rule (worker view only). Re-checks as the screen loads and changes. */
function CohortGuard({ children }: { children: ReactNode }) {
  const view = useViewRole();
  const person = useAppState().person;
  const box = useRef<HTMLDivElement>(null);
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (view !== "worker" || !el) return;
    // A screen that keeps changing (a clock, an animation) must not starve the check, so this is a throttle, not a debounce: at most one scan per 150 ms, and
    // always one after the last change.
    let timer: number | undefined;
    // Once a section has broken the rule it stays hidden until the address names another section (the guard is keyed by section): it never flickers back.
    const scan = () => { timer = undefined; if (cohortHits(el.textContent, person).length > 0) setBlocked(true); };
    const later = () => { if (timer === undefined) timer = window.setTimeout(scan, 150); };
    const watch = new MutationObserver(later);
    watch.observe(el, { childList: true, subtree: true, characterData: true });
    scan();
    return () => { watch.disconnect(); window.clearTimeout(timer); };
  }, [view, person]);
  if (blocked) {
    return (
      <section className="state" role="status" data-testid="growth-rebuilt">
        <h2 className="state__title">{REBUILT_TITLE}</h2>
        <p className="state__body">{REBUILT_BODY}</p>
        <a className="btn btn--secondary state__action" href={`#${growthPath("progress")}`}>My progress</a>
      </section>
    );
  }
  return <div ref={box}>{children}</div>;
}

export default function GrowthHost() {
  const route = useRoute();
  const section = growthSectionOf(route.query.get("section"));
  const [own, setOwn] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    loadGrowth().then((m) => { if (live) setOwn(m.handlesSections === true); }, () => { if (live) setOwn(false); });
    return () => { live = false; };
  }, []);

  // Track D's page draws the section itself, or the section is My progress: nothing to add.
  if (own === true || section === "progress") {
    return <Suspense fallback={<Loading label="Loading your progress" />}><Progress /></Suspense>;
  }
  if (own === null) return <Loading label="Loading" />;
  const Parts = LEGACY[section];
  return (
    <div className="growth-host" data-section={section}>
      <nav className="growth-host__switch" aria-label="Growth sections">
        <span className="segmented">
          {GROWTH_SECTIONS.map((s) => (
            <button key={s} type="button" aria-pressed={s === section} onClick={() => navigate(growthPath(s))}>{GROWTH_SECTION_LABEL[s]}</button>
          ))}
        </span>
      </nav>
      <CohortGuard key={section}>
        <Suspense fallback={<Loading label={`Loading ${GROWTH_SECTION_LABEL[section].toLowerCase()}`} />}>
          {Parts.map((P, i) => <P key={i} />)}
        </Suspense>
      </CohortGuard>
    </div>
  );
}
