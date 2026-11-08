// Home: one sentence about the week, one action, at most two quiet rows (docs/knack-ux/01-home.md). No chart, no statistic, no paragraph.
// A blocking approval or a safety pause takes the hero slot. Everything the old Your week showed beyond this moved: the Monday note to the
// palette, "What your admin can see" to Your data, the example-week selector to Settings, the data mode to the sidebar's status line.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, forgetBackoff, refreshQueueBadge } from "../../api";
import { useRoute } from "../../router";
import { useAppState } from "../../store";
import { useLoad } from "../../hooks";
import { ApprovalHero } from "../../components/home/ApprovalHero";
import { WhyThis } from "../../components/home/PointerCard";
import { Hint } from "../../components/Hint";
import { Icon } from "../../components/shell/icons";
import { FIRST_RUN_KEY } from "../FirstRun/model";
import { loadRepeats } from "../Repeats/data";
import { loadWorker, parseStory } from "./data";
import { blockingItem, remainingAfter } from "./approval";
import { COULD_NOT_LOAD, GROWTH_ROW, exampleLine, heroAction, heroSentence, needsLine, originBadge, quietFor, repeatsHint, repeatsRow, rowSentence, tryLine, weekOf, type Quiet } from "./model";
import { useExampleWeek } from "./story";
import "../../components/home/home.css";

function Row({ href, icon, children, hint }: { href: string; icon: "needs-you" | "routines" | "growth"; children: string; hint?: { label: string; text: string } | null }) {
  return (
    <li className="home__row">
      <a className="home__row-link" href={href}>
        <Icon name={icon} />
        <span className="home__row-text">{children}</span>
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

const firstRunAt = (): string | null => { try { return window.localStorage.getItem(FIRST_RUN_KEY); } catch { return null; } };

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
  useEffect(() => { document.title = "Home · Knack"; }, []);
  useEffect(() => setGone(new Set()), [story, person]);

  const onGone = useCallback((id: string) => setGone((g) => new Set([...g, id])), []);
  const retry = useCallback(() => { forgetBackoff(); window.dispatchEvent(new Event("understudy:retry")); w.reload(); }, [w]);
  const decided = useCallback(() => { queue.reload(); void refreshQueueBadge(); }, [queue]);

  const data = w.data;
  const pointers = useMemo(() => (data ? data.pointers.filter((p) => !gone.has(p.id)) : []), [data, gone]);
  const pending = (queue.data ?? []).filter((x) => x.status === "pending");
  const blocking = blockingItem(pending);

  if (w.status === "error" && !data) return <div className="page page--read home"><QuietState q={COULD_NOT_LOAD} onRetry={w.reload} /></div>;
  if (!data) return <Reading />;

  const example = w.source === "demo";
  const status = pointers.length === 0 && data.status === "ok" ? "nothing_stands_out" : data.status;
  const quiet = pointers.length === 0 ? quietFor(status, { setUp: !!app.role || !!person }) : null;
  const badge = originBadge({ example, origin: w.meta?.origin, badge: (w.meta as { badge?: string } | null)?.badge });
  const date = weekOf(data.week);
  const standInNote = data.stand_in ? ((w.meta as { note?: string } | null)?.note ?? "An example week from the synthetic firm stands in for this profile.") : null;

  const [first, second] = pointers;
  const action = first ? heroAction(first) : null;
  const toTry = tryLine(data.try) ?? exampleLine(data.stand_in, firstRunAt());
  const needs = needsLine(remainingAfter(pending.length || app.pendingQueue, !!blocking));
  const repeats = rep.data && rep.data.state === "ok" ? rep.data.total : null;
  const rLine = repeatsRow(repeats);

  // At most two quiet rows, in order of claim: the pointer an approval displaced, what needs you, the next pointer, then the best of Repeats and Growth.
  const candidates: ReactNode[] = [];
  if (blocking && first) candidates.push(<Row key="first" href={action?.href ?? "#/growth"} icon="growth">{rowSentence(first.headline)}</Row>);
  if (needs) candidates.push(<Row key="needs" href="#/needs-you" icon="needs-you">{needs}</Row>);
  if (second) candidates.push(<Row key="second" href={heroAction(second)?.href ?? "#/growth"} icon="growth">{rowSentence(second.headline)}</Row>);
  if (rLine) candidates.push(<Row key="repeats" href="#/routines?tab=could-automate" icon="routines" hint={{ label: "About the repeated time", text: repeatsHint(repeats) ?? "" }}>{rLine}</Row>);
  if (pointers.length > 0) candidates.push(<Row key="growth" href="#/growth" icon="growth">{GROWTH_ROW}</Row>);
  const rows = candidates.slice(0, 2);

  return (
    <div className="page page--read home" aria-busy={w.status === "loading"}>
      <div className="home__meta">
        <span>{date ?? "This week"}</span>
        {badge && <span className="pill pill--origin" data-origin={example ? "example" : w.meta?.origin ?? "synthetic"}>{badge}</span>}
      </div>

      {blocking ? <ApprovalHero item={blocking} onDone={decided} /> : quiet ? <QuietState q={quiet} onRetry={retry} /> : first && (
        <section className="home__hero" aria-labelledby="home-hero">
          <h1 id="home-hero" className="home__hero-text hero-insight">{heroSentence(first.headline)}</h1>
          {toTry && <p className="home__why">{toTry}</p>}
          <div className="home__actions">
            {action && <a className="btn btn--primary" href={action.href}>{action.label}</a>}
            {first.details_available && <WhyThis p={first} person={person} note={standInNote} onGone={onGone} />}
          </div>
        </section>
      )}

      {rows.length > 0 && <ul className="home__rows">{rows}</ul>}
    </div>
  );
}
