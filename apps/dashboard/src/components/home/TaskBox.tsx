import { useCallback, useEffect, useRef, useState } from "react";
import { getBridge } from "../shell/bridge";
import { Icon } from "../shell/icons";
import { answerQuestion, decideConsent, readTask, submitTask } from "../../lib/taskClient";
import {
  BOX_LABEL, BOX_PLACEHOLDER, NOT_STARTED, checkTask, consentButtons, examplesFor, summaryLine,
  type ConsentCard, type ConsentChoice, type QuestionCard, type Submitted,
} from "../../lib/taskbox";

/**
 * "What should Knack do?" The one text field on Home: type a task and press Enter, or open the Ask bar to talk (only where the desktop app has one). Examples
 * fill the field and never send. Whatever the task service answers is shown at once, in its own plain line; if it wants the worker's consent it is a card with the
 * scope printed whole and two buttons of one size (a small More reveals the wider choice where the service offers it); if it has a question, a card with its options.
 * Nothing is auto-sent, nothing is pre-selected, focus never jumps to a button (so the Enter that sent the task cannot also answer its consent), and with no task
 * service the box says nothing was started and keeps what was typed.
 */
type Phase =
  | { at: "idle" }
  | { at: "sending" }
  | { at: "placed"; sub: Submitted; decided: string | null; busy: boolean; error: string | null; more: boolean }
  | { at: "unavailable" }
  | { at: "error"; message: string };

const DECIDED: Record<ConsentChoice, string> = { allow: "Allowed. Knack is starting.", everything: "Allowed. Knack is starting.", decline: "Not started. Nothing was changed." };
const POLL_MS = 1200;
const POLL_MAX = 50;

export function TaskBox({ role, onPlaced }: { role: string | null; onPlaced?: () => void }) {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>({ at: "idle" });
  const [answer, setAnswer] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);

  const check = checkTask(text);
  const bridge = getBridge();
  const canTalk = typeof bridge.ask === "function";
  const busy = phase.at === "sending";
  const tooLong = !check.ok && check.message !== null;

  // An inline answer is read once the task is done: asked every second or so, for at most a minute.
  const waitForAnswer = useCallback(async (id: string) => {
    for (let i = 0; i < POLL_MAX && live.current; i++) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      const t = await readTask(id);
      if (!live.current) return;
      if (t && (t.state === "done" || t.state === "failed" || t.state === "stopped")) {
        if (t.state === "done" && t.answer) setAnswer(t.answer);
        return;
      }
    }
  }, []);

  const send = useCallback(async () => {
    const c = checkTask(text);
    if (!c.ok || busy) return;
    setAnswer(null);
    setPhase({ at: "sending" });
    const r = await submitTask(c.text, "typed");
    if (!live.current) return;
    if (r.kind === "unavailable") { setPhase({ at: "unavailable" }); return; }
    if (r.kind === "error") { setPhase({ at: "error", message: r.message }); return; }
    setText("");
    setPhase({ at: "placed", sub: r.sub, decided: null, busy: false, error: null, more: false });
    onPlaced?.();
    if (r.sub.route === "answer" && !r.sub.consent && !r.sub.question) void waitForAnswer(r.sub.id);
  }, [text, busy, onPlaced, waitForAnswer]);

  const decide = async (choice: ConsentChoice) => {
    if (phase.at !== "placed" || phase.busy) return;
    const sub = phase.sub;
    setPhase({ ...phase, busy: true, error: null });
    const d = await decideConsent(sub.id, choice);
    if (!live.current) return;
    if (d.kind === "done") { setPhase({ at: "placed", sub, decided: DECIDED[choice], busy: false, error: null, more: false }); onPlaced?.(); if (choice !== "decline" && sub.route === "answer") void waitForAnswer(sub.id); return; }
    setPhase({ at: "placed", sub, decided: null, busy: false, error: d.kind === "unavailable" ? NOT_STARTED : d.message, more: phase.more });
  };

  const answerIt = async (optionId: string, label: string) => {
    if (phase.at !== "placed" || phase.busy) return;
    const sub = phase.sub;
    setPhase({ ...phase, busy: true, error: null });
    const d = await answerQuestion(sub.id, optionId);
    if (!live.current) return;
    if (d.kind === "done") { setPhase({ at: "placed", sub, decided: `Answered: ${label}.`, busy: false, error: null, more: false }); onPlaced?.(); return; }
    setPhase({ at: "placed", sub, decided: null, busy: false, error: d.kind === "unavailable" ? NOT_STARTED : d.message, more: false });
  };

  const examples = examplesFor(role);
  const showExamples = focused && text === "" && phase.at !== "sending";

  return (
    <section className="taskbox" aria-labelledby="taskbox-h" data-testid="task-box">
      <h2 id="taskbox-h" className="taskbox__label">{BOX_LABEL}</h2>
      <form className="taskbox__form" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <div className="taskbox__field">
          <input
            ref={input}
            className="input taskbox__input"
            type="text"
            value={text}
            placeholder={BOX_PLACEHOLDER}
            autoComplete="off"
            spellCheck
            dir="auto"
            aria-labelledby="taskbox-h"
            aria-describedby="taskbox-status"
            aria-invalid={tooLong ? true : undefined}
            onChange={(e) => { setText(e.target.value); if (phase.at === "error" || phase.at === "unavailable") setPhase({ at: "idle" }); }}
            onFocus={() => setFocused(true)}
            onBlur={() => window.setTimeout(() => { if (live.current) setFocused(false); }, 150)}
            onKeyDown={(e) => {
              // Enter sends; an Enter that only finishes a word in an input method (isComposing) does not.
              if (e.key === "Enter" && !e.nativeEvent.isComposing && !e.shiftKey) { e.preventDefault(); void send(); }
            }}
          />
          {canTalk && (
            <button type="button" className="taskbox__mic" aria-label="Talk to Knack" onClick={() => bridge.ask?.()}>
              <Icon name="mic" />
            </button>
          )}
          {check.ok && <button type="submit" className="btn btn--primary btn--sm taskbox__send" disabled={busy}>{busy ? "Sending" : "Send"}</button>}
        </div>
        {showExamples && (
          <div className="taskbox__examples" role="group" aria-label="Suggestions">
            {examples.map((x) => <button key={x} type="button" className="taskbox__chip" onMouseDown={(e) => e.preventDefault()} onClick={() => { setText(x); input.current?.focus(); }}>{x}</button>)}
          </div>
        )}
      </form>

      <div id="taskbox-status" className="taskbox__status" role="status" aria-live="polite">
        {tooLong && <p className="taskbox__line taskbox__line--error">{!check.ok ? check.message : ""}</p>}
        {phase.at === "sending" && <p className="taskbox__line">Sending</p>}
        {phase.at === "unavailable" && <p className="taskbox__line taskbox__line--error">{NOT_STARTED}</p>}
        {phase.at === "error" && <p className="taskbox__line taskbox__line--error">{phase.message}</p>}
        {phase.at === "placed" && <p className="taskbox__line" data-testid="task-summary">{summaryLine(phase.sub)}</p>}
        {phase.at === "placed" && phase.decided && <p className="taskbox__line">{phase.decided}</p>}
        {phase.at === "placed" && phase.error && <p className="taskbox__line taskbox__line--error" role="alert">{phase.error}</p>}
      </div>

      {phase.at === "placed" && !phase.decided && phase.sub.consent && (
        <ConsentCardView c={phase.sub.consent} busy={phase.busy} more={phase.more} onMore={() => setPhase({ ...phase, more: !phase.more })} onChoose={decide} />
      )}
      {phase.at === "placed" && !phase.decided && !phase.sub.consent && phase.sub.question && (
        <QuestionCardView q={phase.sub.question} busy={phase.busy} onChoose={answerIt} />
      )}
      {answer && (
        <div className="taskbox__answer" data-testid="task-answer">
          <p className="taskbox__answer-text" dir="auto">{answer}</p>
          <button type="button" className="linkish" onClick={() => setAnswer(null)}>Dismiss</button>
        </div>
      )}
    </section>
  );
}

