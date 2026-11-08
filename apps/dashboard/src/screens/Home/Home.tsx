// Home: one sentence about the week, one action, at most two quiet rows (docs/knack-ux/01-home.md). No chart, no statistic, no paragraph.
// A blocking approval or a safety pause takes the hero slot. Everything the old Your week showed beyond this moved: the Monday note to the
// palette, "What your admin can see" to Your data, the example-week selector to Settings, the data mode to the sidebar's status line.
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from "react";
import { api, forgetBackoff } from "../../api";
import { reportInsight } from "../../lib/wakeContext";
import { refreshNeedsBadge } from "../NeedsYou/count";
import { useRoute } from "../../router";
import { useAppState } from "../../store";
import { useLoad } from "../../hooks";
import { pick } from "../../screenRegistry";
import { ApprovalHero } from "../../components/home/ApprovalHero";
import { TaskBox } from "../../components/home/TaskBox";
import { WhyThis } from "../../components/home/PointerCard";
import { Hint } from "../../components/Hint";
import { Icon } from "../../components/shell/icons";
import { loadRepeats } from "../Repeats/data";
import { loadWorker, parseStory } from "./data";
import { blockingItem, remainingAfter } from "./approval";
import { COULD_NOT_LOAD, GROWTH_ROW, coachLine, heroAction, heroSentence, needsLine, quietFor, repeatsHint, repeatsRow, rowSentence, tryLine, weekOf, type Quiet } from "./model";
import { useExampleWeek } from "./story";
import "../../components/home/home.css";

function Row({ href, icon, children, hint }: { href: string; icon: "needs-you" | "routines" | "growth" | "coach"; children: string; hint?: { label: string; text: string } | null }) {
  return (
    <li className="home__row">
      <a className="home__row-link" href={href}>
        <Icon name={icon} />
        <span className="home__row-text" dir="auto">{children}</span>
        <Icon name="chevron" className="home__row-chev" />
      </a>
      {hint && <Hint label={hint.label}>{hint.text}</Hint>}
    </li>
  );
}

/** Holds the hero's height while the week loads. After 600 ms it says what it is doing; with the engine still starting it says that instead. */
function Reading() {
  const engineUp = useAppState().engineUp;
  const [late, setLate] = useState(false);
  useEffect(() => { const t = window.setTimeout(() => setLate(true), 600); return () => window.clearTimeout(t); }, []);
  return (
    <div className="page page--read home" aria-busy="true">
      <div className="home__loading" role="status">
        <span className="u-sr-only">Loading your week</span>
        {late && <p className="home__reading">{engineUp === null ? "Starting Knack, about 20 seconds." : "Reading your week"}</p>}
      </div>
    </div>
  );
}

function QuietState({ q, onRetry }: { q: Quiet; onRetry: () => void }) {
  return (
    <section className="home__hero home__quiet" aria-labelledby="home-hero">
      <h1 id="home-hero" className="home__hero-text hero-insight">{q.title}</h1>
      <p className="home__why">{q.body}</p>
      {q.action === "try-again" && <div className="home__actions"><button type="button" className="btn btn--secondary" onClick={onRetry}>Try again</button></div>}
      {q.action === "choose-role" && <div className="home__actions"><a className="btn btn--primary" href="#/first-run">Choose a role</a></div>}
    </section>
  );
}

// The background tasks list is Track C's (components/routines/BackgroundTasks): one line per task, nothing when there are none. Found by glob so Home builds whether or
// not that folder has landed in the branch being built; a missing one draws nothing.
const BACKGROUND = import.meta.glob("../../components/routines/BackgroundTasks.tsx");
type BackgroundModule = { default?: ComponentType<{ limit?: number }>; BackgroundTasks?: ComponentType<{ limit?: number }> };
const loadBackground = pick(BACKGROUND, ["../../components/routines/BackgroundTasks.tsx"]) as (() => Promise<BackgroundModule>) | null;
// The list is a named export of that module; a default export is accepted too. Either way `lazy` gets the { default } shape it needs.
const BackgroundTasks = lazy(async () => {
  const m = loadBackground ? await loadBackground() : null;
  return { default: (m?.default ?? m?.BackgroundTasks ?? (() => null)) as ComponentType<{ limit?: number }> };
});


