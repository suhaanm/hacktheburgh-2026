import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";
import { Loading } from "../components/common";
import { GROWTH_SECTIONS, GROWTH_SECTION_LABEL, growthPath, growthSectionOf, type GrowthSection } from "../components/home/navModel";
import { navigate, useRoute } from "../router";

/**
 * Growth is one page with five sections (docs/knack-ux/views.md): My progress, Where my time goes, My steps, How my routines connect, My commits.
 * `?section=progress|time|steps|map|commits` picks one. Track D draws the page; until its Growth module says it draws the sections itself (it exports
 * `handlesSections = true`), this host draws D's page for My progress and the screen that used to hold each other section, under one switch, so a worker
 * never loses a view while the page is being rebuilt. Nothing here reads a number: each screen loads its own data.
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
      <Suspense fallback={<Loading label={`Loading ${GROWTH_SECTION_LABEL[section].toLowerCase()}`} />}>
        {Parts.map((P, i) => <P key={i} />)}
      </Suspense>
    </div>
  );
}