function ConsentCardView({ c, busy, more, onMore, onChoose }: { c: ConsentCard; busy: boolean; more: boolean; onMore: () => void; onChoose: (x: ConsentChoice) => void }) {
  const b = consentButtons(c);
  return (
    <article className="taskcard" data-testid="task-consent" aria-label="Before Knack starts">
      <p className="taskcard__scope" dir="auto">{c.scope}</p>
      {c.can.length > 0 && <p className="taskcard__line"><b>It can:</b> {c.can.join("; ")}.</p>}
      {c.cannot.length > 0 && <p className="taskcard__line"><b>It cannot:</b> {c.cannot.join("; ")}.</p>}
      {c.folder && <p className="taskcard__line"><b>Where:</b> <span dir="auto">{c.folder}</span></p>}
      {c.cost && <p className="taskcard__line">{c.cost}</p>}
      {c.maxMinutes !== null && <p className="taskcard__line">It stops after {c.maxMinutes} {c.maxMinutes === 1 ? "minute" : "minutes"}.</p>}
      <div className="taskcard__actions">
        {b.main.map((x) => <button key={x.id} type="button" className="btn btn--secondary" disabled={busy} onClick={() => onChoose(x.id)}>{x.label}</button>)}
        {b.more.length > 0 && <button type="button" className="linkish" aria-expanded={more} onClick={onMore}>More</button>}
      </div>
      {more && b.more.length > 0 && (
        <div className="taskcard__actions taskcard__actions--more">
          {b.more.map((x) => <button key={x.id} type="button" className="btn btn--secondary" disabled={busy} onClick={() => onChoose(x.id)}>{x.label}</button>)}
        </div>
      )}
    </article>
  );
}

function QuestionCardView({ q, busy, onChoose }: { q: QuestionCard; busy: boolean; onChoose: (id: string, label: string) => void }) {
  return (
    <article className="taskcard" data-testid="task-question" aria-label="Knack has a question">
      <p className="taskcard__scope" dir="auto">{q.text}</p>
      <div className="taskcard__actions">
        {q.options.map((o) => <button key={o.id} type="button" className="btn btn--secondary" disabled={busy} onClick={() => onChoose(o.id, o.label)}>{o.label}</button>)}
      </div>
    </article>
  );
}
