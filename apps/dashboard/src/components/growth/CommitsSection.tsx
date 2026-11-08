import { useState } from "react";
import { api } from "../../api";
import { idle, useLoad } from "../../hooks";
import { ChartFoot, EmptyState, LegendItem, Loading, SourceNote } from "../common";
import { HabitDeltas } from "../HabitDeltas";
import { Hint } from "../Hint";
import { Details, fitItems } from "../ui";
import { GrowthSection, SectionError, useReportSource } from "./GrowthSection";
import { notKnown, useOwnPerson } from "./own";
import { splitSentence } from "../../lib/week";
import { DIGEST_LABEL, fmtPoints, fmtPointsInterval, fmtShare, readHabit, sortHabits, splitCounts } from "../../lib/git";
import { oneExpert, safeWhy } from "../../lib/voice";
import { ownMeta } from "../../lib/ownMeta";
import type { GitHabit, GitHabits } from "../../types";
import type { Loaded } from "../../api";

/** The headline sentence: how many of the worker's commit habits differ clearly from an experienced worker's. */
export function commitsHeadline(habits: GitHabit[]): string {
  if (habits.length === 0) return "Your commit habits appear here once a repository is registered.";
  const n = habits.filter((h) => h.flagged).length;
  if (n === 0) return "No commit habit of yours stands out from an experienced worker's.";
  return n === 1 ? "One of your commit habits differs clearly from an experienced worker's." : `${n} of your commit habits differ clearly from an experienced worker's.`;
}

/**
 * My commits (programmers): the worker's own commit habits against ONE experienced worker's. It reads counts and shares only: no message, file name or author.
 * Nobody else's repository is listed and no count of other people is drawn.
 */
export function CommitsSection({ open }: { open: boolean }) {
  const own = useOwnPerson();
  const me = own.person;
  const h = useLoad(() => (own.ready ? (own.blocked ? notKnown<Loaded<GitHabits>>() : api.gitHabits(me, undefined)) : idle<GitHabits>()), [own.ready, own.blocked, me]);
  const [allHabits, setAllHabits] = useState(false);
  useReportSource("commits", h.why ?? null);

  if (h.status === "error" && !h.data) return <GrowthSection id="commits" title="My commits" headline="Your commit habits could not be read just now."><SectionError error={h.error} retry={h.reload} what="your commit habits" empty="No repository is registered for you yet." /></GrowthSection>;
  if (!h.data) return <GrowthSection id="commits" title="My commits" headline="Reading your commit habits." busy><Loading label="Loading your commit habits" /></GrowthSection>;
  const d = h.data;
  const habits = sortHabits(d.habits);
  const flagged = habits.filter((x) => x.flagged);
  const shownHabits = allHabits ? habits : habits.slice(0, 5);
  const meta = ownMeta(h.meta, { n: d.n_commits, unit: "commit" });

  return (
    <GrowthSection id="commits" title="My commits" headline={commitsHeadline(habits)} open={open}>
      {habits.length === 0 ? (
        <EmptyState title="No commits to read yet" body="When you register a repository, its commit habits appear here. Nothing is read until you register one." />
      ) : (
        <div className="stack">
          <div className="chart stack" style={{ gap: "var(--space-4)" }}>
            <HabitDeltas habits={shownHabits} />
            {habits.length > 5 && <div><button type="button" className="btn btn--quiet btn--sm" aria-expanded={allHabits} onClick={() => setAllHabits((v) => !v)}>{allHabits ? "Show fewer" : `Show all ${habits.length}`}</button></div>}
          </div>
          <Details summary="Key" wide>
            <p className="note">Each row is a share of your commits, against an experienced worker&apos;s. Flagged means past its floor and clear of zero.</p>
            <ul className="legend" aria-label="How to read the chart">
              <LegendItem swatch={<span className="sw gh-sw gh-sw--bad" />}>Flagged, and worse than the experienced worker</LegendItem>
              <LegendItem swatch={<span className="sw gh-sw" />}>Not flagged</LegendItem>
              <LegendItem swatch={<span className="sw sw--hatch sw--muted" />}>Floor: a smaller difference is never flagged</LegendItem>
              <LegendItem swatch={<span className="sw" style={{ height: 2, alignSelf: "center", background: "var(--fg)" }} />}>95% interval</LegendItem>
            </ul>
          </Details>
          <Habits d={d} flagged={flagged} />
          <Details summary="Method" wide>
            <div className="stack">
              <p className="note"><b className="tabular">{d.n_commits.toLocaleString("en-GB")}</b> commits were counted. {DIGEST_LABEL[d.digest_source] ?? d.digest_source}. {d.digest_source === "rules" ? "No model was involved." : "It ran on this laptop and saw digests, not commit text."}{d.digest_warming ? " The model is still warming up, so rules answered for now." : ""}</p>
              <Details summary="The habits as a table" wide><HabitTable habits={habits} /></Details>
              <ChartFoot variant="about" meta={meta} badge={false} />
            </div>
          </Details>
        </div>
      )}
      {h.why && <SourceNote why={safeWhy(h.why)} />}
    </GrowthSection>
  );
}

function Habits({ d, flagged }: { d: GitHabits; flagged: GitHabit[] }) {
  const list = d.suggestions ?? flagged.map((f) => f.suggestion).filter((s): s is NonNullable<typeof s> => !!s);
  if (list.length === 0) return null;
  const k = fitItems(list.map((s) => oneExpert(s.text)), 44).shown.length;
  const row = (s: (typeof list)[number]) => {
    const [fact, advice] = splitSentence(oneExpert(s.text));
    const { text, counts } = splitCounts(fact);
    return (
      <li key={s.id} className="sug-row" aria-label={oneExpert(s.text)}>
        <span className="sug__text">{text}{counts && <> <Hint label="The counts behind this">{counts}</Hint></>}</span>
        {advice && <span className="u-muted"> {advice}</span>}
      </li>
    );
  };
  return (
    <Details summary={`Habits worth a look (${list.length})`} wide>
      <div className="stack">
        <ul className="plain-list sug-rows" aria-label="Habits, none acted on">{list.slice(0, k).map(row)}</ul>
        {list.length > k && <Details summary={`More (${list.length - k})`}><ul className="plain-list sug-rows">{list.slice(k).map(row)}</ul></Details>}
        <p className="note">{list.some((s) => s.can_draft) ? "Drafts can be prepared. " : ""}Nothing is committed or pushed.</p>
      </div>
    </Details>
  );
}

function HabitTable({ habits }: { habits: GitHabit[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Habit</th><th className="num">You</th><th className="num">Experienced worker</th><th className="num">Difference</th><th>95% interval</th><th>Read</th></tr></thead>
        <tbody>
          {habits.map((x) => {
            const r = readHabit(x);
            return (
              <tr key={x.id}>
                <td>{x.label}{x.n_num != null && x.n_den != null ? <span className="u-muted"> ({x.n_num} of {x.n_den})</span> : null}</td>
                <td className="num">{fmtShare(x.learner)}</td>
                <td className="num">{fmtShare(x.expert)}</td>
                <td className="num"><b>{fmtPoints(x.delta)}</b></td>
                <td className="num interval">{fmtPointsInterval(x.ci)}</td>
                <td>{r.flagged ? <b>{oneExpert(r.state)}</b> : <span className="u-muted">{oneExpert(r.state)}</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
