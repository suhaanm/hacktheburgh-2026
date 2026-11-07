// WCAG contrast maths + a tiny reader for tokens.css, so the palette is checked by a test, not by eye.

export function parseHex(hex: string): [number, number, number] {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new Error(`not a 6-digit hex colour: ${hex}`);
  const n = parseInt(m[1]!, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function luminance(hex: string): number {
  const [r, g, b] = parseHex(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export type TokenMap = Record<string, string>;

export interface TokenRule {
  selector: string;
  decls: TokenMap;
}

/** Reads top-level `selector { --x: y; }` rules (ignores @media and comments). */
export function parseTokenRules(css: string): TokenRule[] {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const rules: TokenRule[] = [];
  let depth = 0;
  let selectorStart = 0;
  let bodyStart = 0;
  let selector = '';
  for (let i = 0; i < stripped.length; i++) {
    const ch = stripped[i];
    if (ch === '{') {
      if (depth === 0) {
        selector = stripped.slice(selectorStart, i).trim();
        bodyStart = i + 1;
      }
      depth++;
    } else if (ch === '}') {
      depth--;
      if (depth === 0) {
        if (!selector.startsWith('@')) {
          const decls: TokenMap = {};
          for (const line of stripped.slice(bodyStart, i).split(';')) {
            const m = /^\s*(--[\w-]+)\s*:\s*([\s\S]+?)\s*$/.exec(line);
            if (m) decls[m[1]!] = m[2]!;
          }
          rules.push({ selector, decls });
        }
        selectorStart = i + 1;
      }
    }
  }
  return rules;
}

export interface ThemeKey {
  dark: boolean;
  highContrast: boolean;
  persona?: 'marcus' | 'amelia';
  glass?: boolean;
}

function matches(selector: string, key: ThemeKey): boolean {
  const attrs = [...selector.matchAll(/\[data-([\w-]+)='([^']*)'\]/g)].map((m) => [m[1]!, m[2]!] as const);
  if (!selector.startsWith(':root')) return false;
  return attrs.every(([name, value]) => {
    if (name === 'theme') return value === (key.dark ? 'dark' : 'light');
    if (name === 'high-contrast') return value === String(key.highContrast);
    if (name === 'persona') return value === key.persona;
    if (name === 'glass') return value === String(key.glass ?? false);
    return false;
  });
}

/** Computes the token map `key` would see, resolving `var(--x)` chains. Source order wins, as in CSS. */
export function resolveTheme(css: string, key: ThemeKey): TokenMap {
  const merged: TokenMap = {};
  for (const rule of parseTokenRules(css)) {
    if (matches(rule.selector, key)) Object.assign(merged, rule.decls);
  }
  const resolve = (value: string, depth = 0): string => {
    if (depth > 8) throw new Error(`token cycle at ${value}`);
    const m = /^var\((--[\w-]+)\)$/.exec(value);
    return m ? resolve(merged[m[1]!] ?? '', depth + 1) : value;
  };
  const out: TokenMap = {};
  for (const [name, value] of Object.entries(merged)) out[name] = resolve(value);
  return out;
}

/** Opaque result of painting `fg` at `alpha` over `backdrop` (for checking text over translucent glass). */
export function blend(fg: string, alpha: number, backdrop: string): string {
  const [r, g, b] = parseHex(fg);
  const [br, bg, bb] = parseHex(backdrop);
  const mix = (a: number, c: number): string => Math.round(a * alpha + c * (1 - alpha)).toString(16).padStart(2, '0');
  return `#${mix(r, br)}${mix(g, bg)}${mix(b, bb)}`;
}

/** Reads `color-mix(in srgb, #hex var(--glass-x), transparent)` as the hex and which glass variable sets its alpha. */
export function parseGlassMix(value: string): { hex: string; layer: 'shell' | 'card' } | null {
  const m = /^color-mix\(in srgb, (#[0-9a-f]{6}) var\(--glass-(shell|card)\), transparent\)$/i.exec(value.trim());
  return m ? { hex: m[1]!, layer: m[2] as 'shell' | 'card' } : null;
}
