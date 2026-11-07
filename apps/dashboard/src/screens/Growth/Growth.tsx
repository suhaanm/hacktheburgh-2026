import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRoute } from "../../router";
import { useLoad, prefersReducedMotion } from "../../hooks";
import { ErrorState, ExampleBadge, Loading, OriginBadge, PageHead, SourceNote } from "../../components/common";
import { GrowthChart } from "../../components/growth/GrowthChart";
import { Summary } from "../../components/growth/Summary";
import { Cards } from "../../components/growth/Cards";
import { SkillRows } from "../../components/growth/SkillRows";
import { Offloaded } from "../../components/growth/Offloaded";
import { LedgerControls } from "../../components/growth/LedgerControls";
import { About } from "../../components/growth/About";
import { AboutData, Details } from "../../components/ui";
import { Hint } from "../../components/Hint";
import { EarlyHero, EmptyHero } from "../../components/growth/States";
import { buildView, countsOf, ledgerFields, marksOf, normalizeGrowth, offloadItems, originSentence, type LedgerCounts } from "../../components/growth/model";
import "../../components/growth/growth.css";
import { STORIES, deleteLedger, downloadText, exportLedger, loadGrowth, loadLedger, type Story } from "./data";

const STORY_ALIAS: Record<string, Story> = { improves: "improves", improve: "improves", plateau: "plateaus", plateaus: "plateaus", going: "going", early: "going", sparse: "sparse", new: "sparse" };

/** Growth ("Curtain"): how much less help the worker needs over time. One hero: the independence curve, with The Fade beneath it. */
export default function Growth() {
  const route = useRoute();
  const [story, setStory] = useState<Story>(() => STORY_ALIAS[route.query.get("story") ?? ""] ?? "improves");
  const [skill, setSkill] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const heroRef = useRef<HTMLElement>(null);

  const g = useLoad(() => loadGrowth(skill, story), [skill, story, tick]);
  const needsMarks = g.data ? normalizeGrowth(g.data).readiness.occurrences < normalizeGrowth(g.data).readiness.needed : false;
  const led = useLoad(() => loadLedger(story, needsMarks), [story, needsMarks, tick]);

  // A story is only a thing to pick when the screen shows example data.
  const example = g.source === "demo";
  useEffect(() => { document.title = "Growth · Understudy"; }, []);

  const levelPct = Math.round((g.meta?.interval_level ?? 0.95) * 100);
  const wire = useMemo(() => (g.data ? normalizeGrowth(g.data) : null), [g.data]);
  const view = useMemo(() => (wire ? buildView(wire, levelPct) : null), [wire, levelPct]);

  const focusSkill = useCallback((id: string | null) => {
    setSkill(id);
    const el = heroRef.current;
    if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, []);

  if (g.status === "error" && !g.data) return <div className="page"><ErrorState error={g.error} retry={g.reload} what="your growth curve" /></div>;
  if (!wire || !view) return <div className="page"><Loading label="Loading your growth curve" /></div>;

  const rows = led.data?.rows ?? [];
  const counts: LedgerCounts = countsOf(wire, led.data?.counts ?? null);
  const labelOf = (id: string) => view.skills.find((s) => s.id === id)?.label ?? id;
  const focusLabel = view.skills.find((s) => s.id === view.focusId)?.label ?? null;
  const n = g.meta?.n ?? view.total;
  const busy = g.status === "loading";

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

  return (
    <div className="page page--wide" aria-busy={busy}>
      <PageHead
        eyebrow={focusLabel ? `Growth · ${focusLabel}` : "Growth"}
        title={view.title}
        lede="This shows how much less help you need, not how expert you are."
        aside={<>
          <OriginBadge meta={g.meta} always />
          <ExampleBadge why={g.why} />
          {example && (
            <span className="gr-story" role="group" aria-label="Which example learner to show">
              <span>Example learner</span>
              <span className="segmented">
                {STORIES.map((s) => (
                  <button key={s.id} type="button" aria-pressed={story === s.id} onClick={() => { setStory(s.id); setSkill(null); }}>{s.label}</button>
                ))}
              </span>
            </span>
          )}
        </>}
      />

      <section ref={heroRef} className={`hero${busy ? " gr-busy" : ""}`} aria-labelledby="hero-h" style={{ scrollMarginTop: "var(--space-5)" }}>
        <h2 id="hero-h" className="u-sr-only">Independence curve</h2>
        {view.status === "empty" && <EmptyHero needed={view.needed} window={view.window} />}
        {view.status === "early" && (
          <EarlyHero total={view.total} needed={view.needed} marks={marksOf(rows, wire.skill)} unaided={wire.occurrences.unaided} baseline={wire.baseline} />
        )}
        {view.status === "ready" && (
          <>
            <div className="gr-bar">
              <div className="gr-bar__text">
                <h3 className="chart__title">{view.focusName ? `Finished with no cue accepted: ${focusLabel}` : "Finished with no cue accepted, all skills"}</h3>
                {view.lede && <p className="chart__sub">{view.lede}</p>}
              </div>
              {view.focusName && <button type="button" className="btn btn--secondary btn--sm" onClick={() => focusSkill(null)}>Show all skills</button>}
            </div>
            {view.recentLine && <Details summary="Read the latest point in words">{view.recentLine}</Details>}
            <figure className="chart chart--wide">
              <GrowthChart view={view} />
              <figcaption className="chart__foot chart__foot--about">
                <OriginBadge meta={g.meta} always />
                <AboutData rows={[
                  ["n", `${n.toLocaleString("en-GB")} ${n === 1 ? "occurrence" : "occurrences"}`],
                  ...(g.meta?.split ? ([["window", g.meta.split]] as [string, string][]) : []),
                  ["intervals", `${levelPct}%`],
                  ["origin", `${originSentence(view.originDetail, g.meta?.origin)}${g.meta?.note ? ` ${g.meta.note}` : ""}`],
                ]} />
              </figcaption>
            </figure>
            <Summary view={view} n={n} />
          </>
        )}
        <SourceNote why={g.why} />
      </section>

      {view.status === "ready" && (
        <section className="section" aria-labelledby="comp-h">
          <div className="section__head">
            <h2 id="comp-h" className="section__title">What has changed</h2>
            <p className="section__sub">Three plain measures. Read these before any single number.</p>
          </div>
          <Cards cards={view.cards} levelPct={levelPct} />
        </section>
      )}

      {view.skills.length > 0 && (
        <section className="section" aria-labelledby="skills-h">
          <div className="section__head">
            <h2 id="skills-h" className="section__title">By skill<Hint label="About this list">Press a row to show that skill on the curve.</Hint></h2>
            <p className="section__sub">{view.claim}</p>
          </div>
          <SkillRows rows={view.skills} focusId={view.focusId} onFocus={focusSkill} levelPct={levelPct} needed={view.needed} />
        </section>
      )}

      <Offloaded delegated={counts.delegated} automation={counts.automation} minutes={view.offloadedMinutes} items={offloadItems(rows, labelOf)} />

      <hr className="rule" />
      <div className="cols-2">
        <LedgerControls counts={counts} fields={ledgerFields(rows)} example={example} onExport={onExport} onDelete={onDelete} />
        <About view={view} meta={g.meta} />
      </div>

    </div>
  );
}
