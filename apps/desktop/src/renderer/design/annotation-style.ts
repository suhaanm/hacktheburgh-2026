/**
 * Handoff contract: DESIGN -> OVERLAY.
 *
 * Pure data, no DOM, no CSS. All lengths are CSS px in the overlay window; durations are ms.
 * Every stroke is drawn as THREE stacked layers (see `strokeLayers`): a white halo, a dark ink casing,
 * then the coloured core. The halo separates the mark from dark screens, the casing from light screens,
 * so each mark keeps >=3:1 edge contrast on any background. Colour is never the only cue: each tone also
 * has a `glyph` and a `dash` pattern.
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
  /** Pass `matchMedia('(prefers-reduced-motion: reduce)').matches`. Pulses become static, entrances fade only. */
  reducedMotion?: boolean;
}

export interface ToneStyle {
  /** Coloured core stroke / fill. >=3:1 against `casing`. */
  core: string;
  /** Dark ink drawn directly under the core (same for all tones). */
  casing: string;
  /** Light halo drawn outermost (same for all tones). */
  halo: string;
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
  };
  badge: {
    diameter: number;
    fontSize: number;
    fontWeight: 700;
    fontFamily: string;
    /** Place the badge this far outside the ring's top-left corner. */
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
  bubble: {
    fontSize: number;
    lineHeight: number;
    fontFamily: string;
    padding: { x: number; y: number };
    radius: number;
    maxWidth: number;
    background: string;
    color: string;
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
const UI_FONT = "'Atkinson Hyperlegible', system-ui, -apple-system, 'Segoe UI', sans-serif";
const DYSLEXIA_FONT = "'OpenDyslexic', 'Atkinson Hyperlegible', system-ui, sans-serif";

// Okabe-Ito-derived hues, lightened so the core clears 3:1 on the ink casing.
const CORES_NORMAL: Record<AnnotationTone, string> = {
  guide: '#4FB3FF',
  success: '#2FD39A',
  warn: '#FFB000',
  danger: '#FF6A4D',
};
const CORES_HC: Record<AnnotationTone, string> = {
  guide: '#7CD0FF',
  success: '#4DF0B2',
  warn: '#FFD23F',
  danger: '#FF8A70',
};
const GLYPHS: Record<AnnotationTone, ToneGlyph> = { guide: 'pointer', success: 'check', warn: 'alert', danger: 'stop' };
const DASHES: Record<AnnotationTone, string | null> = { guide: null, success: null, warn: '12 8', danger: '2 9' };
const NAMES: Record<AnnotationTone, string> = { guide: 'Look here', success: 'Done', warn: 'Take care', danger: 'Stop and check' };
// One soft echo when a mark appears, then it stays steady (nothing blinks): user request for the demo.
const PULSES: Record<AnnotationTone, number | 'infinite'> = { guide: 1, success: 1, warn: 1, danger: 1 };

function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const round1 = (n: number): number => Math.round(n * 10) / 10;

export function annotationStyle(settings: AnnotationStyleSettings, options: AnnotationStyleOptions = {}): AnnotationStyle {
  const big = settings.bigAnnotations;
  const hc = settings.highContrast;
  const reduced = options.reducedMotion ?? false;
  const s = big ? 1.6 : 1;
  const px = (n: number): number => round1(n * s);
  const font = settings.dyslexiaFont ? DYSLEXIA_FONT : UI_FONT;
  const cores = hc ? CORES_HC : CORES_NORMAL;

  const tones = {} as Record<AnnotationTone, ToneStyle>;
  for (const tone of ANNOTATION_TONES) {
    const core = cores[tone];
    tones[tone] = {
      core,
      casing: INK,
      halo: HALO,
      onCore: INK,
      glow: hexToRgba(core, hc ? 0.7 : 0.55),
      wash: hexToRgba(core, hc ? 0.4 : 0.3),
      dash: DASHES[tone],
      glyph: GLYPHS[tone],
      name: NAMES[tone],
      pulseIterations: reduced ? 1 : PULSES[tone],
    };
  }

  const core = px(hc ? 3.5 : 2.5);
  const casingExtra = px(hc ? 1.8 : 1.2);
  const haloExtra = px(hc ? 1.8 : 1);

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
    glow: { blur: px(hc ? 8 : 10), opacity: hc ? 0.7 : 0.55 },
    pulse: {
      enabled: !reduced,
      periodMs: 1700,
      scaleFrom: 1,
      scaleTo: big ? 1.1 : 1.07,
      opacityFrom: 0.6,
      opacityTo: 0,
      easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)',
    },
    transition: {
      enterMs: reduced ? 100 : 180,
      exitMs: reduced ? 80 : 150,
      easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)',
      enterFromScale: reduced ? 1 : 1.05,
    },
    ring: { pad: px(5), radius: px(8), minSize: px(24), maxSize: px(180) },
    badge: { diameter: px(18), fontSize: px(12), fontWeight: 700, fontFamily: font, offset: px(2) },
    arrow: { headLength: px(14), headWidth: px(14), gap: px(6), curvature: 0.12, minLength: px(36) },
    spotlight: {
      dimOpacity: hc ? 0.72 : 0.45,
      dimColor: '#05070D',
      pad: px(6),
      radius: px(9),
      feather: hc ? 0 : px(8),
    },
    tick: { size: px(24), offset: px(4), drawMs: reduced ? 0 : 420, okTone: 'success', notOkTone: 'warn' },
    highlightText: { pad: px(3), underlineWidth: px(4), radius: px(4), tone: 'danger', noteMaxWidth: px(300) },
    caption: {
      fontSize: px(16),
      lineHeight: 1.3,
      fontFamily: font,
      padding: { x: px(14), y: px(7) },
      radius: px(14),
      maxWidth: px(720),
      background: hc ? 'rgba(11, 18, 32, 0.94)' : 'rgba(11, 18, 32, 0.78)',
      color: '#FFFFFF',
      speakerFontSize: px(12),
      speakerColor: '#FFD9A0',
      border: hc ? `${px(3)}px solid #FFFFFF` : `${px(1)}px solid rgba(255, 255, 255, 0.22)`,
      bottomInset: px(28),
      maxHeightFraction: 0.12,
    },
    bubble: {
      fontSize: px(22),
      lineHeight: 1.4,
      fontFamily: font,
      padding: { x: px(18), y: px(12) },
      radius: px(14),
      maxWidth: px(340),
      background: '#FFFFFF',
      color: '#0B1220',
      borderColor: INK,
      borderWidth: px(hc ? 3.5 : 2.5),
      tail: px(14),
      shadow: '0 6px 22px rgba(5, 7, 13, 0.35)',
    },
    ghostCursor: {
      size: px(17),
      fill: cores.guide,
      tag: 'Showing you. I will not click.',
      tagFontSize: px(11),
      trail: { count: 0, spacingPx: px(14), opacity: 0.45 },
      press: { radius: px(18), durationMs: reduced ? 0 : 700 },
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
      fontSize: px(16),
      padding: { x: px(14), y: px(7) },
      radius: px(999),
      background: 'rgba(11, 18, 32, 0.8)',
      color: '#FFFFFF',
      border: `${px(hc ? 3 : 1.5)}px solid ${hc ? '#FFFFFF' : 'rgba(255, 255, 255, 0.4)'}`,
      changeMs: reduced ? 0 : 900,
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
    { color: t.halo, width: round1(style.stroke.halo * widthScale), opacity: 0.92 },
    { color: t.casing, width: round1(style.stroke.casing * widthScale), opacity: 1 },
    { color: t.core, width: round1(style.stroke.core * widthScale), opacity: 1 },
  ];
}

export const DEFAULT_ANNOTATION_STYLE: AnnotationStyle = annotationStyle({ bigAnnotations: false, highContrast: false });
