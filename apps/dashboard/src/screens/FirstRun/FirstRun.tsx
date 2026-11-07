// First run: three screens, one click each (docs/knack-ux/07-first-run.md). No sidebar, no text field, no Next button.
// The role pack's safe defaults are written to the memory file when the one consent is answered; everything else is editable in Your data.
import { Suspense, lazy, useEffect, useReducer, useRef, useState, type ComponentType } from "react";
import { ApiError, api } from "../../api";
import { navigate } from "../../router";
import { useLoad } from "../../hooks";
import { Details } from "../../components/ui";
import { Glyph } from "../../components/Lockup";
import type { OnboardingAnswers, OnboardingQuestions } from "../../types";
import { CAPTURE_CHOICE_KEY, FIRST_RUN_KEY, START, STEPS, captureRecord, defaultAnswers, readyLines, reduce, roleCards, type CaptureChoice } from "./model";
import "./firstrun.css";

/**
 * The role step has a slot for "Connect your tools" chips, supplied by the connections track (components/connections/ConnectionChips.tsx, default or
 * named export `ConnectionChips`, one prop: `role`, the pack id). Every chip is off by default and nothing connects without a click on it. Found with
 * import.meta.glob: until the file exists the slot is empty and a role card advances at once (three clicks); with it, choosing a card opens its chips
 * and a Continue button (four clicks).
 */
const CHIP_FILES = import.meta.glob("../../components/connections/ConnectionChips.tsx");
const chipLoader = CHIP_FILES["../../components/connections/ConnectionChips.tsx"] as (() => Promise<{ default?: ComponentType<{ role: string }>; ConnectionChips?: ComponentType<{ role: string }> }>) | undefined;
const ConnectionChips = chipLoader ? lazy(async () => { const m = await chipLoader(); return { default: (m.default ?? m.ConnectionChips ?? (() => null)) as ComponentType<{ role: string }> }; }) : null;

const remember = (key: string, value: string): void => { try { window.localStorage.setItem(key, value); } catch { /* storage can be blocked: first run then shows again, which is harmless */ } };

export default function FirstRun() {
  const [s, dispatch] = useReducer(reduce, START);
  const packs = useLoad(() => api.packs(), []);
  const questions = useLoad(() => (s.role ? api.onboardingQuestions(s.role) : Promise.resolve({ data: null as unknown as OnboardingQuestions, meta: null, source: "demo" as const })), [s.role]);
  const [picked, setPicked] = useState<string | null>(null);
  const [written, setWritten] = useState<{ q: OnboardingQuestions; a: OnboardingAnswers } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const n = STEPS.indexOf(s.step) + 1;

  useEffect(() => { document.title = "Welcome · Knack"; }, []);
  useEffect(() => { heading.current?.focus(); }, [s.step]);

  const chooseCapture = async (choice: CaptureChoice) => {
    const q = questions.data;
    if (!s.role || !q) return;
    dispatch({ type: "choose-capture", choice });
    const answers = defaultAnswers(q, choice === "yes");
    try {
      await api.onboard(s.role, answers, q);
      remember(CAPTURE_CHOICE_KEY, captureRecord(choice));
      setWritten({ q, a: answers });
      dispatch({ type: "written" });
    } catch (e) {
      dispatch({ type: "failed", message: e instanceof ApiError ? e.message : "Could not write your memory file. Nothing was changed." });
    }
  };
  const finish = () => { remember(FIRST_RUN_KEY, new Date().toISOString()); navigate("/home"); };

  const cards = packs.data ? roleCards(packs.data) : [];
  return (
    <div className="firstrun">
      <div className="firstrun__col">
        <header className="firstrun__top">
          <Glyph size="firstRun" label="Knack" />
          <div className="firstrun__progress" role="progressbar" aria-label="First run progress" aria-valuemin={1} aria-valuemax={3} aria-valuenow={n} aria-valuetext={`${n} of 3`}>
            <i style={{ width: `${(n / 3) * 100}%` }} />
          </div>
          <span className="firstrun__count">{n} of 3</span>
        </header>

        {s.step === "role" && (
          <section className="firstrun__step" aria-labelledby="fr-h">
            <h1 id="fr-h" className="firstrun__q" ref={heading} tabIndex={-1}>What work do you do?</h1>
            {packs.status === "error" && !packs.data
              ? <p className="firstrun__note" role="alert">Could not read the roles. Nothing was changed. <button type="button" className="linkish" onClick={packs.reload}>Try again</button></p>
              : (
                <div className="firstrun__cards">
                  {cards.map((c) => (
                    <div key={c.id} className="rolecard__wrap" data-picked={picked === c.id || undefined}>
                      <button type="button" className="rolecard" aria-pressed={ConnectionChips ? picked === c.id : undefined} onClick={() => (ConnectionChips ? setPicked(c.id) : dispatch({ type: "choose-role", role: c.id }))}>
                        <span className="rolecard__name">{c.name}</span>
                        <span className="rolecard__line">{c.line}</span>
                      </button>
                      {ConnectionChips && picked === c.id && (
                        <div className="rolecard__chips">
                          <Suspense fallback={null}><ConnectionChips role={c.id} /></Suspense>
                          <button type="button" className="btn btn--primary" onClick={() => dispatch({ type: "choose-role", role: c.id })}>Continue</button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
          </section>
        )}

        {s.step === "capture" && (
          <section className="firstrun__step" aria-labelledby="fr-h">
            <h1 id="fr-h" className="firstrun__q" ref={heading} tabIndex={-1}>Let Knack learn from your work?</h1>
            <p className="firstrun__lede">It records when you are active, never what you read: no page text, no URLs, no field values. The record stays on this laptop.</p>
            <div className="firstrun__choices" role="group" aria-label="Your choice">
              {([["yes", "Yes, learn my times"], ["not-now", "Not now"], ["never", "Never"]] as [CaptureChoice, string][]).map(([k, label]) => (
                <button key={k} type="button" className="btn btn--secondary" disabled={s.writing || !questions.data} onClick={() => chooseCapture(k)}>{label}</button>
              ))}
            </div>
            {s.error && <p className="firstrun__note" role="alert">{s.error}</p>}
            <Details summary="Times only">
              <p>Recorded: when each step of your role starts and ends, and its name. Never recorded: page text, URLs, field values, passwords or screenshots.</p>
            </Details>
            <p className="firstrun__note">You can change this any time in Your data.</p>
            <button type="button" className="linkish firstrun__back" onClick={() => dispatch({ type: "back" })} disabled={s.writing}>Back</button>
          </section>
        )}

        {s.step === "ready" && written && (
          <section className="firstrun__step" aria-labelledby="fr-h">
            <h1 id="fr-h" className="firstrun__q" ref={heading} tabIndex={-1}>What Knack will remember</h1>
            <ul className="firstrun__lines">{readyLines(written.q, written.a).map((l) => <li key={l}>{l}</li>)}</ul>
            <p className="firstrun__note">Edit any line later in Your data.</p>
            <div><button type="button" className="btn btn--primary" onClick={finish}>Show my week</button></div>
          </section>
        )}
      </div>
    </div>
  );
}
