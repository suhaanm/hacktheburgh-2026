/**
 * Handoff contract: DESIGN -> OVERLAY.
 *
 * Pure data, no DOM, no CSS. All lengths are CSS px in the overlay window; durations are ms.
 * The look is Understudy's own (packages/design/tokens.css): calm, precise, hairline. Colours are the design tokens (accent teal for
 * "look here", good, warn, bad), words are set in the body face and numerals in the mono face, nothing glows and nothing loops.
 * A mark is a 2 px coloured line with a 1 px white keyline beside it and a 1 px ink keyline outside that (the ring draws them on its
 * outer side only, so it stays a thin line; other strokes use `strokeLayers`, centred). White stands out from dark pages and ink from
 * light pages, so each mark keeps >=3:1 edge contrast on any background. Colour is never the only cue: each tone also has a `glyph` and a `dash` pattern.
 */

import type { AnnotationTone } from '../../shared/protocol';

export type { AnnotationTone };
export const ANNOTATION_TONES: readonly AnnotationTone[] = ['guide', 'success', 'warn', 'danger'];

export type ToneGlyph = 'pointer' | 'check' | 'alert' | 'stop';

export interface AnnotationStyleSettings {
  bigAnnotations: boolean;
  highContrast: boolean;
  dyslexiaFont?: boolean;
}

export interface AnnotationStyleOptions {
  /** Pass `matchMedia('(prefers-reduced-motion: reduce)').matches`. Entrances do not move at all. */
  reducedMotion?: boolean;
  /** Pass `matchMedia('(prefers-color-scheme: dark)').matches`: the dark note chip (marks keep the same colours on every page). */
  dark?: boolean;
}

export interface ToneStyle {
  /** Coloured core stroke / fill. >=3:1 against `casing`. */
  core: string;
  /** Dark ink (same for all tones): chip and tag fills, the ghost cursor's outline. */
  casing: string;
  /** White (same for all tones). */
  halo: string;
  /** Stroke keylines: the one next to the core (the colour that contrasts with the core, >=3:1) and the one outside it. */
  keyInner: string;
  keyOuter: string;
  /** Text colour to put ON a `core` fill (badge digits). >=4.5:1 against `core`. */
  onCore: string;
  /** Soft glow colour (rgba). Decorative only. */
  glow: string;
  /** Translucent wash for highlightText fills. */
  wash: string;
  /** Stroke dash pattern as an SVG `stroke-dasharray`, or null for solid. Redundant, non-colour cue. */
  dash: string | null;
  /** Icon to draw beside the mark so the tone is readable without colour. */
  glyph: ToneGlyph;
  /** Spoken/ARIA name of the tone. */
  name: string;
  /** How many times the echo pulse repeats ('infinite' until cleared). */
  pulseIterations: number | 'infinite';
}

export interface StrokeLayer {
  color: string;
  width: number;
  opacity: number;
}

export interface AnnotationStyle {
  /** 1 normally, 1.6 with `bigAnnotations`. */
  scale: number;
  highContrast: boolean;
  reducedMotion: boolean;
  tones: Record<AnnotationTone, ToneStyle>;

  /** Total stroke widths per layer for a standard line (ring edge, arrow shaft). Paint halo, casing, core in that order. */
  stroke: { core: number; casing: number; halo: number; linecap: 'round'; linejoin: 'round' };
  /** Soft outer glow behind a mark (SVG blur stdDeviation ~ blur/2). */
  glow: { blur: number; opacity: number };
  /** Expanding "echo" ring that makes a mark breathe. */
  pulse: {
    enabled: boolean;
    periodMs: number;
    scaleFrom: number;
    scaleTo: number;
    opacityFrom: number;
    opacityTo: number;
    easing: string;
  };
  /** Appear/disappear. */
  transition: { enterMs: number; exitMs: number; easing: string; enterFromScale: number };

