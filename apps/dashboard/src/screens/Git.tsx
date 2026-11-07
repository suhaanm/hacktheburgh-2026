import { useEffect, useState } from "react";
import { api } from "../api";
import { idle, useLoad } from "../hooks";
import { ChartFoot, EmptyState, ErrorState, ExampleBadge, LegendItem, Loading, OriginBadge, PageHead, SourceNote } from "../components/common";
import { HabitDeltas } from "../components/HabitDeltas";
import { Hint } from "../components/Hint";
import { Details } from "../components/ui";
import { splitSentence } from "../lib/week";
import { DIGEST_LABEL, fmtPoints, fmtPointsInterval, fmtShare, gitHeadline, learnerLabel, readHabit, sortHabits, splitCounts } from "../lib/git";
import type { GitHabit, GitHabits } from "../types";

export default function Git() {
  const people = useLoad(() => api.gitPeople(), []);
  const learners = people.data?.learners ?? [];
  const [person, setPerson] = useState<string | null>(null);
  useEffect(() => {
    if (person || !people.data) return;
    setPerson(people.data.default_person ?? people.data.learners[0]?.person ?? null);
  }, [people.data, person]);
  const repo = learners.find((l) => l.person === person)?.repo;
  const h = useLoad(() => (person ? api.gitHabits(person, repo) : idle<GitHabits>()), [person, repo]);

  if (people.status === "error" && !people.data) return <div className="page"><ErrorState error={people.error} retry={people.reload} what="who has a repository" /></div>;
  if (!people.data || !person) return <div className="page"><Loading label="Loading git habits" /></div>;
  if (h.status === "error" && !h.data) return <div className="page"><ErrorState error={h.error} retry={h.reload} what="git habits" /></div>;
  if (!h.data) return <div className="page"><Loading label="Counting commit habits" /></div>;
  const d = h.data;
  const habits = sortHabits(d.habits);
  const flagged = habits.filter((x) => x.flagged);

  return (
    <div className="page">
      <PageHead
        eyebrow="Git habits"
        title={gitHeadline(d.habits)}
        lede={`${learnerLabel(d.person)}'s commits against ${d.reference?.n_experts ?? "the"} experts'. No commit message, file name or author is in this data.`}
        aside={<><OriginBadge meta={h.meta} /><ExampleBadge why={h.why} /></>}
      />
      <SourceNote why={h.why} />

      <div className="row">
        <div className="field" style={{ minWidth: 220 }}>
          <label className="field__label" htmlFor="git-person">Learner</label>
          <select id="git-person" className="select" value={person} onChange={(e) => setPerson(e.target.value)}>
            {learners.map((l) => <option key={l.person} value={l.person}>{learnerLabel(l.person)}</option>)}
          </select>
        </div>
      </div>

      <section className="hero" aria-labelledby="gh-h">
        <div className="section__head">
          <h2 className="section__title" id="gh-h">Where the habits differ</h2>
          <p className="section__sub">Each row is a share of commits. Flagged means past its floor and clear of zero.</p>
        </div>
        {habits.length === 0 ? (
          <EmptyState title="No commits to read yet" body="When a repository is registered, its commit habits appear here. Nothing is read until you register one." />
        ) : (
          <div className="chart stack" style={{ gap: "var(--space-4)" }}>
            <HabitDeltas habits={habits} />
            <ul className="legend" aria-label="How to read the chart">
              <LegendItem swatch={<span className="sw gh-sw gh-sw--bad" />}>Flagged, and worse than the experts</LegendItem>
              <LegendItem swatch={<span className="sw gh-sw" />}>Not flagged</LegendItem>
              <LegendItem swatch={<span className="sw sw--hatch sw--muted" />}>Floor: a smaller difference is never flagged</LegendItem>
              <LegendItem swatch={<span className="sw" style={{ height: 2, alignSelf: "center", background: "var(--fg)" }} />}>95% interval</LegendItem>
            </ul>
            <ChartFoot variant="about" meta={h.meta} extra={<span>Reference: <b>{d.reference?.n_experts ?? "?"} experts</b>.{d.reference?.note ? ` ${d.reference.note}.` : ""}</span>} />
          </div>
        )}
      </section>

      <hr className="rule" />
      <Suggestions d={d} flagged={flagged} />

      <hr className="rule" />
      <section className="section" aria-labelledby="gh-how">
        <h2 className="section__title" id="gh-how">How this was counted</h2>
        <p className="note"><b className="tabular">{d.n_commits.toLocaleString("en-GB")}</b> commits were counted.</p>
        <Details summary="Method and the habits as a table" wide>
          <div className="stack">
            <p className="note">{DIGEST_LABEL[d.digest_source] ?? d.digest_source}. {d.digest_source === "rules" ? "No model was involved." : "It ran on this laptop and saw digests, not commit text."}{d.digest_warming ? " The model is still warming up, so rules answered for now." : ""}</p>
            <HabitTable habits={habits} />
          </div>
        </Details>
      </section>
    </div>
  );
}

function Suggestions({ d, flagged }: { d: GitHabits; flagged: GitHabit[] }) {
  const list = d.suggestions ?? flagged.map((f) => f.suggestion).filter((s): s is NonNullable<typeof s> => !!s);
  return (
    <section className="section" aria-labelledby="gs-h">
      <div className="section__head">
        <h2 className="section__title" id="gs-h">Habits worth a look</h2>
        <p className="section__sub">General advice from a fixed list, with your numbers. Nothing is applied for you.</p>
      </div>
      {list.length === 0 ? (
        <EmptyState title="Nothing to suggest" body="No habit is far enough from the experts to be worth a change right now." />
      ) : (
        <div className="sug-grid">
          {list.map((s) => {
            const [fact, advice] = splitSentence(s.text);
            const { text, counts } = splitCounts(fact);
            return (
              <article key={s.id} className="card card__pad sug" aria-label={s.text}>
                <p className="sug__text">{text}{counts && <> <Hint label="The counts behind this">{counts}</Hint></>}</p>
                {advice && <p className="note">{advice}</p>}
                <p className="note">{s.can_draft ? "A draft can be prepared. " : ""}Nothing is committed or pushed.</p>
              </article>
            );
          })}
        </div>
      )}
    </section>
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
                <td>{r.flagged ? <span className="pill"><b>{r.state}</b></span> : <span className="pill">{r.state}</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
