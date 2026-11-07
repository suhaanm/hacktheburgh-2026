// The one icon set (KNACK_UX section 6): inline SVG on a 16 px grid, 1.5 px stroke, currentColor, no dependency.
// The fourteen of the spec come first; the rest are the trend arrows and the three Admin destinations. Icons sit beside nav items, the pill's
// glyph and rows. They never go inside a primary button (a verb needs no picture), never decorate, and are never emoji.
import type { CSSProperties } from "react";

type Shape = { d?: string; circles?: { cx: number; cy: number; r: number; fill?: boolean }[]; rect?: { x: number; y: number; w: number; h: number; fill?: boolean } };

export const ICONS = {
  // the fourteen of the spec
  home: { d: "M2.5 7.5 8 3l5.5 4.5M4 6.5V13h8V6.5" },
  "needs-you": { circles: [{ cx: 8, cy: 8, r: 5.5 }, { cx: 8, cy: 8, r: 1.4, fill: true }] },
  routines: { d: "M3 6h9l-2.5-2.5M13 10H4l2.5 2.5" },
  growth: { d: "M2.5 12 6 8l2.5 2.5L13.5 4M10 4h3.5v3.5" },
  "your-data": { d: "M3 4h10M3 8h10M3 12h6" },
  more: { circles: [{ cx: 3.5, cy: 8, r: 1, fill: true }, { cx: 8, cy: 8, r: 1, fill: true }, { cx: 12.5, cy: 8, r: 1, fill: true }] },
  stop: { rect: { x: 4, y: 4, w: 8, h: 8, fill: true } },
  check: { d: "M3.5 8.5 6.5 11.5 12.5 4.5" },
  alert: { d: "M8 2.5 14 13H2L8 2.5ZM8 6.5v3M8 11.2v.1" },
  chevron: { d: "M6 3.5 10.5 8 6 12.5" },
  info: { circles: [{ cx: 8, cy: 8, r: 6 }], d: "M8 7.3V11M8 5v.1" },
  search: { circles: [{ cx: 7, cy: 7, r: 4.5 }], d: "M10.4 10.4 13.5 13.5" },
  plus: { d: "M8 3v10M3 8h10" },
  close: { d: "M4 4l8 8M12 4l-8 8" },
  // trend arrows (a word always travels with them)
  up: { d: "M3 11l3.5-3.5 2 2L13 5M10 5h3v3" },
  down: { d: "M3 5l3.5 3.5 2-2L13 11M10 11h3V8" },
  flat: { d: "M3 8h10M10 5l3 3-3 3" },
  // Admin destinations
  firm: { d: "M3 13V6M8 13V3M13 13V8" },
  roles: { circles: [{ cx: 5.5, cy: 6, r: 2.2 }, { cx: 11, cy: 9, r: 2.2 }], d: "M2 13c.6-2 2-3 3.5-3M8.5 13.5c.5-1.6 1.4-2.3 2.5-2.3" },
  onboarding: { d: "M2.5 12.5C5 12.5 5 6 8 6s3 6.5 5.5 6.5" },
} satisfies Record<string, Shape>;

export type IconName = keyof typeof ICONS;
export const ICON_NAMES = Object.keys(ICONS) as IconName[];
/** The fourteen icons the spec names. The rest are extras (trend arrows, Admin destinations). */
export const SPEC_ICONS: IconName[] = ["home", "needs-you", "routines", "growth", "your-data", "more", "stop", "check", "alert", "chevron", "info", "search", "plus", "close"];

/** One icon. Decorative unless `label` is given (then it is an image with that name). 16 px by default; `size` scales the box, the stroke stays 1.5 in the 16 grid. */
export function Icon({ name, size = 16, label, className, style }: { name: IconName; size?: number; label?: string; className?: string; style?: CSSProperties }) {
  const s = ICONS[name] as Shape;
  const a11y = label ? { role: "img" as const, "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg className={className ? `icon ${className}` : "icon"} width={size} height={size} viewBox="0 0 16 16" focusable="false" style={style} {...a11y}>
      {s.rect && <rect x={s.rect.x} y={s.rect.y} width={s.rect.w} height={s.rect.h} fill={s.rect.fill ? "currentColor" : "none"} />}
      {s.circles?.map((c, i) => <circle key={i} cx={c.cx} cy={c.cy} r={c.r} fill={c.fill ? "currentColor" : "none"} />)}
      {s.d && <path d={s.d} />}
    </svg>
  );
}
