import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { prefersReducedMotion, useLoad, useWidth } from "../hooks";
import { ChartFoot, EmptyState, ErrorState, Loading, OriginBadge, PageHead } from "../components/common";
import { useToast } from "../components/Toasts";
import { NODE_COLOUR, NODE_LABEL, layoutGraph, nodeOpacity, placeLabels, radiusFn, type Placed } from "../lib/graph";
import { findLine, replaceLineText } from "../lib/memory";
import { fmtDate } from "../lib/format";
import type { WorkGraph, WorkNode, WorkNodeType } from "../types";

/** Tween node positions between layouts so a merge or a deletion slides instead of jumping. */
function useTweened(target: Placed[], ms: number): Placed[] {
  const [pos, setPos] = useState<Placed[]>(target);
  const from = useRef<Placed[]>(target);
  const raf = useRef(0);
  useEffect(() => {
    cancelAnimationFrame(raf.current);
    const start = performance.now();
    const a = new Map(from.current.map((p) => [p.id, p]));
    if (prefersReducedMotion() || ms <= 0) { from.current = target; setPos(target); return; }
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const next = target.map((p) => { const q = a.get(p.id) ?? p; return { id: p.id, r: p.r, x: q.x + (p.x - q.x) * e, y: q.y + (p.y - q.y) * e }; });
      from.current = next;
      setPos(next);
      if (t < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, ms]);
  return pos;
}

function hex(r: number): string {
  return Array.from({ length: 6 }, (_, i) => { const a = (Math.PI / 3) * i + Math.PI / 6; return `${Math.cos(a) * r * 1.12},${Math.sin(a) * r * 1.12}`; }).join(" ");
}

function Shape({ type, r }: { type: WorkNodeType; r: number }) {
  const fill = NODE_COLOUR[type];
  if (type === "memory") return <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={2} style={{ fill }} />;
  if (type === "automation") return <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={2} transform="rotate(45)" style={{ fill }} />;
  if (type === "skill") return <polygon points={hex(r)} style={{ fill }} />;
  return <circle r={r} style={{ fill }} />;
}

function capsule(ax: number, ay: number, bx: number, by: number, R: number): string {
  const dx = bx - ax, dy = by - ay;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;
  const p = (x: number, y: number, s: number) => `${x + nx * R * s},${y + ny * R * s}`;
  return `M${p(ax, ay, 1)} L${p(bx, by, 1)} A${R},${R} 0 0 0 ${p(bx, by, -1)} L${p(ax, ay, -1)} A${R},${R} 0 0 0 ${p(ax, ay, 1)} Z`;
}

export default function Graph() {
  const g = useLoad(() => api.workGraph(), []);
  const [sel, setSel] = useState<string | null>(null);
  const [box, width] = useWidth<HTMLDivElement>();
  const [combine, setCombine] = useState(false);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const a = window.setTimeout(() => setShown(true), 60);
    const b = window.setTimeout(() => setCombine(true), prefersReducedMotion() ? 0 : 900);
    return () => { window.clearTimeout(a); window.clearTimeout(b); };
  }, []);

  const height = width && width < 560 ? 720 : Math.max(440, Math.min(660, Math.round(width * 0.58)));
  const target = useMemo(() => (g.data && width ? layoutGraph(g.data, width, height, combine) : []), [g.data, width, height, combine]);
  const pos = useTweened(target, 1100);

  if (g.status === "error" && !g.data) return <div className="page"><ErrorState error={g.error} retry={g.reload} what="the work graph" /></div>;
  if (!g.data) return <div className="page"><Loading label="Loading the work graph" /></div>;
  const graph = g.data;
  const at = new Map(pos.map((p) => [p.id, p]));
  const radius = radiusFn(graph.nodes);
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const narrowCanvas = width < 560;
  const maxChars = narrowCanvas ? 24 : 34;
  const labelText = (n: WorkNode) => (n.label.length > maxChars ? `${n.label.slice(0, maxChars - 1)}…` : n.label);
  // Labels are placed once per layout (on the settled positions), then ride along with their node while it moves.
  const labels = placeLabels(target.map((p) => { const n = byId.get(p.id); return { id: p.id, x: p.x, y: p.y, r: p.r, text: n ? labelText(n) : "", priority: n ? n.strength + (n.type === "routine" ? 0.3 : 0) : 0 }; }), width, height, sel);
  const node = sel ? byId.get(sel) ?? null : null;
  const faded = graph.nodes.filter((n) => n.strength < 0.4).length;

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow="Graph"
        title="How your work connects"
        lede={`${graph.nodes.length} things Understudy knows about your work. Related ones are linked, routines that always run together join up, and anything you stop using fades${faded ? ` (${faded} fading now)` : ""}.`}
        aside={<OriginBadge meta={g.meta} />}
      />

      {graph.nodes.length === 0 ? (
        <EmptyState title="Nothing here yet" body="The graph fills in as Understudy sees your routines, skills and the notes you keep. Finish set-up first, then come back." action={<a className="btn btn--secondary" href="#/onboarding">Go to set-up</a>} />
      ) : (
        <div className="stack">
          <div className="gcanvas__stage" ref={box} style={{ height }}>
            {width > 0 && (
              <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" aria-label={`Work graph with ${graph.nodes.length} nodes. Use Tab to move between nodes and Enter to open one.`}>
                {combine && graph.links.filter((l) => l.kind === "combined").map((l) => {
                  const a = at.get(l.a), b = at.get(l.b);
                  if (!a || !b) return null;
                  return <path key={`h${l.a}${l.b}`} className="ghull" d={capsule(a.x, a.y, b.x, b.y, Math.max(a.r, b.r) + 12)} style={{ opacity: 0.8 }} />;
                })}
                {graph.links.map((l) => {
                  const a = at.get(l.a), b = at.get(l.b), na = byId.get(l.a), nb = byId.get(l.b);
                  if (!a || !b || !na || !nb) return null;
                  const o = shown ? 0.2 + 0.6 * Math.min(na.strength, nb.strength) : 0;
                  return <line key={`${l.a}-${l.b}`} className={`glink${l.kind === "combined" ? " glink--combined" : ""}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={0.8 + l.weight * 1.8} style={{ opacity: o }} />;
                })}
                {graph.nodes.map((n) => {
                  const p = at.get(n.id);
                  if (!p) return null;
                  const r = radius(n);
                  const op = shown ? nodeOpacity(n.strength) : 0;
                  return (
                    <g key={n.id} className="gnode" transform={`translate(${p.x},${p.y})`} data-sel={sel === n.id} tabIndex={0} role="button"
                      aria-label={`${NODE_LABEL[n.type]}: ${n.label}. Strength ${Math.round(n.strength * 100)} percent.`} aria-pressed={sel === n.id}
                      onClick={() => setSel(n.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(n.id); } }}>
                      <g className="gnode__body" style={{ opacity: op }}><Shape type={n.type} r={r} /></g>
                      <circle className="gnode__ring" r={r + 6} />
                      <title>{n.label}</title>
                      {(() => { const lp = labels.get(n.id); return lp && !lp.hidden ? <text className="gnode__label" x={lp.dx} y={lp.dy} textAnchor={lp.anchor} style={{ opacity: shown ? Math.max(0.7, op) : 0 }}>{labelText(n)}</text> : null; })()}
                    </g>
                  );
                })}
              </svg>
            )}
            {node && (
              <aside className="gpanel" aria-label="Node details">
                <NodePanel key={node.id} node={node} onClose={() => setSel(null)} onChanged={() => { setSel(null); g.reload(); }} graph={graph} />
              </aside>
            )}
          </div>
          <Legend />
          <ChartFoot meta={g.meta} extra={<span>click a node for why it exists · layout is for reading only</span>} />
        </div>
      )}
    </div>
  );
}

function Legend() {
  const glyph = (type: WorkNodeType) => (
    <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true"><Shape type={type} r={5.5} /></svg>
  );
  return (
    <ul className="legend" aria-label="How to read the graph">
      {(["routine", "skill", "memory", "automation"] as WorkNodeType[]).map((t) => <li key={t} className="legend__item">{glyph(t)}{NODE_LABEL[t]}</li>)}
      <li className="legend__item"><span className="sw sw--muted" style={{ width: 10, height: 10, borderRadius: "50%" }} />Size: minutes a week (routines, automations) or mastery (skills)</li>
      <li className="legend__item"><span className="sw" style={{ background: "linear-gradient(90deg, var(--muted), transparent)" }} />Fainter: weaker, fades with disuse</li>
      <li className="legend__item"><span className="sw sw--line sw--muted" />Linked</li>
      <li className="legend__item"><span className="sw sw--dashed sw--accent" />Capsule: always run together</li>
    </ul>
  );
}

function NodePanel({ node: n, graph, onClose, onChanged }: { node: WorkNode; graph: WorkGraph; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const mem = useLoad(() => api.memory(), []);
  const line = mem.data && n.memory_line_id ? findLine(mem.data.sections, n.memory_line_id) : null;
  const [text, setText] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const current = text ?? line?.line.text ?? "";
  const days = Math.max(0, Math.round((Date.now() - new Date(n.last_seen).getTime()) / 86_400_000));
  const linked = graph.links.filter((l) => l.a === n.id || l.b === n.id).map((l) => graph.nodes.find((x) => x.id === (l.a === n.id ? l.b : l.a))?.label).filter(Boolean);

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

  return (
    <div className="sidepanel">
      <div className="sidepanel__head">
        <div className="stack" style={{ gap: "var(--space-2)" }}>
          <span className="t-label" style={{ color: NODE_COLOUR[n.type] }}>{NODE_LABEL[n.type]}</span>
          <h2 className="sidepanel__title">{n.label}</h2>
        </div>
        <button type="button" className="btn btn--quiet btn--sm" onClick={onClose} aria-label="Close details">Close</button>
      </div>
      <div className="sidepanel__body">
        <div className="stack" style={{ gap: "var(--space-1)" }}><span className="t-label">Why it exists</span><p>{n.why}</p></div>
        <div className="stack" style={{ gap: "var(--space-1)" }}>
          <span className="t-label">Strength</span>
          <div className="mastery__track" aria-hidden="true"><i style={{ width: `${n.strength * 100}%`, background: NODE_COLOUR[n.type] }} /></div>
          <p className="note">{Math.round(n.strength * 100)}%. Last seen {fmtDate(n.last_seen)}{days > 0 ? `, ${days} ${days === 1 ? "day" : "days"} ago` : ""}. Strength fades with disuse and returns when you use it.</p>
        </div>
        {linked.length > 0 && <div className="stack" style={{ gap: "var(--space-1)" }}><span className="t-label">Linked to</span><p className="note">{linked.join(", ")}</p></div>}
        {n.editable && line && (
          <div className="field">
            <label className="field__label" htmlFor="node-edit">Edit this line in your memory file</label>
            <textarea id="node-edit" className="textarea" rows={3} value={current} onChange={(e) => setText(e.target.value)} />
            <div className="row"><button type="button" className="btn btn--secondary btn--sm" disabled={busy || !text || text.trim() === line.line.text} onClick={save}>Save</button></div>
          </div>
        )}
        {(n.type === "routine" || n.type === "automation") && <p className="note"><a href="#/routines">Open this in Routines</a> to change what it may do.</p>}
        {!n.editable && <p className="lock-note">This one is kept by Understudy and cannot be edited by hand.</p>}
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
