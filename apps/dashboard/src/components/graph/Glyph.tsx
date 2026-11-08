// The graph layer's icons as React: one glyph inside a canvas node (an SVG group), and one on its own (a chip in the card, the panel and the key).
// The drawing data is lib/nodeIcons.ts. Strokes keep their 1.5 px at any size (vector-effect), caps and joins are round, colour is `currentColor`.
import { NODE_ICON, STEP_ICON, type IconPrim } from "../../lib/nodeIcons";
import type { WorkNodeType } from "../../types";

function Prims({ prims }: { prims: IconPrim[] }) {
  return (
    <>
      {prims.map((p, i) =>
        p.t === "path"
          ? <path key={i} d={p.d} vectorEffect="non-scaling-stroke" />
          : <circle key={i} cx={p.cx} cy={p.cy} r={p.r} vectorEffect="non-scaling-stroke" fill={p.fill ? "currentColor" : "none"} />,
      )}
    </>
  );
}

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round" } as const;

/** A glyph drawn inside a canvas node: centred on the origin, `size` px square. */
export function GlyphG({ prims, size }: { prims: IconPrim[]; size: number }) {
  const s = size / 16;
  return (
    <g className="gglyph" transform={`translate(${-size / 2} ${-size / 2}) scale(${s})`} {...stroke}>
      <Prims prims={prims} />
    </g>
  );
}

/** A glyph on its own, 16 px grid. Decorative: the name always travels beside it, in an aria-label or in the card. */
export function GlyphIcon({ prims, size = 16 }: { prims: IconPrim[]; size?: number }) {
  return (
    <svg className="icon gglyph" width={size} height={size} viewBox="0 0 16 16" focusable="false" aria-hidden="true" {...stroke}>
      <Prims prims={prims} />
    </svg>
  );
}

/** The filled round chip a kind wears everywhere outside the canvas: the same colour and glyph as its node. */
export function KindChip({ kind, step, tone, size = 20 }: { kind?: WorkNodeType; step?: keyof typeof STEP_ICON; tone?: "expert" | "novice" | "muted"; size?: number }) {
  const prims = kind ? NODE_ICON[kind] : STEP_ICON[step ?? "step"];
  return (
    <span className="gkind" data-kind={kind} data-tone={tone} style={{ width: size, height: size }} aria-hidden="true">
      <GlyphIcon prims={prims} size={Math.round(size * 0.66)} />
    </span>
  );
}