export default function Home() {
  const route = useRoute();
  const app = useAppState();
  const person = app.person;
  const stored = useExampleWeek();
  const story = route.query.get("story") ? parseStory(route.query.get("story")) : stored;
  const [gone, setGone] = useState<ReadonlySet<string>>(new Set());
  const w = useLoad(() => loadWorker(person, story), [person, story]);
  const rep = useLoad(() => loadRepeats(7), []);
  const queue = useLoad(() => api.queue("pending"), []);
  // The live coach: while a step is active, one quiet row opens the coaching page. Asked again every 15 seconds and when the window comes back; a failure
  // (no engine, no active task) is simply no row.
  const coach = useLoad(() => api.coach(person ?? undefined), [person]);
  const reloadCoach = useRef(coach.reload);
  reloadCoach.current = coach.reload;
  useEffect(() => {
    const again = () => reloadCoach.current();
    const t = window.setInterval(again, 15_000);
    window.addEventListener("focus", again);
    return () => { window.clearInterval(t); window.removeEventListener("focus", again); };
  }, []);
  const [coachGrace, setCoachGrace] = useState(false);
  useEffect(() => { const t = window.setTimeout(() => setCoachGrace(true), 1500); return () => window.clearTimeout(t); }, []);
  const coachSettled = coach.status !== "loading" || coachGrace;
  useEffect(() => { document.title = "Home · Knack"; }, []);
  useEffect(() => setGone(new Set()), [story, person]);

  const onGone = useCallback((id: string) => setGone((g) => new Set([...g, id])), []);
  const retry = useCallback(() => { forgetBackoff(); window.dispatchEvent(new Event("understudy:retry")); w.reload(); }, [w]);
  const decided = useCallback(() => { queue.reload(); void refreshNeedsBadge(); }, [queue]);

  const data = w.data;
  const pointers = useMemo(() => (data ? (data.pointers ?? []).filter((p) => p && !gone.has(p.id) && typeof p.headline === "string" && p.headline.trim() !== "") : []), [data, gone]);
  const pending = (queue.data ?? []).filter((x) => x.status === "pending");
  const blocking = blockingItem(pending);

  // Tell the voice conversation which insight is the hero (an id and the template it was built from, nothing else). An approval, a quiet week or a loading screen has none.
  const heroPointer = !blocking && pointers.length > 0 ? pointers[0] : null;
  useEffect(() => { reportInsight(heroPointer?.id ?? null, heroPointer?.kind ?? null); }, [heroPointer?.id, heroPointer?.kind]);

  if (w.status === "error" && !data) return <div className="page page--read home"><QuietState q={COULD_NOT_LOAD} onRetry={w.reload} /></div>;
  if (!data) return <Reading />;

  const status = pointers.length === 0 && data.status === "ok" ? "nothing_stands_out" : data.status;
  const quiet = pointers.length === 0 ? quietFor(status, { setUp: !!app.role || !!person }) : null;
  const date = weekOf(data.week);

  const [first, second] = pointers;
  const action = first ? heroAction(first) : null;
  const toTry = tryLine(data.try);
  const needs = needsLine(remainingAfter(Math.max(app.pendingQueue, pending.length), !!blocking));
  const repeats = rep.data && rep.data.state === "ok" ? rep.data.total : null;
  const rLine = repeatsRow(repeats);

  // At most two quiet rows, in order of claim: the coaching row while a step is active, the pointer an approval displaced, what needs you, the next pointer, then the best of Repeats and Growth.
  const candidates: ReactNode[] = [];
  // Only a live answer counts: with no engine the coach state is an example, and an example is not a step anyone is coaching.
  const coaching = coach.source === "live" ? coachLine(coach.data?.task, coach.data?.active) : null;
  if (coaching) candidates.push(<Row key="coach" href="#/today" icon="coach">{coaching}</Row>);
  if (blocking && first) candidates.push(<Row key="first" href={action?.href ?? "#/growth"} icon="growth">{rowSentence(first.headline)}</Row>);
  if (needs) candidates.push(<Row key="needs" href="#/needs-you" icon="needs-you">{needs}</Row>);
  if (second) candidates.push(<Row key="second" href={heroAction(second)?.href ?? "#/growth"} icon="growth">{rowSentence(second.headline)}</Row>);
  if (rLine) candidates.push(<Row key="repeats" href="#/routines?tab=could-automate" icon="routines" hint={{ label: "About the repeated time", text: repeatsHint(repeats) ?? "" }}>{rLine}</Row>);
  if (pointers.length > 0) candidates.push(<Row key="growth" href="#/growth" icon="growth">{GROWTH_ROW}</Row>);
  // The quiet rows wait for the coach's answer (at most a second and a half), so a late "Coaching you on..." row does not take the place of one already drawn.
  const rows = coachSettled ? candidates.slice(0, 2) : [];

  return (
    <div className="page page--read home" aria-busy={w.status === "loading"}>
      {/* Above everything, when there are any: what is running for the worker, three lines at most. */}
      <Suspense fallback={null}><BackgroundTasks limit={3} /></Suspense>
      <div className="home__meta">
        <span>{date ?? "This week"}</span>
      </div>

      {blocking ? <ApprovalHero item={blocking} onDone={decided} /> : quiet ? <QuietState q={quiet} onRetry={retry} /> : first && (
        <section className="home__hero" aria-labelledby="home-hero">
          <h1 id="home-hero" className="home__hero-text hero-insight" dir="auto">{heroSentence(first.headline)}</h1>
          {toTry && <p className="home__why">{toTry}</p>}
          <div className="home__actions">
            {action && <a className="btn btn--primary" href={action.href}>{action.label}</a>}
            {first.details_available && <WhyThis p={first} person={person} onGone={onGone} />}
          </div>
        </section>
      )}

      <TaskBox role={app.role} />

      {rows.length > 0 && <ul className="home__rows">{rows}</ul>}
    </div>
  );
}