  ring: {
    /** Gap between the target box and the ring (px). */
    pad: number;
    /** Corner radius cap (px); use min(radius, shorter side / 2). */
    radius: number;
    /** Never draw a ring smaller than this (px) so tiny targets stay visible. */
    minSize: number;
    /** Never draw a ring larger than this (px per side): a ring is a pointer, not a frame. */
    maxSize: number;
    /** A very subtle second outline outside the ring, and the viewfinder corner ticks on it. */
    halo: { offset: number; width: number; opacity: number };
    ticks: { arm: number };
    /** How far a note chip sits from the ring's outer edge (clears the halo and the ticks). */
    noteGap: number;
  };
  badge: {
    /** The step number sits in a small pill this high (px). `diameter` is the same number, kept for obstacle maths. */
    diameter: number;
    padX: number;
    fontSize: number;
    fontWeight: 600;
    /** Numerals are set in the mono face. */
    fontFamily: string;
    /** Place the pill this far outside the ring's top-left corner. */
    offset: number;
  };
  arrow: {
    headLength: number;
    headWidth: number;
    /** Stop the tip this far short of the target edge so the arrow never covers it. */
    gap: number;
    /** 0 = straight; positive bows the shaft (fraction of its length). */
    curvature: number;
    minLength: number;
  };
  spotlight: {
    /** Opacity of the dim layer outside the cut-out. */
    dimOpacity: number;
    dimColor: string;
    pad: number;
    radius: number;
    /** Soft edge on the cut-out. 0 under high contrast. */
    feather: number;
  };
  tick: {
    size: number;
    /** Offset of the tick centre from the box's top-right corner (px, outward). */
    offset: number;
    drawMs: number;
    /** Tones used for ok / not-ok. A miss is a gentle `warn`, never `danger`. */
    okTone: AnnotationTone;
    notOkTone: AnnotationTone;
  };
  highlightText: {
    pad: number;
    underlineWidth: number;
    radius: number;
    /** Tone used for scam red flags. */
    tone: AnnotationTone;
    noteMaxWidth: number;
  };
  caption: {
    fontSize: number;
    lineHeight: number;
    fontFamily: string;
    padding: { x: number; y: number };
    radius: number;
    maxWidth: number;
    background: string;
    color: string;
    speakerFontSize: number;
    speakerColor: string;
    border: string;
    /** Distance from the bottom edge of the display. */
    bottomInset: number;
    /** Never over the middle of the screen. */
    maxHeightFraction: number;
  };
  /** The note on a ring (and any bubble): one quiet line, never a paragraph. */
  bubble: {
    fontSize: number;
    lineHeight: number;
    fontFamily: string;
    /** Numerals inside notes (the step pill) use this face. */
    monoFamily: string;
    fontWeight: 500;
    padding: { x: number; y: number };
    radius: number;
    maxWidth: number;
    /** At most this many characters are shown; the full sentence belongs on the dashboard. */
    maxChars: number;
    background: string;
    color: string;
    muted: string;
    borderColor: string;
    borderWidth: number;
    tail: number;
    shadow: string;
  };
  ghostCursor: {
    size: number;
    fill: string;
    /** Visual-only: this is where the "I never click" promise is shown. */
    tag: string;
    tagFontSize: number;
    /** Trail of fading dots behind the cursor. */
    trail: { count: number; spacingPx: number; opacity: number };
    /** Echo ring shown when `pressAtEnd` is set. It is a picture of a click, not a click. */
    press: { radius: number; durationMs: number };
    flight: { minMs: number; maxMs: number; pxPerSec: number; arcHeightFraction: number; easing: string; dwellMs: number };
  };
  levelChip: {
    fontSize: number;
    padding: { x: number; y: number };
    radius: number;
    background: string;
    color: string;
    border: string;
    changeMs: number;
  };
}

const INK = '#0B1220';
const HALO = '#FFFFFF';
// packages/design/tokens.css: --font-body and --font-mono (the faces are bundled, see overlay-fonts.css; the stacks fall back to system fonts).
const UI_FONT = "'Source Sans 3', 'Source Sans Pro', system-ui, -apple-system, 'Segoe UI', sans-serif";
const MONO_FONT = "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace";
const DYSLEXIA_FONT = "'OpenDyslexic', 'Atkinson Hyperlegible', system-ui, sans-serif";

