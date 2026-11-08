// What opens when a node is clicked, tapped or entered: the insight first (what this is, in one line; why it exists, in one line), the numbers
// behind a closed disclosure, then the few things the worker can do with it. The names of the actions are the old ones, so a worker who knew them still does.
import { useState } from "react";
import { ApiError, api } from "../../api";
import { useLoad } from "../../hooks";
import { firstSentence, isLapsed } from "../../lib/graph";
import { fmtDate } from "../../lib/format";
import { findLine, replaceLineText } from "../../lib/memory";
import { NODE_BLURB, NODE_NAME } from "../../lib/nodeIcons";
import type { WorkGraph, WorkNode } from "../../types";
import { Hint } from "../Hint";
import { useToast } from "../Toasts";
import { Details } from "../ui";
import { KindChip } from "./Glyph";

const REASON_WORDS = 24;

export function NodePanel({ node: n, graph, onClose, onChanged }: { node: WorkNode; graph: WorkGraph; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const mem = useLoad(() => api.memory(), []);
  const line = mem.data && n.memory_line_id ? findLine(mem.data.sections, n.memory_line_id) : null;
  const [text, setText] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const current = text ?? line?.line.text ?? "";
  const days = Math.max(0, Math.round((Date.now() - new Date(n.last_seen).getTime()) / 86_400_000));
  const names = new Map(graph.nodes.map((x) => [x.id, x.label]));
  const linked = graph.links.filter((l) => l.a === n.id || l.b === n.id).map((l) => names.get(l.a === n.id ? l.b : l.a)).filter((x): x is string => !!x);
  const reason = firstSentence(n.why, REASON_WORDS);
  const pct = Math.round(Math.min(1, Math.max(0, n.strength)) * 100);

  const save = async () => {
    if (!mem.data || !line) return;
    setBusy(true); setErr(null);
    try {
      const md = replaceLineText(mem.data.markdown, line.line.text, current.trim());
      if (!md) throw new ApiError(409, "line_moved", "That line is not in the file any more. Reload the page and try again.");
      await api.putMemory(md, mem.data.revision);
      toast({ tone: "success", text: "Saved to your memory file.", detail: current.trim() });
      onChanged();
    } catch (e) { setErr(e instanceof ApiError ? (e.status === 409 ? "The memory file changed while you were editing. Reload this screen and try again; your text is not lost until you leave." : e.message) : "Could not save. Try again."); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true); setErr(null);
    try {
      await api.deleteWorkNode(n);
      toast({ tone: "success", text: n.type === "memory" || n.memory_line_id ? "Removed from your memory file." : "Turned off for good.", detail: n.label });
      onChanged();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not remove it. Try again."); }
    finally { setBusy(false); setConfirm(false); }
  };
  const removeLabel = n.type === "memory" ? "Forget this line" : n.type === "skill" ? "Forget this skill" : "Never for this";
  const size = n.type === "routine" || n.type === "automation" ? `about ${Math.round(n.size)} min a week` : n.type === "skill" && n.size >= 0 && n.size <= 1 ? `mastery ${Math.round(n.size * 100)}%` : null;

  return (
    <div className="sidepanel">
      <div className="sidepanel__head">
        <div className="gpanel__who">
          <KindChip kind={n.type} size={28} />
          <div className="stack" style={{ gap: "var(--space-1)" }}>
            <span className="t-label">{NODE_NAME[n.type]}</span>
            <h2 className="sidepanel__title">{n.label}</h2>
          </div>
        </div>
        <button type="button" className="btn btn--quiet btn--sm" onClick={onClose} aria-label="Close details">Close</button>
      </div>
      <div className="sidepanel__body">
        <p className="gpanel__what">{NODE_BLURB[n.type]}</p>
        <div className="stack" style={{ gap: "var(--space-1)" }}><span className="t-label">Why it exists</span><p>{reason}</p></div>
        <Details summary="The numbers">
          <dl className="gpanel__nums">
            <div><dt>Strength</dt><dd><span className="num">{pct}%</span>{isLapsed(n) ? ", fading" : ""}<Hint label="About strength">Strength fades with disuse and returns when you use it.</Hint></dd></div>
            <div><dt>Last seen</dt><dd>{fmtDate(n.last_seen)}{days > 0 ? `, ${days} ${days === 1 ? "day" : "days"} ago` : ""}</dd></div>
            {size && <div><dt>Size</dt><dd>{size}</dd></div>}
            {linked.length > 0 && <div><dt>Linked to</dt><dd>{linked.join(", ")}</dd></div>}
            {reason !== n.why.trim() && <div><dt>In full</dt><dd>{n.why}</dd></div>}
          </dl>
        </Details>
        {n.editable && line && (editing ? (
          <div className="field">
            <label className="field__label" htmlFor="node-edit">Edit this line in your memory file</label>
            <textarea id="node-edit" className="textarea" rows={3} value={current} onChange={(e) => setText(e.target.value)} autoFocus />
            <div className="row">
              <button type="button" className="btn btn--secondary btn--sm" disabled={busy || !text || text.trim() === line.line.text} onClick={save}>Save</button>
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => { setEditing(false); setText(null); }}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="row"><button type="button" className="btn btn--secondary btn--sm" onClick={() => setEditing(true)}>Edit this line</button></div>
        ))}
        {(n.type === "routine" || n.type === "automation") && <p className="note"><a href="#/routines">Open this in Routines</a> to change what it may do.</p>}
        {!n.editable && <p className="lock-note">This one is kept by Knack and cannot be edited by hand.</p>}
        {err && <p className="field__error" role="alert">{err}</p>}
      </div>
      {n.editable && (
        <div className="sidepanel__foot">
          {confirm ? (
            <>
              <p className="note" style={{ flexBasis: "100%" }}>{n.type === "memory" || n.memory_line_id ? "This removes the line from your memory file and from what the system does." : "This turns the routine off and stops it being suggested again."}</p>
              <button type="button" className="btn btn--danger btn--sm" disabled={busy} onClick={remove}>{busy ? "Working" : "Yes, remove"}</button>
              <button type="button" className="btn btn--secondary btn--sm" onClick={() => setConfirm(false)}>Keep it</button>
            </>
          ) : (
            <button type="button" className="btn btn--danger btn--sm" onClick={() => setConfirm(true)}>{removeLabel}</button>
          )}
        </div>
      )}
    </div>
  );
}
