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
import { EarlyHero, EmptyHero } from "../../components/growth/States";
import { buildView, countsOf, ledgerFields, marksOf, offloadItems, type LedgerCounts } from "../../components/growth/model";
import "../../components/growth/growth.css";
import { STORIES, deleteLedger, downloadText, exportLedger, loadGrowth, loadLedger, type Story } from "./data";

const STORY_ALIAS: Record<string, Story> = { improves: "improves", improve: "improves", plateau: "plateaus", plateaus: "plateaus", sparse: "sparse", new: "sparse" };

/** Growth ("Curtain"): how much less help the worker needs over time. One hero: the independence curve, with The Fade beneath it. */
export default function Growth() {
  const route = useRoute();
  const [story, setStory] = useState<Story>(() => STORY_ALIAS[route.query.get("story") ?? ""] ?? "improves");
  const [skill, setSkill] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const heroRef = useRef<HTMLElement>(null);

  const g = useLoad(() => loadGrowth(skill, story), [skill, story, tick]);
  const needsMarks = g.data ? g.data.readiness.occurrences < g.data.readiness.needed : false;
  const led = useLoad(() => loadLedger(story, needsMarks), [story, needsMarks, tick]);

  // A story is only a thing to pick when the screen shows example data.
  const example = g.source === "demo";
  useEffect(() => { document.title = "Growth · Understudy"; }, []);

  const levelPct = Math.round((g.meta?.interval_level ?? 0.95) * 100);
  const view = useMemo(() => (g.data ? buildView(g.data, levelPct) : null), [g.data, levelPct]);

  const focusSkill = useCallback((id: string | null) => {
    setSkill(id);
    const el = heroRef.current;
    if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, []);

  if (g.status === "error" && !g.data) return <div className="page"><ErrorState error={g.error} retry={g.reload} what="your growth curve" /></div>;
  if (!g.data || !view) return <div className="page"><Loading label="Loading your growth curve" /></div>;

  const rows = led.data?.rows ?? [];
  const counts: LedgerCounts = countsOf(g.data, led.data?.counts ?? null);
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
                  <button key={s.id} type="button" aria-pressed={story === s.id} title={s.hint} onClick={() => { setStory(s.id); setSkill(null); }}>{s.label}</button>
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
          <EarlyHero total={view.total} needed={view.needed} marks={marksOf(rows, g.data.skill)} unaided={g.data.occurrences.unaided} baseline={g.data.baseline} />
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
            {view.recentLine && <p className="t-prose">{view.recentLine}</p>}
            <figure className="chart chart--wide">
              <GrowthChart view={view} />
              <figcaption className="chart__foot">
                <span>n = <b>{n.toLocaleString("en-GB")} {n === 1 ? "occurrence" : "occurrences"}</b></span>
                {g.meta?.split && <span>window: <b>{g.meta.split}</b></span>}
                <span>intervals: <b>{levelPct}%</b></span>
                <OriginBadge meta={g.meta} always />
                {g.meta?.note && <span className="chart__note">{g.meta.note}</span>}
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
            <p className="section__sub">Three things, each with its own interval. They are the parts of the score that matter.</p>
          </div>
          <Cards cards={view.cards} levelPct={levelPct} />
        </section>
      )}

      {view.skills.length > 0 && (
        <section className="section" aria-labelledby="skills-h">
          <div className="section__head">
            <h2 id="skills-h" className="section__title">By skill</h2>
            <p className="section__sub">{view.claim} Press a row to show that skill on the curve.</p>
          </div>
          <SkillRows rows={view.skills} focusId={view.focusId} onFocus={focusSkill} levelPct={levelPct} />
        </section>
      )}

      <Offloaded delegated={view.offloaded.delegated} automation={view.offloaded.automation} items={offloadItems(rows, labelOf)} />

      <hr className="rule" />
      <div className="cols-2">
        <LedgerControls counts={counts} fields={ledgerFields(rows)} example={example} onExport={onExport} onDelete={onDelete} />
        <About view={view} meta={g.meta} />
      </div>

    </div>
  );
}
