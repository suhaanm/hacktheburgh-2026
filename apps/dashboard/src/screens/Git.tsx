import { useEffect, useState } from "react";
import { api } from "../api";
import { idle, useLoad } from "../hooks";
import { ChartFoot, EmptyState, ErrorState, ExampleBadge, LegendItem, Loading, OriginBadge, PageHead, SourceNote, workerOriginLabel } from "../components/common";
import { HabitDeltas } from "../components/HabitDeltas";
import { Hint } from "../components/Hint";
import { Details, fitItems } from "../components/ui";
import { splitSentence } from "../lib/week";
import { readRememberedFree, writeRememberedFree } from "../lib/remember";
import { DIGEST_LABEL, fmtPoints, fmtPointsInterval, fmtShare, gitHeadline, learnerLabel, readHabit, sortHabits, splitCounts } from "../lib/git";
import type { GitHabit, GitHabits } from "../types";

export default function Git() {
  const people = useLoad(() => api.gitPeople(), []);
  const learners = people.data?.learners ?? [];
  const [person, setPerson] = useState<string | null>(null);
  useEffect(() => {
    if (person || !people.data) return;
    const last = readRememberedFree("git-learner");
    const known = new Set(people.data.learners.map((l) => l.person));
    setPerson(people.data.default_person ?? (last && known.has(last) ? last : null) ?? people.data.learners[0]?.person ?? null);
  }, [people.data, person]);
  const repo = learners.find((l) => l.person === person)?.repo;
  const [allHabits, setAllHabits] = useState(false);
  const h = useLoad(() => (person ? api.gitHabits(person, repo) : idle<GitHabits>()), [person, repo]);

  if (people.status === "error" && !people.data) return <div className="page"><ErrorState error={people.error} retry={people.reload} what="who has a repository" /></div>;
  if (!people.data || !person) return <div className="page"><Loading label="Loading git habits" /></div>;
  if (h.status === "error" && !h.data) return <div className="page"><ErrorState error={h.error} retry={h.reload} what="git habits" /></div>;
  if (!h.data) return <div className="page"><Loading label="Counting commit habits" /></div>;
  const d = h.data;
  const habits = sortHabits(d.habits);
  const flagged = habits.filter((x) => x.flagged);
  const shownHabits = allHabits ? habits : habits.slice(0, 5);

  return (
    <div className="page page--wide">
      <PageHead
        hero
        title={gitHeadline(d.habits)}
        lede="This data holds no message, file name or author."
        aside={h.why ? <ExampleBadge why={h.why} /> : <OriginBadge meta={h.meta} label={h.meta ? workerOriginLabel(h.meta.origin) : undefined} />}
      />

      <div className="row">
        <div className="field" style={{ minWidth: 220 }}>
          <label className="field__label" htmlFor="git-person">Learner</label>
          <select id="git-person" className="select" value={person} onChange={(e) => { setPerson(e.target.value); writeRememberedFree("git-learner", e.target.value); }}>
            {learners.map((l) => <option key={l.person} value={l.person}>{learnerLabel(l.person)}</option>)}
          </select>
        </div>
      </div>

      <section className="hero" aria-labelledby="gh-h">
        <h2 className="u-sr-only" id="gh-h">Where the habits differ</h2>
        {habits.length === 0 ? (
          <EmptyState title="No commits to read yet" body="When a repository is registered, its commit habits appear here. Nothing is read until you register one." />
        ) : (
          <div className="chart stack" style={{ gap: "var(--space-4)" }}>
            <HabitDeltas habits={shownHabits} />
            {habits.length > 5 && <div><button type="button" className="btn btn--quiet btn--sm" aria-expanded={allHabits} onClick={() => setAllHabits((v) => !v)}>{allHabits ? "Show fewer" : `Show all ${habits.length}`}</button></div>}
            <Details summary="Key">
              <p className="note">Each row is a share of {learnerLabel(d.person)}&apos;s commits, against {d.reference?.n_experts ?? "the"} experts&apos;. Flagged means past its floor and clear of zero.</p>
              <ul className="legend" aria-label="How to read the chart">
                <LegendItem swatch={<span className="sw gh-sw gh-sw--bad" />}>Flagged, and worse than the experts</LegendItem>
                <LegendItem swatch={<span className="sw gh-sw" />}>Not flagged</LegendItem>
                <LegendItem swatch={<span className="sw sw--hatch sw--muted" />}>Floor: a smaller difference is never flagged</LegendItem>
                <LegendItem swatch={<span className="sw" style={{ height: 2, alignSelf: "center", background: "var(--fg)" }} />}>95% interval</LegendItem>
              </ul>
            </Details>
            <ChartFoot variant="about" meta={h.meta} badge={false} extra={<span>Reference: <b>{d.reference?.n_experts ?? "?"} experts</b>.{d.reference?.note ? ` ${d.reference.note}.` : ""}</span>} />
          </div>
        )}
      </section>

      {h.why && <SourceNote why={h.why} />}

      <hr className="rule" />
      <Suggestions d={d} flagged={flagged} />

      <hr className="rule" />
      <section className="section" aria-labelledby="gh-how">
        <h2 className="section__title" id="gh-how">How this was counted</h2>
        <p className="note"><b className="tabular">{d.n_commits.toLocaleString("en-GB")}</b> commits were counted.</p>
        <Details summary="Method" wide>
          <div className="stack">
            <p className="note">{DIGEST_LABEL[d.digest_source] ?? d.digest_source}. {d.digest_source === "rules" ? "No model was involved." : "It ran on this laptop and saw digests, not commit text."}{d.digest_warming ? " The model is still warming up, so rules answered for now." : ""}</p>
            <Details summary="The habits as a table" wide>
              <HabitTable habits={habits} />
            </Details>
          </div>
        </Details>
      </section>
    </div>
  );
}

function Suggestions({ d, flagged }: { d: GitHabits; flagged: GitHabit[] }) {
  const list = d.suggestions ?? flagged.map((f) => f.suggestion).filter((s): s is NonNullable<typeof s> => !!s);
  const k = fitItems(list.map((s) => s.text), 44).shown.length;
  const row = (s: (typeof list)[number]) => {
    const [fact, advice] = splitSentence(s.text);
    const { text, counts } = splitCounts(fact);
    return (
      <li key={s.id} className="sug-row" aria-label={s.text}>
        <span className="sug__text">{text}{counts && <> <Hint label="The counts behind this">{counts}</Hint></>}</span>
        {advice && <span className="u-muted"> {advice}</span>}
      </li>
    );
  };
  return (
    <Details summary={`Habits worth a look (${list.length})`} wide>
      {list.length === 0 ? (
        <EmptyState title="Nothing to suggest" body="No habit is far enough from the experts to be worth a change right now." />
      ) : (
        <div className="stack">
          <ul className="plain-list sug-rows" aria-label="Habits, none acted on">{list.slice(0, k).map(row)}</ul>
          {list.length > k && <Details summary={`More (${list.length - k})`}><ul className="plain-list sug-rows">{list.slice(k).map(row)}</ul></Details>}
          <p className="note">{list.some((s) => s.can_draft) ? "Drafts can be prepared. " : ""}Nothing is committed or pushed.</p>
        </div>
      )}
    </Details>
  );
}

function HabitTable({ habits }: { habits: GitHabit[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Habit</th><th className="num">You</th><th className="num">Experts</th><th className="num">Difference</th><th>95% interval</th><th>Read</th></tr></thead>
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
                <td>{r.flagged ? <b>{r.state}</b> : <span className="u-muted">{r.state}</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
