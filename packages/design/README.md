# Understudy design system

Direction: `docs/UI_DIRECTION.md`. Preview: `design-system.html` (self-contained, also published as an Artifact).

**Use it.** In the dashboard entry: `import '../../packages/design/tokens.css'; import '../../packages/design/components.css';`. Both are plain CSS, no framework, no build step. Add the font link once in `index.html`: `https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,300..800&family=JetBrains+Mono:wght@400;500;600&family=Source+Sans+3:wght@300..700&display=swap`. Stacks fall back to system fonts, so the wifi-off demo still works (self-host the three fonts for pixel-identical offline use).

**Tokens.** Colour names are fixed by UI_DIRECTION: `--bg --panel --fg --muted --line --accent --expert --novice --good --warn --bad`. Added: `--sunk --line-strong --control-line --accent-strong --on-*` (text on a solid colour), `--*-soft` (tints behind `--fg` text), `--seq-0..4` (one-hue magnitude ramp for the heatmap), `--text-xs..4xl`, `--space-1..12` (4 px unit), `--radius-1..3`, `--hair`, `--elev-*`, `--ease-*`, `--dur-*`. Dark theme: `prefers-color-scheme` unless `data-theme="light"`, or `data-theme="dark"` on `<html>`. Text pairs pass WCAG AA in both themes; reduced motion zeroes every `--dur-*`.

**Naming.** `block`, `block__element`, `block--modifier`. State lives in `aria-*` / `data-*` (`data-rung="A2"`, `data-mode="shadow"`, `data-state="small"`, `data-help="3"`), not extra classes. Chart text and strokes use `.svg-text`, `.svg-axis`, `.svg-grid`, `.c-expert`, `.c-novice`. Hatch patterns for gaps and uncertainty are drawn per SVG (see the page source).

**Type rationale.** Bricolage Grotesque (display) has an optical-size axis, so big numbers and headings get character while small headings stay calm; used only for headings and key figures. Source Sans 3 (body) is quiet, very legible, and has proper tabular figures. JetBrains Mono (data) keeps axes, intervals and labels aligned and distinguishes 0/O and 1/l. Not Inter, not Space Grotesk. Ligatures are off in mono so `<!--` stays literal.

**Do.** One hero per screen. Say what will happen, and make "Not now" and "Never for this" as easy as "Yes". Every chart shows n, interval, a legend and a `synthetic` badge when it is. Hairlines for structure; cards only for separate objects (proposal, queue item). Pair colour with text, shape or hatching.

**Don't.** No gradients, glows, sparkles, emoji markers, accent bars on cards, pies, 3D, dual axes, tooltips for essential info, or looping decorative motion. Do not hard-code hex values in components; add a token.

**Rebuild the preview.** Edit `tokens.css`, `components.css` or `design-system.src.html`, then `node packages/design/build.mjs` (inlines the CSS and regenerates the colour table with contrast ratios).
