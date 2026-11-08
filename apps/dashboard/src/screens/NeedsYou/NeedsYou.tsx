import { useEffect, useMemo, useState } from "react";
import { AGENT_URL, api } from "../../api";
import { ErrorState, Loading } from "../../components/common";
import { useToast } from "../../components/Toasts";
import { ApprovalRow } from "../../components/needsyou/ApprovalRow";
import { AwayDetails } from "../../components/needsyou/AwayDetails";
import { OriginBadge, OriginDetails } from "../../components/needsyou/Origin";
import { PausedRow } from "../../components/needsyou/PausedRow";
import { TaskNeedRow } from "../../components/needsyou/TaskNeedRow";
import { PreparedRow } from "../../components/needsyou/PreparedRow";
import { ProposalRow } from "../../components/needsyou/ProposalRow";
import { RowList } from "../../components/needsyou/RowList";
import type { Decide } from "../../components/routines/types";
import { useLoad } from "../../hooks";
import { runActive } from "../../lib/agents";
import { useLive, useRegisteredStreams } from "../../lib/live";
import { useAppState, setState } from "../../store";
import "../../components/kc.css";
import "../../components/needsyou/needsyou.css";
import { DEMO_PERSON } from "./count";
import { PAGE_ROWS, awayLine, buildItems, madeLine, needsCount, needsHeadline, visibleItems, type NeedsItem } from "./model";

/**
 * Needs you: ONE list for everything that waits on the worker (approvals, practice runs that differed, routine proposals, prepared actions, paused runs).
 * Safety first, then what a job waits on, then the rest, newest first. A decision never costs an extra click to open: every row carries its own buttons.
 */
export default function NeedsYou() {
  const toast = useToast();
  const me = useAppState().person;
  const person = me ?? DEMO_PERSON;
  const q = useLoad(() => api.queue("all"), []);
  const rt = useLoad(() => api.routines(), []);
  const br = useLoad(() => api.briefing(person), [person]);
  const ag = useLoad(() => api.agentsRuns(me ?? undefined), [me]);
  const tk = useLoad(() => api.tasks(), []);
  const rep = useLoad(() => api.offhoursReport(), []);
  const audit = useLoad(() => api.audit(20), []);
  const [cap, setCap] = useState(0);   // 0: the default fold; otherwise how many rows are drawn
  const [made, setMade] = useState<{ title: string; text: string } | null>(null);
  const [gone, setGone] = useState<Record<string, true>>({});

  const items = useMemo(
    () => buildItems({ queue: q.data, routines: rt.data, cards: (br.data?.cards ?? []).filter((c) => !gone[c.id]), cardsAt: br.data?.generated_at, runs: ag.data, tasks: tk.source === "live" ? tk.data : null }),
    [q.data, rt.data, br.data, ag.data, tk.data, tk.source, gone],
  );
  const ready = !!q.data;
  const n = needsCount(items);
  // The badge in the sidebar counts the same list.
  useEffect(() => { if (ready) setState({ pendingQueue: n }); }, [ready, n]);

  const reload = () => { q.reload(); rt.reload(); br.reload(); ag.reload(); tk.reload(); rep.reload(); };
  // An approval that arrives, or a run that pauses or finishes, shows up by itself: every 2 s while a run is active, every 15 s otherwise, on focus.
  useLive(reload, !!ag.data?.some((r) => { try { return runActive(r); } catch { return false; } }) || !!tk.data?.some((x) => x?.state === "running" || x?.state === "planning"), useRegisteredStreams(), tk.source === "live" ? [`${AGENT_URL}/tasks/events`] : []);

  if (q.status === "error" && !q.data) return <div className="page page--read kc-page"><ErrorState error={q.error} retry={q.reload} what="what needs you" /></div>;
  if (!q.data) return <div className="page page--read kc-page"><Loading label="Loading what needs you" /></div>;

  const decide: Decide = async (routine, body, done) => {
    await api.setConsent(routine.id, body);
    toast({ tone: "success", text: done, detail: "You can change this any time in Routines." });
    reload();
  };

  // The one primary button goes to the first real approval. A pause for safety and a practice run that differed are choices of equal weight.
  const primaryKey = items.find((i) => i.kind === "approval" && i.queue.kind !== "injection_pause" && i.queue.kind !== "shadow_mismatch")?.key;
  const shown = visibleItems(items, cap > 0, cap);
  const node = (it: NeedsItem) => {
    switch (it.kind) {
      case "approval": return <ApprovalRow item={it.queue} cls={it.cls} primary={it.key === primaryKey} onDone={reload} />;
      case "proposal": return <ProposalRow routine={it.routine} onDecide={decide} />;
      case "prepared": return (
        <PreparedRow card={it.card} onChanged={reload}
          onFired={(f, title) => { setGone((g) => ({ ...g, [it.card.id]: true })); setMade({ title, text: madeLine(f) }); reload(); }}
          onDismissed={() => { setGone((g) => ({ ...g, [it.card.id]: true })); reload(); }} />
      );
      case "paused": return <PausedRow run={it.run} onDone={reload} />;
      case "task": return <TaskNeedRow row={it.task} onDone={reload} />;
    }
  };
  const away = awayLine(rep.data);
  const sources = [q, rt, br, ag];

  return (
    <div className="page page--read kc-page">
      <div className="kc-head">
        <h1 className="kc-title">Needs you</h1>
        <OriginBadge sources={sources} />
      </div>
      {items.length > 0 && <p className="kc-headline" data-testid="headline">{needsHeadline(items)}</p>}
      <OriginDetails sources={sources} />
      {made && <p className="note" role="status" data-testid="fired">{made.title}: {made.text}</p>}

      {items.length === 0 ? (
        <div className="kc-empty">
          <h2>Nothing needs you.</h2>
          <p>Knack asks when a step cannot be undone.</p>
        </div>
      ) : (
        <>
          <RowList label="Waiting for you" rows={shown.map((it) => ({ key: it.key, node: node(it) }))} />
          {items.length > shown.length && (
            <div><button type="button" className="btn btn--secondary btn--sm" onClick={() => setCap(cap === 0 && items.length <= PAGE_ROWS ? items.length : shown.length + PAGE_ROWS)}>
              {cap === 0 && items.length <= PAGE_ROWS ? `Show all ${items.length}` : `Show ${Math.min(PAGE_ROWS, items.length - shown.length)} more`}
            </button></div>
          )}
        </>
      )}

      {away && rep.data && <AwayDetails rep={rep.data} audit={audit.data} line={away} />}
    </div>
  );
}
