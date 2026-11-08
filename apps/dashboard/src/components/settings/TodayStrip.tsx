import { useEffect, useState } from "react";
import { ApiError, api } from "../../api";
import { STATE_WORD, needsYouLine, todayHeadline, todaySummary, whyLines } from "../../lib/attention";
import { plainWords } from "../../screens/NeedsYou/model";
import type { AttentionDigest } from "../../types";
import { Details } from "../ui";

/** "Why?" for one item that needs you: loaded the first time it is opened, in the engine's own fixed words (the old name and codes mapped to the worker's words). */
function WhyItem({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const [w, setW] = useState<{ reason: string; steps: { state: string; text: string }[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!open || w || err) return;
    api.attentionWhy(id).then((r) => setW(whyLines(r.data)), (e: unknown) => setErr(e instanceof ApiError ? e.message : "The reason could not be read."));
  }, [open, w, err, id]);
  return (
    <details className="notices__why" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Why?</summary>
      {err ? <p className="kc-sub">{err}</p> : !w ? <p className="kc-sub">Reading the reason.</p> : (
        <div style={{ display: "grid", gap: "var(--space-1)" }}>
          <p className="kc-sub">{plainWords(w.reason) || "No reason was recorded."}</p>
          {w.steps.length > 0 && <ol className="yd-plain">{w.steps.map((s, i) => <li key={i}><b>{s.state}</b>: {plainWords(s.text)}</li>)}</ol>}
        </div>
      )}
    </details>
  );
}

/**
 * Today, in Settings under Interruptions, Per kind: how many notices were shown, held and dropped, and why in the engine's fixed words, and each held item
 * that needs the worker with its own "Why?". Counts and fixed lines only: nothing from a screen, a page or a file ever passes through here.
 */
export function TodayStrip({ digest, budgetPerDay }: { digest: AttentionDigest; budgetPerDay: number }) {
  const t = todaySummary(digest.today, digest.today_detail);
  const items = digest.needs_you_items ?? [];
  return (
    <div className="st-group" data-testid="today-strip">
      <p className="kc-label">Today</p>
      <p className="kc-row__body" style={{ margin: 0 }}>{todayHeadline(t, digest.budget ?? { used: 0, per_day: budgetPerDay })}</p>
      {t.lines.length === 0 ? <p className="kc-sub">Nothing has been shown, held or dropped yet today.</p> : (
        <Details summary="Why each count" wide>
          <ul className="yd-plain" data-testid="today-detail">
            {t.lines.map((l) => <li key={`${l.state}:${l.code}`}><b className="tabular">{l.n} {STATE_WORD[l.state]}</b> {plainWords(l.text ?? "The engine sent only this count.")}</li>)}
          </ul>
        </Details>
      )}
      {items.length > 0 && (
        <ul className="yd-plain" aria-label="Needs you" data-testid="needs-you">
          {items.map((i) => <li key={`${i.type}:${i.id ?? ""}`}><b>{needsYouLine(i)}</b>{i.id ? <WhyItem id={i.id} /> : null}</li>)}
        </ul>
      )}
    </div>
  );
}
