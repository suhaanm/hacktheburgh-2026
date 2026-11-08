import { useState } from "react";
import { ENGINE_URL } from "../../api";
import { useAppState } from "../../store";
import { plainWords } from "../../screens/NeedsYou/model";
import { TierPill } from "../common";
import { Details } from "../ui";
import type { QueueItem } from "../../types";
import { KV } from "./KV";

/** Screenshots come from the engine (GET /runs/{run_id}/{file}). When it is not serving them, a labelled placeholder stays. */
function Shot({ runId, path }: { runId: string; path: string }) {
  const live = useAppState().live > 0;
  const [failed, setFailed] = useState(false);
  const file = path.split("/").pop() ?? path;
  if (!live || failed) return <span className="shot">{file}<br />{live ? "could not load" : "not available in example data"}</span>;
  return <img className="shot shot--img" src={`${ENGINE_URL}/runs/${encodeURIComponent(runId)}/${encodeURIComponent(file)}`} alt={`Screenshot ${file} from run ${runId}`} loading="lazy" onError={() => setFailed(true)} />;
}

/** A short text from the engine as it is shown: the old name and codes mapped, and cut at a sane length so one runaway value cannot take the screen. */
const clip = (v: unknown, max = 240): string => { const s = plainWords(String(v ?? "")); return s.length > max ? `${s.slice(0, max)}…` : s; };

/**
 * What the worker needs to decide, opened on demand: when it started, which run, what the run found against what was expected (one row each, the
 * difference marked), the screenshots, and under one closed "More" the method that ran each step. At most one short paragraph: what the summary
 * did not already say. Every field may be missing: a missing field leaves out its row.
 */
export function Evidence({ item: it, rest, since }: { item: QueueItem; rest?: string; since?: string }) {
  const ev = it.evidence ?? { screenshots: [], extracted: {}, expected: {}, diff: [], tier_log: [] };
  const shots = Array.isArray(ev.screenshots) ? ev.screenshots : [];
  const tiers = Array.isArray(ev.tier_log) ? ev.tier_log : [];
  const diff = (Array.isArray(ev.diff) ? ev.diff : []) as { field: string; expected: string; got: string }[];
  const keys = Array.from(new Set([...Object.keys(ev.extracted ?? {}), ...Object.keys(ev.expected ?? {})]));
  return (
    <div className="kc-panel" data-testid="evidence">
      {rest && <p>{rest}</p>}
      <KV rows={[["Since", since], ["Run", it.run_id ? clip(it.run_id, 60) : null], ["Routine", it.routine_id ? clip(it.routine_id, 60) : null]]} label="About this item" />
      {shots.length > 0 && (
        <div className="shots" aria-label="Screenshots">
          {shots.map((s, i) => <Shot key={`${s}-${i}`} runId={it.run_id} path={String(s)} />)}
        </div>
      )}
      {keys.length > 0 ? (
        <div className="kv" role="table" aria-label="What the run found against what was expected">
          <span className="t-label">Field</span><span className="t-label">Found</span><span className="t-label">Expected</span>
          {keys.map((k) => {
            const got = String(ev.extracted?.[k] ?? "");
            const exp = ev.expected?.[k];
            const bad = exp != null && String(exp) !== got;
            return (<span key={k} style={{ display: "contents" }}><span className="kv__k">{clip(k, 60)}</span><span className={bad ? "kv__bad" : ""}>{got ? clip(got) : "none"}</span><span>{exp != null ? clip(exp) : "not set"}</span></span>);
          })}
        </div>
      ) : diff.length > 0 && (
        <KV rows={diff.map((d): [string, string] => [clip(d.field, 60), `expected ${clip(d.expected, 80)}, got ${clip(d.got, 80)}`])} label="Differences" />
      )}
      {tiers.length > 0 && (
        <Details summary="More">
          <div className="row" aria-label="Which method ran each step">{tiers.map((t, i) => <TierPill key={`${t.step}-${i}`} tier={t.tier} step={t.step} />)}</div>
        </Details>
      )}
    </div>
  );
}
