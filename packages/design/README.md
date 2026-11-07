# Understudy design system

Direction: `docs/UI_DIRECTION.md`. What changed on 7 Nov 2026 and why: `docs/DESIGN_DIFF.md`. Preview: `design-system.html` (self-contained, also published as an Artifact).

## Rules for new components

Every new component follows these ten. Break one only with a reason written in `docs/DECISIONS.md`.

1. **One hero per screen.** Everything else sits behind a click.
2. **One short helper line under a title**, one line at 1440 px (about 90 characters). No lede paragraph on a worker screen.
3. **Details live in a disclosure or a Hint.** Disclosure first (`Details`, "Why this?", "About this data"); a Hint for a unit, a definition or an interval.
4. **At most 7 rows in any default list**, then "Show all N".
5. **Numbers always carry a unit and a badge** (origin badge stays visible). Interval and n sit behind a Hint on worker screens (`MetricRow`, "About this data"); admin, Evidence and reviewer screens print them.
6. **No walls of text**: no paragraph over two lines of 65 characters in a default view. If it is longer, it is a disclosure.
7. **No gradients, glows, emoji, accent bars.** Hatching and range bands are data encodings, not decoration.
8. **Few controls**: one primary action, at most two quiet ones; row actions show on hover or focus-within and are always visible on touch.
9. **A Hint never holds the only copy of a fact**: not a limitation, an approval's consequence, an error, a gate or an origin. No links or buttons inside a Hint (needing a click makes it a disclosure). Never use the `title` attribute to explain anything.
10. **Look at it**: light and dark, 1440 by 900 and 390 by 844, keyboard focus visible, reduced motion respected, empty, loading and error states designed.

Empty, loading and error wording: say what happened, then what the person can do, then what was not touched ("Nothing leaves this laptop", "Your memory file is untouched"). No blame, no "invalid", no "oops". Errors say how to fix it. Loading says what is being read and roughly how long.

## Word budgets (what the audit measured against)

| Thing | Budget |
|---|---|
| Page title | at most 10 words, two lines at 1440 |
| Helper line under a title (lede) | one line, about 90 characters; none on a worker screen if the title says it |
| Section subtitle | one line, about 90 characters |
| Card or row sentence | two lines at 65 characters (about 130 characters) |
| Hint | one or two sentences, under about 160 characters |
| Disclosure body | five lines of prose, or a list of at most 7 items |
| Button label | four words; a pill three |
| Tab or segmented label | two words |
| Default view of a worker screen | about 400 words of text, not counting figures; admin screens about 700; Evidence is exempt and keeps everything printed |

Measured on the demo fixtures at 1440 after the 7 Nov audit: Today 62 words, Presence 232, Memory 308, Routines 464, Growth 812, Genome 642 (Explain panel included). Anything over its budget goes into a Details or a Hint, or it is cut.

## Which pattern for detail?

| Detail is | Use | Why |
|---|---|---|
| a reason, a method, a limitation, a list | `Details` disclosure (or "About this data" under a chart) | opens in place; the same for keyboard, touch and screen reader |
| a unit, a definition, an interval, an n beside a figure | `Hint` | one or two sentences; opens on hover, focus or tap; Escape closes |
| a fact the worker must see (origin, "not enabled", "It will never", an error, a gate) | printed | never hidden |
| "+N more" items | `brief` with a "+N more" button | opens the list in place |

## Use it

In the dashboard entry: `import '../../packages/design/tokens.css'; import '../../packages/design/components.css';`. Both are plain CSS, no framework, no build step. Fonts are bundled by the dashboard (`@fontsource`); stacks fall back to system fonts, so the wifi-off demo works. React wrappers live in `apps/dashboard/src/components/` (`Hint.tsx`, `HitListRow.tsx`, `ui.tsx` for MetricRow, SectionHeader, Details, AboutData, InsightCard, NoticeCard, QuestionCard). The CSS is the source of truth; the wrappers only emit its markup.

## Components (all in `components.css`)

`btn`, `pill` (rung, consent, tier, origin, level, check, state), `stat`, `metric` (MetricRow), `hint`, `details` and `about`, `brief`, `part` (SectionHeader), `state` (EmptyState, with `state__action`), `insight` (InsightCard), `alert` (NoticeCard: suggest, ask, stop, pause, report, rule), `hitlist` and `hitrow` (HitListRow), `qcard` (QuestionCard), `proposal`, `queue-item`, `toast`, `kill`, `coach`, `ring`, `memfile`, `sidepanel`, `tabs`, `segmented`, `table`, graph node classes (`node-fill-*`, `gnode`).

## Tokens

Colour names are fixed by UI_DIRECTION: `--bg --panel --fg --muted --line --accent --expert --novice --good --warn --bad`. Added: `--sunk --line-strong --control-line --accent-strong --on-*` (text on a solid colour), `--*-soft` (tints behind `--fg` text), `--seq-0..4` (one-hue magnitude ramp for the heatmap), `--node-routine --node-skill --node-memory` (graph fills; automation nodes use `--fg` with a glyph), `--text-xs..4xl`, `--space-1..12` (4 px unit), `--radius-1..3`, `--hair`, `--elev-*`, `--ease-*`, `--dur-*` (`instant 80`, `fast 140`, `base 240`, `arrive 360`, `land 560`, `fade 900`, `pop` = fast), `--z-*` (`panel 20`, `toast 30`, `hint 35`, `kill 40`, `overlay 50`), `--measure 65ch`, `--measure-short 46ch`. Dark theme: `prefers-color-scheme` unless `data-theme="light"`, or `data-theme="dark"` on `<html>`. Text pairs pass WCAG AA in both themes; reduced motion zeroes every `--dur-*`. Add tokens, never rename: existing code and `apps/desktop/src/renderer/design/tokens.css` (a mirror of the shared colours, checked by a test) depend on the names.

**Naming.** `block`, `block__element`, `block--modifier`. State lives in `aria-*` / `data-*` (`data-rung="A2"`, `data-mode="shadow"`, `data-state="small"`, `data-help="3"`, `data-polarity="positive"`, `data-detail="hint"`), not extra classes. Chart text and strokes use `.svg-text`, `.svg-axis`, `.svg-grid`, `.c-expert`, `.c-novice`. Hatch patterns for gaps and uncertainty are drawn per SVG (see the page source).

**Labels.** Sentence case in the display face (`.t-label`, `.stat__label`, table heads). The tracked mono capitals (`.t-label--mono`) are kept only for chart axes and the work ribbon.

**Type rationale.** Bricolage Grotesque (display) has an optical-size axis, so big numbers and headings get character while small headings stay calm; used for headings, labels and key figures. Source Sans 3 (body) is quiet, very legible, and has proper tabular figures. JetBrains Mono (data) keeps axes, intervals and labels aligned and distinguishes 0/O and 1/l. Not Inter, not Space Grotesk. Ligatures are off in mono so `<!--` stays literal.

**Do.** Say what will happen, and make "Not now" and "Never for this" as easy as "Yes". Every chart keeps its n, interval, a legend and a `synthetic` badge when it is, one click away for workers and printed for admins. Hairlines for structure; cards only for separate objects (proposal, queue item, notice, insight). Pair colour with text, shape or hatching.

**Don't.** No gradients, glows, sparkles, emoji markers, accent bars on cards, pies, 3D, dual axes, hover-only popovers, the `title` attribute as an explanation, or looping decorative motion. Do not hard-code hex values in components; add a token.

**Rebuild the preview.** Edit `tokens.css`, `components.css` or `design-system.src.html`, then `node packages/design/build.mjs` (inlines the CSS and regenerates the colour table with contrast ratios).
