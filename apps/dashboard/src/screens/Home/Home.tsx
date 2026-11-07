import { useCallback, useEffect, useMemo, useState } from "react";
import { useRoute } from "../../router";
import { useAppState } from "../../store";
import { idle, useLoad } from "../../hooks";
import { ErrorState, ExampleBadge, Loading, PageHead, SourceNote } from "../../components/common";
import { Details } from "../../components/ui";
import { Hint } from "../../components/Hint";
import { PointerCard } from "../../components/home/PointerCard";
import { SharingPanel } from "../../components/home/SharingPanel";
import { copyText, mondayNote, noteLines } from "../../components/home/monday";
import type { WireSharing, WireWorker } from "../../components/firm/wire";
import { loadRepeats } from "../Repeats/data";
import { WORKER_STORIES, STORY_LABEL, loadSharing, loadWorker, parseStory, type WorkerStory } from "./data";
import { homeTitle, quietBody, repeatsLine, weekLabel } from "./model";
import "../../components/home/home.css";

/** The Monday note: three pointers and one number to try, in plain text the worker can copy. A disclosure, so the page keeps one hero. */
function MondayNote({ w }: { w: WireWorker }) {
  const note = mondayNote(w);
  const [copied, setCopied] = useState<"idle" | "yes" | "no">("idle");
  if (!note) return null;
  const copy = async () => { setCopied((await copyText(note)) ? "yes" : "no"); window.setTimeout(() => setCopied("idle"), 3000); };
  return (
    <div className="home__monday">
      <Details summary="Your Monday note">
        <ul className="home__note">{noteLines(note).map((l) => <li key={l}>{l}</li>)}</ul>
      </Details>
      <button type="button" className="btn btn--quiet btn--sm" onClick={copy}>Copy the note</button>
      <span className="u-sr-only" role="status">{copied === "yes" ? "Copied." : copied === "no" ? "Could not copy." : ""}</span>
      {copied === "yes" && <span className="home__said" aria-hidden="true">Copied</span>}
      {copied === "no" && <span className="home__said" aria-hidden="true">Your browser blocked copying. Select the text instead.</span>}
    </div>
  );
}

/** What an admin can see about this worker. Read when opened. A read-only list, never a toggle. */
function AdminCanSee({ person }: { person: string | null }) {
  const [open, setOpen] = useState(false);
  const s = useLoad(() => (open ? loadSharing(person) : idle<WireSharing>()), [open, person]);
  return (
    <Details summary="What your admin can see" onToggle={setOpen} wide>
      {open && s.status === "loading" && !s.data && <p>Reading what is shared.</p>}
      {s.status === "error" && !s.data && <p>That could not be loaded. Nothing is shared that is not listed here.</p>}
      {s.data && <SharingPanel sharing={s.data} />}
    </Details>
  );
}

/** Your week: the first screen for a worker. A few pointers, chosen by fixed rules, each with one action and the reason behind it. */
export default function Home() {
  const route = useRoute();
  const person = useAppState().person;
  const [story, setStory] = useState<WorkerStory>(() => parseStory(route.query.get("story")));
  const [gone, setGone] = useState<ReadonlySet<string>>(new Set());
  const w = useLoad(() => loadWorker(person, story), [person, story]);
  const rep = useLoad(() => loadRepeats(7), []);
  useEffect(() => { document.title = "Your week · Understudy"; }, []);
  useEffect(() => setGone(new Set()), [story, person]);

  const onGone = useCallback((id: string) => setGone((g) => new Set([...g, id])), []);
  const data = w.data;
  const pointers = useMemo(() => (data ? data.pointers.filter((p) => !gone.has(p.id)) : []), [data, gone]);

  if (w.status === "error" && !data) return <div className="page page--read"><ErrorState error={w.error} retry={w.reload} what="your week" /></div>;
  if (!data) return <div className="page page--read"><Loading label="Loading your week" /></div>;

  const example = w.source === "demo";
  const status = pointers.length === 0 && data.status === "ok" ? "nothing_stands_out" : data.status;
  const label = weekLabel(data.week);
  const repeats = rep.data && rep.data.state === "ok" ? repeatsLine(rep.data.total) : null;
  const badge = (w.meta as { badge?: string } | null)?.badge ?? (w.meta?.origin ? (w.meta.origin === "real" ? null : `${w.meta.origin}`) : null);

  return (
    <div className="page page--read home" aria-busy={w.status === "loading"}>
      <PageHead
        eyebrow="Your week"
        title={homeTitle(status, pointers.length)}
        lede={label ? `${label}. Chosen by fixed rules, not by a model.` : "Chosen by fixed rules, not by a model."}
        aside={<>
          {badge && <span className="pill pill--origin" data-origin={w.meta?.origin ?? "synthetic"}>{badge}</span>}
          <ExampleBadge why={w.why} />
          {example && (
            <label className="home__story">
              <span className="home__story-label">Example week</span>
              <select className="select" value={story} onChange={(e) => setStory(e.target.value as WorkerStory)}>
                {WORKER_STORIES.map((k) => <option key={k} value={k}>{STORY_LABEL[k]}</option>)}
              </select>
            </label>
          )}
        </>}
      />

      <section className="hero" aria-labelledby="pointers-h">
        <h2 id="pointers-h" className="u-sr-only">Pointers for this week</h2>
        {pointers.length > 0 ? (
          <div className="home__cards">
            {pointers.map((p) => <PointerCard key={p.id} p={p} person={person} onGone={onGone} />)}
          </div>
        ) : (
          <div className="state home__quiet">
            <span className="state__mark" aria-hidden="true" />
            <h2 className="state__title">{homeTitle(status, 0)}</h2>
            <p className="state__body">{status === "ok" || status === "nothing_stands_out" ? (data.message ?? quietBody("nothing_stands_out")) : (data.message ?? quietBody(status))}</p>
            {status === "onboarding" && <a className="btn btn--secondary btn--sm state__action" href="#/onboarding">Choose a role</a>}
          </div>
        )}
        {data.stand_in && <p className="note">{(w.meta as { note?: string } | null)?.note ?? "An example week from the synthetic firm stands in for this profile."}</p>}
        <SourceNote why={w.why} />
      </section>

      <MondayNote w={{ ...data, pointers }} />

      <section aria-labelledby="go-h" className="home__go">
        <h2 id="go-h" className="u-sr-only">Where to next</h2>
        <ul className="home__links">
          <li>
            <a className="home__link" href="#/growth"><span className="home__link-title">Growth</span><span className="home__link-hint">How much less help you need over time</span></a>
          </li>
          <li>
            <a className="home__link" href="#/repeats">
              <span className="home__link-title">Repeats</span>
              <span className="home__link-hint">{repeats ? repeats.line : "What you do again and again"}</span>
            </a>
            {repeats && <Hint label="About the repeated time">{repeats.hint}</Hint>}
          </li>
        </ul>
      </section>

      <AdminCanSee person={person} />
    </div>
  );
}
