// First run: three screens, each with a Skip (docs/knack-ux/07-first-run.md, docs/knack-ux/defaults.md). No text field. The role pack's safe defaults are written to
// the memory file when the second screen is done; every consent is a real click on a card; permissions are shown as they are and never block anything.
import { Suspense, lazy, useCallback, useEffect, useMemo, useReducer, useRef, useState, type ComponentType } from "react";
import { ApiError, api } from "../../api";
import { navigate, useRoute } from "../../router";
import { useLoad } from "../../hooks";
import { Glyph } from "../../components/Lockup";
import { getBridge, permissionsAvailable, permStates, type PermKind, type PermState } from "../../components/shell/bridge";
import { reportWake } from "../../lib/wakeContext";
import { awarenessBridge } from "../YourData/awareness";
import { liveModelsBridge, wakeBridge, type LiveModelsState, type WakeStatus } from "../Settings/bridge";
import type { OnboardingQuestions } from "../../types";
import {
  BROWSER_ROWS, CAPTURE_CARD, CAPTURE_CHOICE_KEY, CHOICES, FIRST_RUN_KEY, GLANCE_CARD, GLANCE_CHOICE_KEY, NEEDS_APP, NO_ROLE, PERM_COPY, PROGRESS_KEY, RING_SENTENCE, SEEN_KEY, START, STEPS, VOICE_CARD, VOICE_CHOICE_KEY,
  captureRecord, defaultAnswers, heyKnackRow, kindsFor, nextUnanswered, parseProgress, permsToShow, progressRecord, reduce, roleCards, type Choice, type ConsentKind,
} from "./model";
import "./firstrun.css";

/**
 * The role step has a slot for "Connect your tools" chips, supplied by the connections track (components/connections/ConnectionChips.tsx, default or
 * named export `ConnectionChips`, one prop: `role`, the pack id). Every chip is off by default and nothing connects without a click on it. Found with
 * import.meta.glob: until the file exists the slot is empty and a role card advances at once; with it, choosing a card opens its chips and a Continue button.
 */
const CHIP_FILES = import.meta.glob("../../components/connections/ConnectionChips.tsx");
const chipLoader = CHIP_FILES["../../components/connections/ConnectionChips.tsx"] as (() => Promise<{ default?: ComponentType<{ role: string }>; ConnectionChips?: ComponentType<{ role: string }> }>) | undefined;
const ConnectionChips = chipLoader ? lazy(async () => { const m = await chipLoader(); return { default: (m.default ?? m.ConnectionChips ?? (() => null)) as ComponentType<{ role: string }> }; }) : null;