// Design tokens (packages/design/tokens.css): --accent, --good, --warn, --bad (the light theme's deep colours, which also hold up on dark
// pages with the white keyline beside them) and the colour that goes ON each.
const CORES: Record<AnnotationTone, string> = { guide: '#0A7C78', success: '#177540', warn: '#8A6100', danger: '#B3261E' };
const ON_CORE = '#FFFFFF';
// Surfaces for the note chip: --panel, --fg, --muted.
const SURFACES = {
  // `line` is the chip's own hairline: dark on the light chip, light on the dark one, so the chip has an edge on any page.
  light: { panel: '#FFFFFF', fg: '#141922', muted: '#566074', line: 'rgba(11, 18, 32, 0.5)' },
  dark: { panel: '#161D26', fg: '#E7EBF1', muted: '#9AA6B8', line: 'rgba(255, 255, 255, 0.38)' },
} as const;
const GLYPHS: Record<AnnotationTone, ToneGlyph> = { guide: 'pointer', success: 'check', warn: 'alert', danger: 'stop' };
const DASHES: Record<AnnotationTone, string | null> = { guide: null, success: null, warn: '8 5', danger: '2 6' };
const NAMES: Record<AnnotationTone, string> = { guide: 'Look here', success: 'Done', warn: 'Take care', danger: 'Stop and check' };
// Nothing loops: a mark arrives with one short ease and then stays still.
const PULSES: Record<AnnotationTone, number | 'infinite'> = { guide: 0, success: 0, warn: 0, danger: 0 };

function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const round1 = (n: number): number => Math.round(n * 10) / 10;

