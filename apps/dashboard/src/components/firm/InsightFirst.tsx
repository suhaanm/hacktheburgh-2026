// The shape every Admin screen shares: one headline sentence built by code, at most one simple chart or short list, and the numbers behind one closed
// "See the numbers". Small pieces so each screen reads the same way and a test can check the rules once.
import { useState, type ReactNode } from "react";
import { Hint } from "../Hint";
import { Details, wordCount } from "../ui";
import { CONFIDENCE_HINT, CONFIDENCE_WORD, freshness, type Confidence } from "./insights";

/** The one sentence a screen opens with. It is a fixed template filled from the data (insights.ts), never model text. */
export function Headline({ children, id }: { children: ReactNode; id?: string }) {
  return <p className="insight-head hero-insight" id={id}>{children}</p>;
}

/** The small confidence word of an insight, with what it means one tap away. The word is chosen by code from n and the interval. */
export function ConfidenceWord({ level, hint = false }: { level: Confidence; hint?: boolean }) {
  return (
    <span className="conf" data-level={level}>
      <span className="conf__dot" aria-hidden="true" />
      <span className="conf__word">{CONFIDENCE_WORD[level]}</span>
      {hint && <Hint label="What this word means">{CONFIDENCE_HINT[level]}</Hint>}
    </span>
  );
}

/** What the three confidence words mean, as label : value rows. Printed once on a screen, in the closed "How reliable" row, not as a hint on every card. */
export const CONFIDENCE_ROWS: [string, string][] = (Object.keys(CONFIDENCE_WORD) as Confidence[]).map((k) => [CONFIDENCE_WORD[k], CONFIDENCE_HINT[k]]);

/** Numbers that are old or dated after today, said once in words under the headline. Silent when fresh or unreadable. */
export function FreshNote({ asOf, now }: { asOf: string | null | undefined; now: Date }) {
  const f = freshness(asOf, now);
  return f.text ? <p className="note insight-fresh" role="status">{f.text}</p> : null;
}

/** The closed disclosure every Admin screen keeps its numbers in. */
export function SeeNumbers({ children, summary = "See the numbers" }: { children: ReactNode; summary?: string }) {
  return <Details summary={summary} wide>{children}</Details>;
}

/**
 * A small table of figures with their intervals: the first column names the row. Four rows show, the rest behind one "Show all N", so an opened
 * disclosure stays a few scannable lines. Cells are strings made by code, so a number never reaches the page as NaN.
 */
export function NumbersTable({ heads, rows, caption, limit = 4 }: { heads: string[]; rows: string[][]; caption: string; limit?: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, limit);
  if (rows.length === 0) return <p className="note">No figures yet.</p>;
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <div className="table-wrap">
        <table className="table numbers">
          <caption className="u-sr-only">{caption}</caption>
          <thead><tr>{heads.map((h, i) => <th key={h} scope="col" className={i > 0 ? "num" : undefined}>{h}</th>)}</tr></thead>
          <tbody>
            {shown.map((r, k) => (
              <tr key={`${r[0]}-${k}`}>{r.map((c, i) => (i === 0 ? <th key={i} scope="row">{c}</th> : <td key={i} className="num">{c}</td>))}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > limit && <div><button type="button" className="btn btn--quiet btn--sm" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button></div>}
    </div>
  );
}

/**
 * A paragraph kept to about `max` words: the first sentences that fit stay, the rest go behind one closed "More" so an opened block stays one short paragraph.
 * Text shorter than `max` is returned whole. Never returns an empty paragraph.
 */
export function ShortParagraph({ text, max = 36, more = "More" }: { text: string; max?: number; more?: string }) {
  const sentences = text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g)?.map((s) => s.trim()).filter(Boolean) ?? [];
  let used = 0;
  const head: string[] = [];
  for (const s of sentences) {
    const w = wordCount(s);
    if (head.length > 0 && used + w > max) break;
    head.push(s);
    used += w;
  }
  const rest = sentences.slice(head.length);
  if (head.length === 0) return null;
  return (
    <>
      <p className="note">{head.join(" ")}</p>
      {rest.length > 0 && <Details summary={more}><p className="note">{rest.join(" ")}</p></Details>}
    </>
  );
}