const store = {
  get: (k: string): string | null => { try { return window.localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string): void => { try { window.localStorage.setItem(k, v); } catch { /* storage can be blocked: first run then shows again, which is harmless */ } },
  del: (k: string): void => { try { window.localStorage.removeItem(k); } catch { /* ignore */ } },
};
const KEY_FOR: Record<ConsentKind, string> = { capture: CAPTURE_CHOICE_KEY, glance: GLANCE_CHOICE_KEY, voice: VOICE_CHOICE_KEY };
const SLOW_MS = 8000;
/** What the shell's Hey Knack state carries beyond the switch: the fix to offer (a permission or dictation) and whether the first-time welcome was heard. */
type WakeState = WakeStatus & { fix?: "microphone" | "speech" | "dictation" | null; welcomed?: boolean };
type WakeApi = NonNullable<ReturnType<typeof wakeBridge>> & { arm?: () => Promise<unknown> | unknown };
/** While first run is open the listener stays off until the worker turns it on here, so no macOS prompt appears at launch (WAKE-VOICE, capabilities-and-permissions.md). */
const setFirstRun = (on: boolean): void => reportWake({ firstRun: on } as never, undefined, 0);

const CHOICE_LABEL: Record<ConsentKind, Record<Choice, string>> = {
  // The card's title and sentence say what Yes does, so the three buttons are one or two words of one size and one weight.
  capture: { yes: "Yes", "not-now": "Not now", never: "Never" },
  glance: { yes: "Yes", "not-now": "Not now", never: "Never" },
  voice: { yes: "Yes", "not-now": "Not now", never: "Never" },
};

export default function FirstRun() {
  const route = useRoute();
  const again = route.path === "/setup";
  const awareness = useMemo(() => awarenessBridge(), []);
  const wakeApi = useMemo(() => wakeBridge(), []);
  const caps = useMemo(() => ({ glance: !!awareness, voice: !!wakeApi }), [awareness, wakeApi]);
  const kinds = kindsFor(caps);

  const [s, dispatch] = useReducer(reduce, undefined, () => (again ? START : (parseProgress(store.get(PROGRESS_KEY)) ?? START)));
  const packs = useLoad(() => api.packs(), []);
  const chosen = s.role && s.role !== NO_ROLE ? s.role : null;
  const questions = useLoad(() => (chosen ? api.onboardingQuestions(chosen) : Promise.resolve({ data: null as unknown as OnboardingQuestions, meta: null, source: "demo" as const })), [chosen]);
  const [picked, setPicked] = useState<string | null>(null);
  const [cardError, setCardError] = useState<Partial<Record<ConsentKind, string>>>({});
  const [slow, setSlow] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const n = STEPS.indexOf(s.step) + 1;

  useEffect(() => { document.title = "Welcome · Knack"; try { window.sessionStorage.setItem(SEEN_KEY, "1"); } catch { /* ignore */ } }, []);
  useEffect(() => { setFirstRun(true); return () => setFirstRun(false); }, []);
  useEffect(() => { heading.current?.focus(); }, [s.step]);
  useEffect(() => { if (!again) store.set(PROGRESS_KEY, progressRecord(s)); }, [s, again]);

  // Answering a card is a real click. The glance and voice answers reach the desktop app at once (and can be undone in Settings and Your data); capture waits for the file.
  const answer = useCallback(async (kind: ConsentKind, choice: Choice) => {
    setCardError((e) => ({ ...e, [kind]: undefined }));
    try {
      if (kind === "glance" && awareness) await awareness.setConsent({ trigger: choice === "yes" });
      if (kind === "voice" && wakeApi) { await wakeApi.set(choice === "yes"); if (choice === "yes") await (wakeApi as WakeApi).arm?.(); }
    } catch {
      setCardError((e) => ({ ...e, [kind]: "Could not change that. Nothing was changed." }));
      return;
    }
    store.set(KEY_FOR[kind], captureRecord(choice));
    dispatch({ type: "answer", kind, choice });
  }, [awareness, wakeApi]);

  // When the last card has an answer, go on.
  useEffect(() => { if (s.step === "may" && !s.writing && kinds.length > 0 && nextUnanswered(s, caps) === null) dispatch({ type: "advance" }); }, [s, caps, kinds.length]);

  // Writing the file: the role's safe defaults, with capture only when the worker said yes. A failure goes back to the cards with the message, and nothing is half-done.
  useEffect(() => {
    if (!s.writing || !chosen) return;
    const q = questions.data;
    if (!q) { if (questions.status === "error") dispatch({ type: "failed", message: "Could not read this role. Nothing was changed." }); return; }
    let live = true;
    const t = window.setTimeout(() => live && setSlow(true), SLOW_MS);
    api.onboard(chosen, defaultAnswers(q, s.answers.capture === "yes"), q).then(
      () => { if (!live) return; setSlow(false); dispatch({ type: "written" }); },
      (e: unknown) => { if (live) { setSlow(false); dispatch({ type: "failed", message: e instanceof ApiError ? `${e.message} Nothing was changed.` : "Could not switch your role. Nothing was changed." }); } },
    );
    return () => { live = false; window.clearTimeout(t); };
  }, [s.writing, chosen, questions.data, questions.status, s.answers.capture]);

  // Finishing: remember it, forget the progress, go Home, and only then ask every screen to read who the worker is again (a role that was just switched must show on Home).
  // The refresh is not sent while first run is open: it would remount this screen before its progress was saved, and the write would run again.
  const finish = useCallback(() => {
    store.set(FIRST_RUN_KEY, new Date().toISOString());
    store.del(PROGRESS_KEY);
    navigate("/home");
    if (s.written) window.setTimeout(() => window.dispatchEvent(new Event("understudy:retry")), 0);
  }, [s.written]);
  const cards = packs.data ? roleCards(packs.data) : [];
  const chooseRole = (id: string) => { setPicked(null); dispatch({ type: "choose-role", role: id }); };

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
                      <div className="rolecard">
                        <button type="button" className="rolecard__btn" aria-describedby={`rc-${c.id}`} aria-pressed={ConnectionChips && c.id !== NO_ROLE ? picked === c.id : undefined} onClick={() => (ConnectionChips && c.id !== NO_ROLE ? setPicked(c.id) : chooseRole(c.id))}>{c.name}</button>
                        <span className="rolecard__line" id={`rc-${c.id}`}>{c.line}{c.tag ? ` · ${c.tag}` : ""}</span>
                      </div>
                      {ConnectionChips && picked === c.id && c.id !== NO_ROLE && (
                        <div className="rolecard__chips">
                          <Suspense fallback={null}><ConnectionChips role={c.id} /></Suspense>
                          <button type="button" className="btn btn--primary" onClick={() => chooseRole(c.id)}>Continue</button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            <button type="button" className="linkish firstrun__skip" onClick={() => dispatch({ type: "skip" })}>Skip</button>
          </section>
        )}

        {s.step === "may" && (
          <section className="firstrun__step" aria-labelledby="fr-h">
            <h1 id="fr-h" className="firstrun__q" ref={heading} tabIndex={-1}>What may Knack do?</h1>
            <div className="consents">
              <ConsentCardView kind="capture" title={CAPTURE_CARD.title} text={CAPTURE_CARD.text} answer={s.answers.capture} error={cardError.capture} onAnswer={answer} disabled={s.writing} />
              {caps.glance && <ConsentCardView kind="glance" title={GLANCE_CARD.title} text={GLANCE_CARD.text} answer={s.answers.glance} error={cardError.glance} onAnswer={answer} disabled={s.writing} />}
              {caps.voice && <ConsentCardView kind="voice" title={VOICE_CARD.title} text={VOICE_CARD.text} answer={s.answers.voice} error={cardError.voice} onAnswer={answer} disabled={s.writing} />}
            </div>
            {s.error && <p className="firstrun__note firstrun__note--error" role="alert">{s.error}</p>}
            {s.writing && <p className="firstrun__note" role="status">{slow ? "This is taking longer than usual. You can skip and set your role later." : "Saving your choices"}</p>}
            <p className="firstrun__note">Change any of this in Your data.</p>
            <div className="firstrun__links">
              {/* The full app screen carries three cards and the ten-control budget; Back is there when the screen is shorter. */}
              {kindsFor(caps).length < 3 && <button type="button" className="linkish firstrun__back" onClick={() => dispatch({ type: "back" })} disabled={s.writing}>Back</button>}
              <button type="button" className="linkish firstrun__skip" onClick={() => dispatch({ type: "skip" })} disabled={s.writing}>Skip</button>
            </div>
          </section>
        )}

        {s.step === "check" && (
          <CheckStep answers={s.answers} heading={heading} onBack={() => dispatch({ type: "back" })} onFinish={finish} writing={s.writing} slow={slow} wakeApi={wakeApi} />
        )}
      </div>
    </div>
  );
}