export function annotationStyle(settings: AnnotationStyleSettings, options: AnnotationStyleOptions = {}): AnnotationStyle {
  const big = settings.bigAnnotations;
  const hc = settings.highContrast;
  const reduced = options.reducedMotion ?? false;
  const theme = options.dark ? 'dark' : 'light';
  const surface = SURFACES[theme];
  const s = big ? 1.6 : 1;
  const px = (n: number): number => round1(n * s);
  const font = settings.dyslexiaFont ? DYSLEXIA_FONT : UI_FONT;
  const cores = CORES;

  const tones = {} as Record<AnnotationTone, ToneStyle>;
  for (const tone of ANNOTATION_TONES) {
    const core = cores[tone];
    tones[tone] = {
      core,
      casing: INK,
      halo: HALO,
      // A 1 px white line next to the colour (it contrasts with every tone) and a 1 px ink line outside that: white stands out from
      // dark pages, ink from light pages.
      keyInner: HALO,
      keyOuter: INK,
      onCore: ON_CORE,
      glow: hexToRgba(core, 0),
      wash: hexToRgba(core, hc ? 0.3 : 0.18),
      dash: DASHES[tone],
      glyph: GLYPHS[tone],
      name: NAMES[tone],
      pulseIterations: PULSES[tone],
    };
  }

  // A 2 px coloured line with a 1 px ink keyline and a 1 px white keyline outside it (high contrast: 3 / 1.5 / 1.5).
  const core = px(hc ? 3 : 2);
  const casingExtra = px(hc ? 1.5 : 1);
  const haloExtra = px(hc ? 1.5 : 1);

  return {
    scale: s,
    highContrast: hc,
    reducedMotion: reduced,
    tones,
    stroke: {
      core,
      casing: round1(core + casingExtra * 2),
      halo: round1(core + casingExtra * 2 + haloExtra * 2),
      linecap: 'round',
      linejoin: 'round',
    },
    glow: { blur: 0, opacity: 0 },
    pulse: { enabled: false, periodMs: 1700, scaleFrom: 1, scaleTo: 1, opacityFrom: 0, opacityTo: 0, easing: 'linear' },
    // One short ease-in with the design system's landing curve (--ease-land); under reduced motion the mark just appears.
    transition: {
      enterMs: reduced ? 1 : 200,
      exitMs: reduced ? 1 : 140,
      easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
      enterFromScale: reduced ? 1 : 1.015,
    },
    ring: {
      pad: px(4),
      radius: px(4),
      minSize: px(20),
      maxSize: px(180),
      halo: { offset: px(4), width: px(1), opacity: 0.4 },
      ticks: { arm: px(9) },
      noteGap: px(10),
    },
    badge: { diameter: px(14), padX: px(5), fontSize: px(10.5), fontWeight: 600, fontFamily: MONO_FONT, offset: px(2) },
    arrow: { headLength: px(10), headWidth: px(10), gap: px(6), curvature: 0.12, minLength: px(36) },
    spotlight: {
      dimOpacity: hc ? 0.72 : 0.4,
      dimColor: '#05070D',
      pad: px(5),
      radius: px(6),
      feather: hc ? 0 : px(6),
    },
    tick: { size: px(18), offset: px(4), drawMs: reduced ? 0 : 320, okTone: 'success', notOkTone: 'warn' },
    highlightText: { pad: px(3), underlineWidth: px(2), radius: px(3), tone: 'danger', noteMaxWidth: px(240) },
    caption: {
      fontSize: px(13),
      lineHeight: 1.3,
      fontFamily: font,
      padding: { x: px(10), y: px(5) },
      radius: px(6),
      maxWidth: px(480),
      background: hexToRgba(surface.panel, hc ? 1 : 0.96),
      color: surface.fg,
      speakerFontSize: px(11),
      speakerColor: surface.muted,
      border: `${px(hc ? 2 : 1)}px solid ${surface.line}`,
      bottomInset: px(76),
      maxHeightFraction: 0.1,
    },
    bubble: {
      fontSize: px(11.5),
      lineHeight: 1.25,
      fontFamily: font,
      monoFamily: MONO_FONT,
      fontWeight: 500,
      padding: { x: px(7), y: px(3) },
      radius: px(4),
      maxWidth: px(300),
      maxChars: 40,
      background: hexToRgba(surface.panel, 0.97),
      color: surface.fg,
      muted: surface.muted,
      borderColor: surface.line,
      borderWidth: px(hc ? 2 : 1),
      tail: 0,
      shadow: `0 1px 2px ${hexToRgba('#05070D', 0.22)}`,
    },
    ghostCursor: {
      size: px(15),
      fill: cores.guide,
      tag: 'Showing you. I will not click.',
      tagFontSize: px(10.5),
      trail: { count: 0, spacingPx: px(14), opacity: 0.45 },
      press: { radius: px(14), durationMs: reduced ? 0 : 500 },
      flight: {
        minMs: reduced ? 150 : 280,
        maxMs: reduced ? 300 : 750,
        pxPerSec: 1700,
        arcHeightFraction: reduced ? 0 : 0.07,
        easing: 'cubic-bezier(0.45, 0, 0.25, 1)',
        dwellMs: 600,
      },
    },
    levelChip: {
      fontSize: px(12),
      padding: { x: px(10), y: px(4) },
      radius: px(999),
      background: hexToRgba(surface.panel, 0.96),
      color: surface.fg,
      border: `${px(hc ? 2 : 1)}px solid ${surface.line}`,
      changeMs: reduced ? 0 : 600,
    },
  };
}

/**
 * Stacked stroke layers for a line of `tone`, painted bottom to top: halo, casing, core.
 * `widthScale` lets thinner parts (arrow head outline, badge rim) reuse the same recipe.
 */
export function strokeLayers(style: AnnotationStyle, tone: AnnotationTone, widthScale = 1): readonly StrokeLayer[] {
  const t = style.tones[tone];
  return [
    { color: t.keyOuter, width: round1(style.stroke.halo * widthScale), opacity: 1 },
    { color: t.keyInner, width: round1(style.stroke.casing * widthScale), opacity: 1 },
    { color: t.core, width: round1(style.stroke.core * widthScale), opacity: 1 },
  ];
}

export const DEFAULT_ANNOTATION_STYLE: AnnotationStyle = annotationStyle({ bigAnnotations: false, highContrast: false });
