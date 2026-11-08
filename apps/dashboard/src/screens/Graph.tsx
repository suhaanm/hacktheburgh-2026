import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useLoad, useWidth } from "../hooks";
import { ChartFoot, EmptyState, ErrorState, Loading, OriginBadge, PageHead } from "../components/common";
import { GraphCanvas } from "../components/graph/GraphCanvas";
import { GraphLegend, WORK_LEGEND } from "../components/graph/GraphLegend";
import { NodePanel } from "../components/graph/NodePanel";
import { cleanGraph, isLapsed } from "../lib/graph";

/** The badge says where the data came from, in the worker's words: an example is an example (D57: the word "synthetic" is not on any screen). */
const originLabel = (origin: string): string => (origin === "real" ? "Real data" : origin === "mixed" ? "Some example data" : origin === "synthetic" ? "Example data" : "Not run");

/** The details panel's width (340) plus the gap to the stage edge, in px. The stylesheet's narrow breakpoint puts the panel under the canvas instead. */
const PANEL_ROOM = 352;
const NARROW = "(max-width: 880px)";

/** True while the viewport matches a media query. */
function useMedia(query: string): boolean {
  const [on, setOn] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(query).matches);
  useEffect(() => {
    const m = window.matchMedia?.(query);
    if (!m) return;
    const f = () => setOn(m.matches);
    f();
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, [query]);
  return on;
}

/** The canvas is as tall as the screen reads well; a crowded graph gets a little more room. */
function canvasHeight(width: number, count: number): number {
  if (count <= 3) return 300;
  const base = width && width < 560 ? 520 : Math.max(420, Math.min(640, Math.round(width * 0.55)));
  return base + Math.min(280, Math.round(Math.sqrt(Math.max(0, count - 40)) * 8));
}

export default function Graph() {
  const g = useLoad(() => api.workGraph(), []);
  const [sel, setSel] = useState<string | null>(null);
  const [box, width] = useWidth<HTMLDivElement>();
  const narrow = useMedia(NARROW);
  const svg = useRef<SVGSVGElement>(null);
  const panel = useRef<HTMLElement>(null);
  const graph = useMemo(() => (g.data ? cleanGraph(g.data) : null), [g.data]);
  const node = graph && sel ? graph.nodes.find((n) => n.id === sel) ?? null : null;

  // A node that was deleted is no longer open.
  useEffect(() => { if (sel && graph && !graph.nodes.some((n) => n.id === sel)) setSel(null); }, [graph, sel]);
  // On a narrow screen the details sit under the canvas: bring them into view when a node opens.
  useEffect(() => {
    if (!node || !panel.current || typeof panel.current.scrollIntoView !== "function") return;
    if (window.matchMedia?.(NARROW).matches) panel.current.scrollIntoView({ block: "nearest", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [node?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (g.status === "error" && !g.data) return <div className="page"><ErrorState error={g.error} retry={g.reload} what="the work graph" /></div>;
  if (!graph) return <div className="page"><Loading label="Loading the work graph" /></div>;
  const count = graph.nodes.length;
  const faded = graph.nodes.filter(isLapsed).length;
  const height = canvasHeight(width, count);
  // On a wide screen the details sit at the stage's right edge: the graph makes room for them, so the opened node is never under the panel.
  const canvasWidth = node && !narrow ? Math.max(300, width - PANEL_ROOM) : width;
  const close = () => { setSel(null); svg.current?.focus(); };

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow="Graph"
        title="How your work connects"
        lede={count === 0 ? undefined : `${count} ${count === 1 ? "thing" : "things"} Knack knows about your work${faded ? `, ${faded} fading now` : ""}.`}
        aside={<OriginBadge meta={g.meta} label={g.meta ? originLabel(g.meta.origin) : undefined} />}
      />

      {count === 0 ? (
        <EmptyState title="Nothing here yet" body="Knack adds things here as it sees your work." action={<a className="btn btn--secondary" href="#/setup">Go to set-up</a>} />
      ) : (
        <div className="stack">
          <div className="gcanvas__stage" ref={box} style={{ height }}>
            {width > 0 && <GraphCanvas graph={graph} width={canvasWidth} height={height} selected={node ? node.id : null} onSelect={setSel} svgRef={svg} />}
            {node && (
              <aside className="gpanel" ref={panel} aria-label="Node details" onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } }}>
                <NodePanel key={node.id} node={node} onClose={close} onChanged={() => { setSel(null); g.reload(); }} graph={graph} />
              </aside>
            )}
          </div>
          <GraphLegend entries={WORK_LEGEND} />
          <ChartFoot variant="about" meta={g.meta} badge={false} extra={<span>click a node for why it exists; the layout is for reading only</span>} />
        </div>
      )}
    </div>
  );
}
