import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRoute } from "../../router";
import { useAppState } from "../../store";
import { growthSectionOf } from "../../components/home/navModel";
import { useLoad, prefersReducedMotion } from "../../hooks";
import { ErrorState, ExampleBadge, Loading, OriginBadge, PageHead, SourceNote, workerOriginLabel } from "../../components/common";
import { GrowthChart, GrowthKey } from "../../components/growth/GrowthChart";
import { SkillRows } from "../../components/growth/SkillRows";
import { Offloaded } from "../../components/growth/Offloaded";
import { LedgerControls } from "../../components/growth/LedgerControls";
import { AboutGrowth } from "../../components/growth/About";
import { Details } from "../../components/ui";
import { EarlyHero, EmptyHero, HowStepsAreCounted } from "../../components/growth/States";
import { SectionSources, useExampleSource } from "../../components/growth/GrowthSection";
import { TimeSection } from "../../components/growth/TimeSection";
import { StepsSection } from "../../components/growth/StepsSection";
import { MapSection } from "../../components/growth/MapSection";
import { CommitsSection } from "../../components/growth/CommitsSection";
import { buildView, countsOf, ledgerFields, marksOf, normalizeGrowth, offloadItems, totalRows, type LedgerCounts } from "../../components/growth/model";
import "../../components/growth/growth.css";
import { STORIES, deleteLedger, downloadText, exportLedger, loadGrowth, loadLedger, type Story } from "./data";

const STORY_ALIAS: Record<string, Story> = { improves: "improves", improve: "improves", plateau: "plateaus", plateaus: "plateaus", going: "going", early: "going", sparse: "sparse", new: "sparse" };

/** The one limit this screen prints. It is a limit, so it is never behind a Hint (D45). */
export const GROWTH_LIMIT = "Measures help needed, not expertise.";

/**
 * My progress: whether the worker needs less help over time (KNACK_UX, 04-growth.md). A sentence for a title, the one printed limit, one chart,
 * the skills as rows, and closed disclosures (About this data, The fade, Your record, What Knack did for you). At most 60 words above the fold.
 * The page that holds it is `Growth` below: the other sections of "growth" follow it on the same page.
 */
