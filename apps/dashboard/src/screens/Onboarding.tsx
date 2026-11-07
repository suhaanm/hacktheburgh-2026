import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { ErrorState, Loading, OriginBadge } from "../components/common";
import { buildPreview } from "../lib/memoryPreview";
import { normDays } from "../lib/days";
import type { OnboardingAnswers, OnboardingQuestion, OnboardingQuestions, OnboardingResult, Pack } from "../types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const defaultHours = { start: "09:00", end: "17:30", days: [0, 1, 2, 3, 4] };

export default function Onboarding() {
  const packs = useLoad(() => api.packs(), []);
  const [role, setRole] = useState<string | null>(null);
  const qs = useLoad(() => (role ? api.onboardingQuestions(role) : Promise.resolve({ data: null as unknown as OnboardingQuestions, meta: null, source: "demo" as const })), [role]);
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Partial<OnboardingAnswers>>({});
  const [result, setResult] = useState<OnboardingResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const started = useRef<number | null>(null);
  const [took, setTook] = useState<number | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  const questions = role && qs.data ? qs.data.questions : [];
  const ready = !!role && !!qs.data;
  const total = ready ? questions.length + 2 : 7;
  const q: OnboardingQuestion | undefined = step >= 1 && step <= questions.length ? questions[step - 1] : undefined;
  const isCapture = ready && step === questions.length + 1;
  const finished = result != null;

  useEffect(() => { heading.current?.focus(); }, [step, finished]);

  // Safe defaults per role: the pack's own pre-selected actions stay "never without me" until the worker unticks them.
  // Capture is never pre-selected: it stays undefined until the worker chooses.
  useEffect(() => {
    const data = qs.data;
    if (!data || !role) return;
    const opts = (id: string) => data.questions.find((x) => x.id === id)?.options ?? [];
    const flagged = (id: string) => opts(id).filter((o) => o.default).map((o) => o.value);
    const risky = flagged("risky").length ? flagged("risky") : opts("risky").map((o) => o.value);
    const dh = data.questions.find((x) => x.id === "hours")?.default_hours;
    const hours = dh ? { start: dh.start, end: dh.end, days: normDays(dh.days) } : defaultHours;
    const pace = opts("pace").find((o) => o.default)?.value ?? (opts("pace").some((o) => o.value === "gradual") ? "gradual" : opts("pace")[Math.floor(opts("pace").length / 2)]?.value ?? "gradual");
    setAnswers({ tools: flagged("tools"), risky, tone: data.pack.tone_defaults.length, pace, hours });
  }, [qs.data, role]);

  const preview = useMemo(() => buildPreview(role ?? "", qs.data ?? undefined, step === 0 ? {} : answers), [role, qs.data, answers, step]);

  const choose = (r: string) => {
    if (started.current == null) started.current = Date.now();
    setRole(r);
  };
  const submit = async () => {
    if (!role || !qs.data) return;
    setBusy(true); setErr(null);
    try {
      const a = { tools: answers.tools ?? [], risky: answers.risky ?? [], tone: answers.tone ?? "short", pace: answers.pace ?? "gradual", hours: answers.hours ?? defaultHours, capture: answers.capture === true };
      const r = await api.onboard(role, a, qs.data);
      setResult(r.result);
      setTook(Math.round((Date.now() - (started.current ?? Date.now())) / 1000));
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not write the file. Your answers are kept; try again."); }
    finally { setBusy(false); }
  };
  const restart = () => { setRole(null); setStep(0); setAnswers({}); setResult(null); setTook(null); started.current = null; };

  if (packs.status === "error" && !packs.data) return <div className="page"><ErrorState error={packs.error} retry={packs.reload} what="the role list" /></div>;
  if (!packs.data) return <div className="page"><Loading label="Loading roles" /></div>;

  const pct = finished ? 100 : role ? (step / total) * 100 : 0;
  const lastQ = isCapture;
  const canNext = step === 0 ? !!role && !!qs.data : true;
  const canWrite = answers.capture !== undefined;

  return (
    <div className="page page--wide">
      <div className="ob">
        <div className="ob__main">
          <div className="ob__top">
            <div className="progress-line" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} aria-label="Set-up progress" style={{ ["--p" as string]: `${Math.max(pct, 4)}%` }}><i /></div>
            <div className="row row--between">
              <span className="ob__step">{finished ? "Done" : `Question ${Math.min(step + 1, total)} of ${total}`}</span>
              <OriginBadge meta={qs.meta} />
            </div>
          </div>

          {finished ? (
            <div className="ob-done">
              <h1 className="question" ref={heading} tabIndex={-1}>Your memory file is written</h1>
              <p className="t-lede">It lives on this device and you own it. Edit any line, or delete it, whenever you like.{took != null && <> Set-up took {took} seconds.</>}</p>
              <div className="stats">
                <div className="stat"><span className="stat__label">Role</span><span className="stat__value" style={{ fontSize: "var(--text-xl)" }}>{qs.data?.pack.name}</span></div>
                <div className="stat"><span className="stat__label">Revision</span><span className="stat__value tabular" style={{ fontSize: "var(--text-xl)" }}>{result.revision}</span></div>
              </div>
              <div className="ob__nav">
                <a className="btn btn--primary" href="#/memory">Open my memory file</a>
                <a className="btn btn--secondary" href="#/today">Go to Today</a>
                <button type="button" className="btn btn--quiet" onClick={restart}>Try another role</button>
              </div>
            </div>
          ) : step === 0 ? (
            <div className="ob__q" key="role">
              <h1 className="question" ref={heading} tabIndex={-1}>What kind of work do you do?</h1>
              <div className="ob__options" role="radiogroup" aria-label="Role">
                {packs.data.map((p) => <RoleCard key={p.id} pack={p} checked={role === p.id} onChoose={() => choose(p.id)} />)}
              </div>
              <p className="note">A starting point. Your own work takes over from here.</p>
              {role && qs.status === "error" && <ErrorState error={qs.error} retry={qs.reload} what="the questions" />}
            </div>
          ) : q ? (
            <div className="ob__q" key={q.id}>
              <h1 className="question" ref={heading} tabIndex={-1}>{q.prompt}</h1>
              <QuestionInput q={q} answers={answers} onChange={(a) => setAnswers((x) => ({ ...x, ...a }))} />
              {q.why && <p className="note">{q.why}</p>}
              {q.id === "risky" && <p className="note">Ticked actions stay behind your click. Untick only what you are happy to hand over.</p>}
            </div>
          ) : isCapture ? (
            <div className="ob__q" key="capture">
              <h1 className="question" ref={heading} tabIndex={-1}>Record when I'm active?</h1>
              <p className="t-lede">Times only. No page text, no URLs, nothing leaves this laptop. You can turn it off any time.</p>
              <div className="ob__options" role="radiogroup" aria-label="Record when I'm active">
                <label className="role-card">
                  <input type="radio" name="capture" value="yes" checked={answers.capture === true} onChange={() => setAnswers((x) => ({ ...x, capture: true }))} />
                  <span className="role-card__name">Yes, record times</span>
                  <span className="role-card__desc">Understudy learns your working rhythm, so it can find the free hours.</span>
                </label>
                <label className="role-card">
                  <input type="radio" name="capture" value="no" checked={answers.capture === false} onChange={() => setAnswers((x) => ({ ...x, capture: false }))} />
                  <span className="role-card__name">Not now</span>
                  <span className="role-card__desc">Nothing is recorded. You can change this later on the Memory screen.</span>
                </label>
              </div>
            </div>
          ) : null}

          {!finished && (
            <div className="ob__nav">
              {step > 0 && <button type="button" className="btn btn--quiet" onClick={() => setStep((s) => s - 1)}>Back</button>}
              {lastQ ? (
                <button type="button" className="btn btn--primary" disabled={busy || !canWrite} onClick={submit}>{busy ? "Writing the file" : "Write my memory file"}</button>
              ) : (
                <button type="button" className="btn btn--primary" disabled={!canNext} onClick={() => setStep((s) => s + 1)}>Next</button>
              )}
            </div>
          )}
          {err && <p className="field__error" role="alert">{err}</p>}
        </div>

        <aside className="ob__preview" aria-label="Preview of your memory file">
          <div className="row row--between">
            <span className="t-label">{finished ? "Written to" : "Your memory file, as you answer"}</span>
            <span className="t-label">{finished ? "~/.understudy/memory.md" : "draft, nothing saved yet"}</span>
          </div>
          <Preview text={finished ? result.memory_markdown : preview.text} fresh={finished ? new Set() : preview.fresh} />
        </aside>
      </div>
    </div>
  );
}