/** One consent card: what Knack would do, in words printed whole, and Yes, Not now and Never of one size and one weight. Nothing is pre-selected. */
function ConsentCardView({ kind, title, text, answer, error, onAnswer, disabled }: { kind: ConsentKind; title: string; text: string; answer?: Choice; error?: string; onAnswer: (k: ConsentKind, c: Choice) => void; disabled?: boolean }) {
  return (
    <article className="consent" data-kind={kind} data-answered={answer || undefined} aria-labelledby={`cn-${kind}`}>
      <h2 className="consent__title" id={`cn-${kind}`}>{title}</h2>
      <p className="consent__text">{text}</p>
      <div className="consent__choices" role="group" aria-label={`Your choice: ${title}`}>
        {CHOICES.map((c) => (
          <button key={c} type="button" className="btn btn--secondary" aria-pressed={answer === c} disabled={disabled} onClick={() => onAnswer(kind, c)}>{CHOICE_LABEL[kind][c]}</button>
        ))}
      </div>
      {error && <p className="firstrun__note firstrun__note--error" role="alert">{error}</p>}
    </article>
  );
}

const STATE_WORD: Record<PermState, string> = { granted: "Allowed", "not-asked": "Not asked yet", off: "Turned off in System Settings" };

/** The last screen: the permissions as they are, Hey Knack's listening state, and "Show me". It never blocks: each permission says what will not work without it. */
function CheckStep({ answers, heading, onBack, onFinish, writing, slow, wakeApi }: {
  answers: Partial<Record<ConsentKind, Choice>>; heading: React.RefObject<HTMLHeadingElement>; onBack: () => void; onFinish: () => void; writing: boolean; slow: boolean; wakeApi: ReturnType<typeof wakeBridge>;
}) {
  const sample = useRef<HTMLDivElement>(null);
  const bridge = getBridge();
  const hasPerms = permissionsAvailable(bridge);
  const hasRing = typeof bridge.tryRing === "function";
  const [perms, setPerms] = useState<Record<PermKind, PermState> | null>(null);
  const [wake, setWake] = useState<WakeState | null>(null);
  const [restart, setRestart] = useState(false);
  const [live, setLive] = useState<LiveModelsState | null>(null);
  const [ring, setRing] = useState<"idle" | "working" | "done" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const liveApi = useMemo(() => liveModelsBridge(), []);

  const read = useCallback(() => {
    if (hasPerms) bridge.permissions!.state().then((r) => { setPerms(permStates(r)); setRestart(r?.needsRestart === true); }, () => { setPerms(null); setRestart(false); });
    wakeApi?.state().then((w) => setWake(w as WakeState), () => setWake(null));
  }, [bridge, hasPerms, wakeApi]);
  useEffect(() => {
    read();
    liveApi?.get().then(setLive, () => setLive(null));
    // A permission can change while this screen is open (the worker goes to System Settings and comes back, or revokes it later): read again when the window is looked at.
    const again = () => { if (document.visibilityState !== "hidden") read(); };
    window.addEventListener("focus", again);
    document.addEventListener("visibilitychange", again);
    return () => { window.removeEventListener("focus", again); document.removeEventListener("visibilitychange", again); };
  }, [read, liveApi]);

  const show = permsToShow(answers, { ring: hasRing && hasPerms });
  const ask = async (kind: PermKind) => { setError(null); try { await bridge.permissions!.request(kind); } catch { setError("Could not ask. Nothing was changed."); } read(); };
  const openSettings = (kind: PermKind) => { try { void bridge.permissions!.openSettings(kind); } catch { setError("Could not open System Settings."); } };
  const showMe = async () => {
    setRing("working"); setError(null);
    try {
      // The ring lands on the sample row below (the shell takes its place in this window's pixels); it draws for a few seconds and never clicks.
      const box = sample.current?.getBoundingClientRect();
      const r = (await (bridge.tryRing as (spot?: { x: number; y: number; width: number; height: number }) => Promise<unknown>)(box ? { x: box.left, y: box.top, width: box.width, height: box.height } : undefined)) as { ok?: boolean } | undefined;
      setRing(r && r.ok === false ? "failed" : "done");
    } catch { setRing("failed"); }
  };
  const hey = heyKnackRow(wake);
  const fix = wake?.fix === "microphone" || wake?.fix === "speech" ? wake.fix : null;
  const desktop = hasPerms || hasRing || !!wakeApi;
  const noKey = live && live.keyPresent === false;

  return (
    <section className="firstrun__step" aria-labelledby="fr-h">
      <h1 id="fr-h" className="firstrun__q" ref={heading} tabIndex={-1}>{desktop ? "Check that it works" : "You are set"}</h1>
      {!desktop && <p className="firstrun__lede">Knack starts counting now. You can change any choice in Your data.</p>}
      {!desktop && (
        <ul className="perms" aria-label="Needs the Knack app" data-testid="needs-app">
          {BROWSER_ROWS.map((r) => <li key={r.key} className="perm"><span className="perm__text"><b>{r.title}</b><span className="perm__state">{NEEDS_APP}</span></span></li>)}
        </ul>
      )}

      {desktop && show.length > 0 && (
        <ul className="perms" aria-label="Permissions">
          {show.map((k) => {
            const st = perms?.[k] ?? "not-asked";
            return (
              <li key={k} className="perm" data-state={st}>
                <span className="perm__text"><b>{PERM_COPY[k].title}</b><span className="perm__state">{STATE_WORD[st]}</span>{st !== "granted" && <span className="perm__without">{PERM_COPY[k].without}</span>}</span>
                {st === "not-asked" && <button type="button" className="btn btn--secondary btn--sm" onClick={() => void ask(k)}>Allow</button>}
                {st === "off" && <button type="button" className="btn btn--secondary btn--sm" onClick={() => openSettings(k)}>Open System Settings</button>}
              </li>
            );
          })}
        </ul>
      )}

      {hey && (
        <p className="firstrun__hey" data-testid="hey-knack"><b>{hey.title}</b><span className="perm__state">{hey.line}</span>{fix && hasPerms && <button type="button" className="btn btn--secondary btn--sm" onClick={() => openSettings(fix)}>Open System Settings</button>}</p>
      )}

      {restart && <p className="firstrun__note" role="status" data-testid="needs-restart">macOS needs Knack to restart before screen recording works. Quit and open it again when you are done here.</p>}

      {hasRing && (
        <div className="firstrun__try">
          <div ref={sample} className="firstrun__sample" aria-hidden="true">Needs you</div>
          <div><button type="button" className="btn btn--secondary" disabled={ring === "working"} onClick={() => void showMe()}>{ring === "working" ? "Showing" : "Show me"}</button></div>
          <p className="firstrun__note">{RING_SENTENCE}</p>
          {ring === "failed" && <p className="firstrun__note firstrun__note--error" role="alert">Could not show it. Nothing was changed. Try again with this window in front.</p>}
        </div>
      )}

      {noKey && <p className="firstrun__note" data-testid="no-key">No Gemini key found, so Knack runs on example data. Add it to .env and reopen Knack.</p>}
      {error && <p className="firstrun__note firstrun__note--error" role="alert">{error}</p>}
      {writing && <p className="firstrun__note" role="status">{slow ? "Still saving. You can carry on." : "Saving your choices"}</p>}

      <div className="firstrun__links firstrun__links--end">
        <button type="button" className="btn btn--primary" onClick={onFinish}>Show my week</button>
        <button type="button" className="linkish firstrun__back" onClick={onBack} disabled={writing}>Back</button>
      </div>
    </section>
  );
}
