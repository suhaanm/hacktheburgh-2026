import { useState } from "react";
import { ENGINE_URL } from "../../api";
import { useAppState } from "../../store";
import { arr, clip as cut } from "../../lib/safeText";
import { fieldName, plainWords } from "../../screens/NeedsYou/model";
import { TierPill } from "../common";
import { Details } from "../ui";
import type { QueueItem } from "../../types";
import { KV } from "./KV";

/** Screenshots come from the engine (GET /runs/{run_id}/{file}). When it is not serving them, a labelled placeholder stays. */
function Shot({ runId, path }: { runId: string; path: string }) {
  const live = useAppState().live > 0;
  const [failed, setFailed] = useState(false);
  const file = path.split("/").pop() ?? path;
  if (!live || failed) return <span className="shot">Screenshot<br />{live ? "could not load" : "not available"}</span>;
  return <img className="shot shot--img" src={`${ENGINE_URL}/runs/${encodeURIComponent(runId)}/${encodeURIComponent(file)}`} alt="Screenshot from the run" loading="lazy" onError={() => setFailed(true)} />;
}

/** A short text from the engine as it is shown: the old name and codes mapped, and cut at a sane length so one runaway value cannot take the screen. */
const clip = (v: unknown, max = 240): string => plainWords(cut(v, max));
/** How many field rows and method pills one item shows: a hundred fields is a list nobody reads, so the rest are counted. */
const FIELDS = 30;

/**
 * What the worker needs to decide, opened on demand: when it started, which run, what the run found against what was expected (one row each, the
 * difference marked), the screenshots, and under one closed "More" the method that ran each step. At most one short paragraph: what the summary
 * did not already say. Every field may be missing: a missing field leaves out its row.
 */
export function Evidence({ item: it, rest, since }: { item: QueueItem; rest?: string; since?: string }) {
  const ev = it.evidence ?? { screenshots: [], extracted: {}, expected: {}, diff: [], tier_log: [] };
  const shots = arr<unknown>(ev.screenshots).filter((x) => typeof x === "string" && x);
  const tiers = arr<{ step: number; tier: number }>(ev.tier_log).filter((t) => t && typeof t === "object");
  const diff = arr<{ field: string; expected: string; got: string }>(ev.diff).filter((d) => d && typeof d === "object");
  const allKeys = Array.from(new Set([...Object.keys(ev.extracted ?? {}), ...Object.keys(ev.expected ?? {})]));
  const keys = allKeys.slice(0, FIELDS);
  return (
    <div className="kc-panel" data-testid="evidence">
      {rest && <p>{rest}</p>}
      {/* A worker never sees a run id or a routine id (docs/knack-ux/views.md): when it started is the one fact that helps them decide. */}
      <KV rows={[["Since", since]]} label="About this item" />
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
            return (<span key={k} style={{ display: "contents" }}><span className="kv__k">{fieldName(clip(k, 60))}</span><span className={bad ? "kv__bad" : ""}>{got ? clip(got) : "none"}</span><span>{exp != null ? clip(exp) : "not set"}</span></span>);
          })}
        </div>
      ) : diff.length > 0 && (
        <KV rows={diff.slice(0, FIELDS).map((d): [string, string] => [fieldName(clip(d.field, 60)), `expected ${clip(d.expected, 80)}, got ${clip(d.got, 80)}`])} label="Differences" />
      )}
      {allKeys.length > keys.length && <p className="kc-sub" data-testid="fields-more">{allKeys.length - keys.length} more fields are in the run.</p>}
      {tiers.length > 0 && (
        <Details summary="More">
          <div className="row" aria-label="Which method ran each step">{tiers.slice(0, FIELDS).map((t, i) => <TierPill key={`${t.step}-${i}`} tier={t.tier} step={t.step} />)}</div>
        </Details>
      )}
    </div>
  );
}