function RoleCard({ pack, checked, onChoose }: { pack: Pack; checked: boolean; onChoose: () => void }) {
  return (
    <label className="role-card">
      <input type="radio" name="role" value={pack.id} checked={checked} onChange={onChoose} />
      <span className="role-card__name">{pack.name}</span>
      <span className="role-card__desc">{pack.summary}</span>
      <span className="t-label">{pack.depth === "deep" ? "Fully built and validated" : "Starter pack"}</span>
    </label>
  );
}

function QuestionInput({ q, answers, onChange }: { q: OnboardingQuestion; answers: Partial<OnboardingAnswers>; onChange: (a: Partial<OnboardingAnswers>) => void }) {
  if (q.kind === "hours") {
    const h = answers.hours ?? defaultHours;
    return (
      <div className="hours-grid">
        <div className="time-pair">
          <div className="field"><label className="field__label" htmlFor="hs">From</label><input id="hs" className="input" type="time" value={h.start} onChange={(e) => onChange({ hours: { ...h, start: e.target.value } })} /></div>
          <div className="field"><label className="field__label" htmlFor="he">Until</label><input id="he" className="input" type="time" value={h.end} onChange={(e) => onChange({ hours: { ...h, end: e.target.value } })} /></div>
        </div>
        <div className="field">
          <span className="field__label" id="hd">On these days</span>
          <div className="day-chips" role="group" aria-labelledby="hd">
            {DAYS.map((d, i) => <button key={d} type="button" className="chip" aria-pressed={h.days.includes(i)} onClick={() => onChange({ hours: { ...h, days: h.days.includes(i) ? h.days.filter((x) => x !== i) : [...h.days, i].sort() } })}>{d}</button>)}
          </div>
        </div>
        <p className="note">Quiet hours are separate. You set those later on the Presence screen.</p>
      </div>
    );
  }
  const multi = q.kind === "multi";
  const key = q.id as "tools" | "risky" | "tone" | "pace";
  const value = answers[key];
  const picked = (v: string) => (multi ? ((value as string[] | undefined) ?? []).includes(v) : value === v);
  const toggle = (v: string) => {
    if (multi) {
      const cur = ((value as string[] | undefined) ?? []);
      onChange({ [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] } as Partial<OnboardingAnswers>);
    } else onChange({ [key]: v } as Partial<OnboardingAnswers>);
  };
  return (
    <div className="ob__options" role={multi ? "group" : "radiogroup"} aria-label={q.prompt}>
      {q.options.map((o) => (
        <label key={o.value} className="role-card">
          <input type={multi ? "checkbox" : "radio"} name={q.id} value={o.value} checked={picked(o.value)} onChange={() => toggle(o.value)} />
          <span className="role-card__name">{o.label}</span>
        </label>
      ))}
    </div>
  );
}

function Preview({ text, fresh }: { text: string; fresh: Set<number> }) {
  const lines = text.replace(/\n$/, "").split("\n");
  return (
    <pre className="pv" aria-live="polite" aria-atomic="false">
      {lines.map((l, i) => (
        <div key={`${i}-${l}`} className={`${l.startsWith("## ") ? "pv__h" : ""} ${l.startsWith("- (") || l.startsWith("---") ? "pv__dim" : ""} ${fresh.has(i) ? "pv__new" : ""}`}>{l || " "}</div>
      ))}
    </pre>
  );
}