function Progress() {
  const route = useRoute();
  const [story, setStory] = useState<Story>(() => STORY_ALIAS[route.query.get("story") ?? ""] ?? "improves");
  const [skill, setSkill] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const heroRef = useRef<HTMLElement>(null);
  const anyExample = useExampleSource();

  const g = useLoad(() => loadGrowth(skill, story), [skill, story, tick]);
  const needsMarks = g.data ? normalizeGrowth(g.data).readiness.occurrences < normalizeGrowth(g.data).readiness.needed : false;
  const led = useLoad(() => loadLedger(story, needsMarks), [story, needsMarks, tick]);

  // A story is only a thing to pick when the screen shows example data.
  const example = g.source === "demo";
  useEffect(() => { document.title = "Growth · Knack"; }, []);

  const levelPct = Math.round((g.meta?.interval_level ?? 0.95) * 100);
  const wire = useMemo(() => (g.data ? normalizeGrowth(g.data) : null), [g.data]);
  const view = useMemo(() => (wire ? buildView(wire, levelPct) : null), [wire, levelPct]);

  const focusSkill = useCallback((id: string | null) => {
    setSkill(id);
    const el = heroRef.current;
    if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, []);

  if (g.status === "error" && !g.data) return <div className="gr-progress"><ErrorState error={g.error} retry={g.reload} what="your growth curve" /></div>;
  if (!wire || !view) return <div className="gr-progress"><Loading label="Loading your growth curve" /></div>;

  const rows = led.data?.rows ?? [];
  const counts: LedgerCounts = countsOf(wire, led.data?.counts ?? null);
  const labelOf = (id: string) => view.skills.find((s) => s.id === id)?.label ?? id;
  const focusLabel = view.skills.find((s) => s.id === view.focusId)?.name ?? null;
  const n = g.meta?.n ?? view.total;
  const busy = g.status === "loading";
  // Nothing to export or forget, and nothing run for the worker: the two disclosures would only say so, so they wait until there is something in them.
  const hasLedger = totalRows(counts) > 0;
  const hasOffloaded = counts.delegated + counts.automation > 0;

  const onExport = async () => {
    const f = await exportLedger(story, example);
    downloadText(f.filename, f.text);
  };
  const onDelete = async () => {
    const count = await deleteLedger(story, example);
    setSkill(null);
    setTick((t) => t + 1);
    return count;
  };

  // One origin badge per screen: the sample badge when the screen shows built-in example data, else the engine's origin in a worker's words.
  // A live answer with nothing counted shows no numbers, so there is nothing to qualify: no badge. The origin is still printed in "About this data".
  const liveAndEmpty = !g.why && g.source === "live" && view.status === "empty";
  const badge = g.why ? <ExampleBadge why={g.why} /> : anyExample ? <ExampleBadge why={anyExample} /> : liveAndEmpty ? null : <OriginBadge meta={g.meta} label={g.meta ? workerOriginLabel(g.meta.origin) : undefined} />;

  return (
    <div className="gr-progress" aria-busy={busy}>
      <PageHead hero title={view.title} lede={GROWTH_LIMIT} aside={badge} />

      <section ref={heroRef} className={`gr-hero${busy ? " gr-busy" : ""}`} aria-label="Independence curve" style={{ scrollMarginTop: "var(--space-5)" }}>
        {view.status === "empty" && <EmptyHero needed={view.needed} />}
        {view.status === "early" && (
          <EarlyHero total={view.total} needed={view.needed} marks={marksOf(rows, wire.skill)} unaided={wire.occurrences.unaided} baseline={wire.baseline} />
        )}
        {view.status === "ready" && (
          <>
            {view.focusName && (
              <div className="gr-focus">
                <span>Showing {focusLabel}</span>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => focusSkill(null)}>Show all skills</button>
              </div>
            )}
            <figure className="chart chart--wide gr-figure">
              <GrowthChart view={view} />
            </figure>
          </>
        )}
        {g.why?.kind === "error" && <SourceNote why={g.why} />}
        <AboutGrowth view={view} meta={g.meta} n={n}>
          {g.why && g.why.kind !== "error" && <SourceNote why={g.why} />}
          {view.status !== "ready" && <HowStepsAreCounted needed={view.needed} window={view.window} />}
          {example && (
            <div className="gr-story" role="group" aria-label="Which example learner to show">
              <span>Example learner</span>
              <span className="segmented">
                {STORIES.map((s) => (
                  <button key={s.id} type="button" aria-pressed={story === s.id} onClick={() => { setStory(s.id); setSkill(null); }}>{s.label}</button>
                ))}
              </span>
            </div>
          )}
        </AboutGrowth>
      </section>

      {view.skills.length > 0 && (
        <section className="gr-skills-section" aria-labelledby="skills-h">
          <h2 id="skills-h" className="u-sr-only">Skills</h2>
          <SkillRows rows={view.skills} focusId={view.focusId} onFocus={focusSkill} levelPct={view.levelPct} needed={view.needed} />
        </section>
      )}

      <div className="gr-more">
        {view.status === "ready" && (
          <Details summary="The fade" wide>
            <GrowthChart view={view} part="fade" />
            <Details summary="Key"><GrowthKey view={view} part="fade" /></Details>
          </Details>
        )}
        {hasLedger && (
          <Details summary="Your record" wide>
            <LedgerControls counts={counts} fields={ledgerFields(rows)} example={example} onExport={onExport} onDelete={onDelete} />
          </Details>
        )}
        {hasOffloaded && (
          <Details summary="What Knack did for you" wide>
            <Offloaded delegated={counts.delegated} automation={counts.automation} minutes={view.offloadedMinutes} items={offloadItems(rows, labelOf)} />
          </Details>
        )}
      </div>
    </div>
  );
}

/** The roles that get "My commits". For every other role the section is not drawn at all, whatever the address says. */
const COMMIT_ROLES = new Set(["programmer"]);

/**
 * Growth is the one worker page for personal insight (docs/knack-ux/views.md): My progress, then Where my time goes, My steps against an
 * experienced worker's, How my routines connect and, for programmers, My commits, one under the other with no extra navigation.
 * Each section is a title, one headline sentence and its numbers behind a disclosure. `?section=` scrolls to a section and opens it.
 */
export default function Growth() {
  const route = useRoute();
  const section = growthSectionOf(route.query.get("section"));
  const role = useAppState().role;
  const commits = role != null && COMMIT_ROLES.has(role);

  useEffect(() => {
    if (section === "progress") return;
    const go = () => document.getElementById(`gr-${section}`)?.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    const a = window.setTimeout(go, 60);
    const b = window.setTimeout(go, 700);
    return () => { window.clearTimeout(a); window.clearTimeout(b); };
  }, [section]);

  return (
    <SectionSources>
      <div className="page page--wide gr-page">
        <Progress />
        <TimeSection open={section === "time"} />
        <StepsSection open={section === "steps"} />
        <MapSection open={section === "map"} />
        {commits && <CommitsSection open={section === "commits"} />}
      </div>
    </SectionSources>
  );
}
