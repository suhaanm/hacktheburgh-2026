import { useEffect, useRef, useState } from "react";
import { ApiError, api, type Loaded } from "../api";
import { useLoad } from "../hooks";
import { useAppState } from "../store";
import { Note, OriginBadge, SourceNote } from "./common";
import { Hint } from "./Hint";
import { Details } from "./ui";
import { CHIPS, MAX_QUESTION, actionsOf, askedTimeNote, badgeText, bodySentences, checkReading, cleanQuestion, fallbackReading, fmtFact, isAnswer, limitsOf, pathWords, sourceReading, usesWithFacts } from "../lib/explain";
import type { ExplainResult, PacketFact } from "../types";

/**
 * "Where did my time go?" The answer comes first, in a few plain sentences. Under it: where the words came from and what the check
 * found, a small "where this comes from" under every sentence, the limits and the footer (always shown), and the numbers themselves.
 * The question is a short box with example chips; its text lives in the box and nowhere else on the page.
 */
export function Explain({ person }: { person?: string }) {
  const app = useAppState();
  const packet = useLoad(() => api.evidencePacket(person), [person]);
  const [question, setQuestion] = useState("");
  const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [res, setRes] = useState<Loaded<ExplainResult> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const run = useRef(0);
  const auto = useRef(false);

  const ask = async (q: string | undefined, hint: string) => {
    const mine = ++run.current;
    setPhase("loading"); setErr(null); setElapsed(0);
    try {
      const r = await api.evidenceExplain({ person, question: q }, hint);
      if (mine === run.current) { setRes(r); setPhase("ready"); }
    } catch (e) {
      if (mine === run.current) { setErr(e instanceof ApiError ? `${e.message}${e.code ? ` (${e.code})` : ""}` : "That did not go through. Try again."); setPhase("error"); }
    }
  };

  // A calm clock while a slow model answers.
  useEffect(() => {
    if (phase !== "loading") return;
    const id = window.setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [phase]);

  // The first look is free when no model can be involved: mock mode (the template only) or example data. Otherwise the worker presses.
  useEffect(() => {
    if (auto.current || !app.extReady || !packet.data) return;
    if (app.mock === true || packet.why) { auto.current = true; void ask(undefined, "where_time_went"); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.extReady, app.mock, packet.data, packet.why]);

  const submit = (text: string, hint: string) => { setQuestion(text); void ask(cleanQuestion(text), hint); };
  const facts = packet.data?.facts ?? [];
  const example = !!(res?.why ?? packet.why);

  return (
    <section className="explain" id="explain" aria-labelledby="ex-h">
      <div className="section__head">
        <h2 id="ex-h" className="section__title">Where did my time go?</h2>
        <p className="section__sub">Reads the numbers behind this case. Code checks each number in the words against the data.</p>
      </div>
      <SourceNote why={res?.why ?? (phase === "idle" ? packet.why : null)} also={example ? "These are example answers. They do not change with what you ask." : undefined} alsoInline />

      <p className="u-sr-only" role="status" aria-live="polite">{phase === "loading" ? "Writing the answer." : phase === "ready" ? "The answer is ready." : phase === "error" ? "The answer could not be made." : ""}</p>

      {phase === "idle" && (
        <div className="explain__start">
          <p className="explain__lede">Press the button to have this case explained. It reads numbers only, and nothing else on this screen waits for it.</p>
          <div className="row"><button type="button" className="btn btn--primary" onClick={() => void ask(undefined, "where_time_went")}>Explain this case</button></div>
        </div>
      )}

      {phase === "loading" && <Progress elapsed={elapsed} />}

      {phase === "error" && (
        <div className="state state--error" role="alert">
          <span className="state__mark" aria-hidden="true" />
          <h3 className="state__title">The explanation could not be made</h3>
          <p className="state__body">{err}</p>
          <button type="button" className="btn btn--secondary" onClick={() => void ask(cleanQuestion(question), "where_time_went")}>Try again</button>
        </div>
      )}

      {res && phase !== "loading" && phase !== "error" && <Answer r={res.data} facts={facts} example={example} />}

      <Ask question={question} onChange={setQuestion} onSubmit={submit} busy={phase === "loading"} />

      {res && phase === "ready" && <Backing r={res.data} facts={facts} />}
    </section>
  );
}

function Progress({ elapsed }: { elapsed: number }) {
  return (
    <div className="explain__progress" aria-hidden={false}>
      <span className="skeleton skeleton--short" /><span className="skeleton" /><span className="skeleton skeleton--mid" />
      <p className="note">Writing the answer, {elapsed} s so far.{elapsed >= 6 ? " The first answer from a model on this laptop can take about two minutes while the model loads. Nothing else is waiting on it, and you can keep reading." : ""}</p>
    </div>
  );
}

/** The words, the coaching, and under them where the words came from. */
function Answer({ r, facts, example }: { r: ExplainResult; facts: PacketFact[]; example: boolean }) {
  const body = bodySentences(r);
  const actions = actionsOf(r);
  const src = sourceReading(r);
  const chk = checkReading(r.check);
  const fb = fallbackReading(r);
  const asked = askedTimeNote(r.question);
  return (
    <div className="explain__answer stack" data-testid="explain-answer" data-source={r.source}>
      <div className="stack" style={{ gap: "var(--space-3)" }}>
        <p className="t-label">{isAnswer(r) ? "The answer" : "What the numbers show"}</p>
        {body.slice(0, 3).map((s, i) => (
          <p key={i} className="explain__text">{s.text}<Uses uses={s.uses} facts={facts} /></p>
        ))}
        {body.length > 3 && (
          <Details summary={`${body.length - 3} more ${body.length - 3 === 1 ? "sentence" : "sentences"}`}>
            <div className="stack" style={{ gap: "var(--space-3)" }}>{body.slice(3).map((s, i) => <p key={i} className="explain__text">{s.text}<Uses uses={s.uses} facts={facts} /></p>)}</div>
          </Details>
        )}
        {asked && <p className="note">{asked}</p>}
      </div>

      <div className="explain__prov" data-ok={chk.ok} data-testid="explain-prov">
        <div className="row" style={{ gap: "var(--space-2)" }}>
          <span className="pill pill--source" data-source={r.source}>{src.label}</span>
          <span className="pill pill--check-run" data-ok={chk.ok}><span className="pill__glyph-char" aria-hidden="true">{chk.ok ? "✓" : "✕"}</span>{chk.ok ? "Checked against the data" : "Did not pass the check"}</span>
          <Hint label="About this answer">{src.detail} {chk.text}</Hint>
        </div>
        {chk.ok && <p className="note">Checked by code against the data. That shows the words come from the data, not that the data is right.</p>}
        {fb && <Note tone="warn">{fb}</Note>}
        {!chk.ok && <Note tone="warn">{chk.text}</Note>}
      </div>

      {actions.length > 0 && (
        <div className="stack" style={{ gap: "var(--space-3)" }}>
          <p className="t-label">Worth practising</p>
          <ul className="explain__actions">
            {actions.map((a) => (
              <li key={a.id}>
                <p className="explain__text">{a.text}<Uses uses={a.uses} facts={facts} /></p>
                <p className="note">{a.chosen_by === "code" ? "Picked by code from a fixed list." : "Picked by the model from a fixed list; code checked it."}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {example && <p className="u-sr-only">Example answer.</p>}
    </div>
  );
}

/**
 * "Where these numbers come from": a Hint on the sentence, listing the packet fact behind each cited path. The same numbers are in the
 * sentence itself and in the table of all the numbers under the answer, so the Hint is never the only copy.
 */
function Uses({ uses, facts }: { uses: string[]; facts: PacketFact[] }) {
  if (uses.length === 0) return null;
  const rows = usesWithFacts(uses, facts);
  return (
    <>
      {" "}
      <Hint label={uses.length === 1 ? "Where this number comes from" : "Where these numbers come from"}>
        Read from the packet the engine built, not supplied by the model:{" "}
        {rows.map(({ path, fact }, i) => (
          <span key={path}>{i > 0 ? "; " : ""}<code>{pathWords(path)}</code> {fact ? <b className="tabular">{fmtFact(fact)}</b> : <span>not found in the packet</span>}</span>
        ))}
        .
      </Hint>
    </>
  );
}

function Ask({ question, onChange, onSubmit, busy }: { question: string; onChange: (v: string) => void; onSubmit: (text: string, hint: string) => void; busy: boolean }) {
  return (
    <form className="explain__ask" onSubmit={(e) => { e.preventDefault(); onSubmit(question, "where_time_went"); }} aria-label="Ask about this case">
      <div className="field">
        <label className="field__label" htmlFor="ex-q">Ask about this case</label>
        <div className="explain__bar">
          <input id="ex-q" className="input" type="text" value={question} maxLength={MAX_QUESTION} autoComplete="off" spellCheck={false}
            placeholder="For example, why was I slow?" onChange={(e) => onChange(e.target.value)} />
          <button type="submit" className="btn btn--secondary" disabled={busy}>{busy ? "Asking" : "Ask"}</button>
        </div>
        <span className="field__hint">Your words are turned into one of a few fixed questions by code. A model never sees them.</span>
      </div>
      <div className="row" style={{ gap: "var(--space-2)" }} role="group" aria-label="Example questions">
        {CHIPS.map((c) => <button key={c.id} type="button" className="chip" disabled={busy} onClick={() => onSubmit(c.text, c.id)}>{c.text}</button>)}
      </div>
    </form>
  );
}

/** Always shown with an answer: the limits and the footer with its badge. Then the numbers themselves, one click away. */
function Backing({ r, facts }: { r: ExplainResult; facts: PacketFact[] }) {
  const limits = limitsOf(r);
  const meta = { origin: r.badge.origin as "real" | "synthetic" | "mixed", n: r.badge.n, n_unit: r.badge.n_unit, split: r.badge.split, interval_level: 0.95, note: null, generated_at: "" };
  return (
    <div className="stack explain__backing">
      <div data-testid="explain-limits">
        {limits.length === 0 ? <p className="note">The engine listed no limits for this answer. That is itself a problem: every answer must list its limits.</p> : (
          <Details summary={`What this does not show (${limits.length})`}>
            <ul className="plain-list explain__limits">{limits.map((l) => <li key={l.id} className="ev-note">{l.text}</li>)}</ul>
          </Details>
        )}
      </div>
      <p className="explain__footer" data-testid="explain-footer">
        <OriginBadge meta={meta} always />
        <span>{r.footer}</span>
        <span className="u-muted">{badgeText(r.badge)}{r.badge.split ? `, ${r.badge.split.replace(/_/g, " ")}` : ""}</span>
      </p>
      {facts.length > 0 && (
        <Details summary={`All the numbers an explanation can use (${facts.length})`} wide>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Where in the packet</th><th className="num">Value</th></tr></thead>
            <tbody>{facts.map((f) => <tr key={f.path}><td><code>{f.path}</code></td><td className="num">{fmtFact(f)}</td></tr>)}</tbody>
          </table></div>
        </Details>
      )}
    </div>
  );
}
