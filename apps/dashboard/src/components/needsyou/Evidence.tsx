import { useState } from "react";
import { ENGINE_URL } from "../../api";
import { useAppState } from "../../store";
import { plainWords } from "../../screens/NeedsYou/model";
import { TierPill } from "../common";
import type { QueueItem } from "../../types";

/** Screenshots come from the engine (GET /runs/{run_id}/{file}). When it is not serving them, a labelled placeholder stays. */
function Shot({ runId, path }: { runId: string; path: string }) {
  const live = useAppState().live > 0;
  const [failed, setFailed] = useState(false);
  const file = path.split("/").pop() ?? path;
  if (!live || failed) return <span className="shot">{file}<br />{live ? "could not load" : "not available in example data"}</span>;
  return <img className="shot shot--img" src={`${ENGINE_URL}/runs/${encodeURIComponent(runId)}/${encodeURIComponent(file)}`} alt={`Screenshot ${file} from run ${runId}`} loading="lazy" onError={() => setFailed(true)} />;
}

/** What the run found against what was expected, the steps and the screenshots: opened on demand, printed in full once opened. */
export function Evidence({ item: it, rest }: { item: QueueItem; rest?: string }) {
  const diff = (it.evidence.diff ?? []) as { field: string; expected: string; got: string }[];
  const keys = Array.from(new Set([...Object.keys(it.evidence.extracted ?? {}), ...Object.keys(it.evidence.expected ?? {})]));
  return (
    <div className="kc-panel" data-testid="evidence">
      {rest && <p>{rest}</p>}
      <p className="kc-sub">Run {it.run_id}{it.routine_id ? ` · ${it.routine_id}` : ""}</p>
      {it.evidence.screenshots.length > 0 && (
        <div className="shots" aria-label="Screenshots">
          {it.evidence.screenshots.map((s, i) => <Shot key={`${s}-${i}`} runId={it.run_id} path={s} />)}
        </div>
      )}
      {keys.length > 0 && (
        <div className="kv" role="table" aria-label="What the run found against what was expected">
          <span className="t-label">Field</span><span className="t-label">Found</span><span className="t-label">Expected</span>
          {keys.map((k) => {
            const got = String(it.evidence.extracted?.[k] ?? "");
            const exp = it.evidence.expected?.[k];
            const bad = exp != null && String(exp) !== got;
            return (<span key={k} style={{ display: "contents" }}><span className="kv__k">{k}</span><span className={bad ? "kv__bad" : ""}>{got || "none"}</span><span>{exp != null ? String(exp) : "not set"}</span></span>);
          })}
        </div>
      )}
      {diff.length > 0 && <p><b>Difference:</b> {plainWords(diff.map((d) => `${d.field}: expected ${d.expected}, got ${d.got}`).join("; "))}</p>}
      {it.evidence.tier_log.length > 0 && (
        <div className="row" aria-label="Which method ran each step">{it.evidence.tier_log.map((t, i) => <TierPill key={`${t.step}-${i}`} tier={t.tier} step={t.step} />)}</div>
      )}
    </div>
  );
}
