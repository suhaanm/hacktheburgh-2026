# Knack design system

Direction: `docs/UI_DIRECTION.md` and, for the Knack look, `docs/KNACK_UX.md` section 6. What changed on 7 Nov 2026 and why: `docs/DESIGN_DIFF.md`. Preview: `design-system.html` (self-contained, also published as an Artifact; rebuild with `node packages/design/build.mjs`). The product was called Understudy; file names, token names and storage keys keep their history, nothing a person sees does.

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

## Word budgets (KNACK_UX section 5; enforced by `apps/dashboard/scripts/check-copy.mjs`, data in `apps/dashboard/qa/knack/budgets.json`)

| Element | Budget |
|---|---|
| Screen title (not a hero sentence) | 6 words, one line |
| Hero insight sentence | 16 words, two lines at 28 px |
| Lede or helper line | none by default; if used, 10 words, one line, and only for a real limit or a use rule |
| List row (title) | 12 words, one line; optional muted line 6 words |
| Card (proposal, queue, notice): title, body, button | 8 words, 20 words, 3 words |
| Corner pill label | 5 words |
| Corner card: title, body | 8 words, 22 words |
| Empty state: title, body, action | 5 words, 10 words, 1 action |
| Hint | 20 words, one sentence, never the only copy of a fact |
| Disclosure body | 60 words or 7 list items |
| Button | 3 words (4 for a hero action); a pill 2 words |
| Above the fold, content only | Home 50; Needs you 120; Routines 100; Growth 60 (empty 25); Your data 90; other worker screens 120; Admin screens 150; Details (More) screens 120; Evidence exempt |
| Whole default view, content only | worker 250, admin 400 |
| Paragraphs over two lines | 0 in any default view |
| Pills and badges above the fold | 1 (the origin badge) |
| Controls above the fold | Home 5, Needs you 12, other worker screens 8, Admin 10 |
| Sidebar | 6 rows (worker), 9 (admin), 0 words of hints |

A screen over its budget moves the excess into a Details, a Hint or the palette, or it is cut. A change that raises a number is a decision for the lead, recorded in `docs/DECISIONS.md`. The old budgets (about 400 words for a worker screen, 700 for admin) are retired.

## Knack additions (8 Nov 2026)

- **Tokens** (add, never rename): `--sidebar-w 208px`, `--content-read 720px`, `--content-wide 1080px`, `--page-pad-x 40px`, `--page-pad-top 32px`, `--row-h 44px`, `--control-h 32px`, `--table-row-h 36px`, `--pill-h 32px`, `--bottombar-h 56px`, `--corner-w 340px`, `--corner-inset 16px`, `--text-corner 13px` (the corner column only), `--lh-hero 1.2`, `--lh-title 1.25`, `--lh-row 1.4`, `--lh-read 1.5`, `--weight-regular 400`, `--weight-strong 600`. Weights are 400 and 600 only; no 500, no 700.
- **Type scale in use** (five sizes): hero 28 and 1.2 (`--text-2xl`, display 600); screen title and card title 22 and 1.25 (`--text-xl`, display 600); reading 16 and 1.5; rows, controls, labels 14 and 1.4 (body 400, 600 for the row title and labels); data, axis, time 12 (mono 400); one key number per chart `--text-3xl` (display 600, tabular).
- **Space rhythm**: 8 inside a row, 12 row padding, 16 between rows, 24 between sections, 32 page top, 40 page sides. One left-aligned column, 40 px from the sidebar on every screen, two widths: reading 720 (`.column`) and wide 1080 (`.column--wide`). Never centred.
- **Surfaces**: at most three on a screen: canvas `--bg`, a raised `--panel` for a separate object (never for a section), `--sunk` for code and evidence. Lists are hairlines, not stacks of cards. A shadow (`--elev-2`) only on layers that float: the corner pill and card, the palette, a sheet or popover. No shadow inside the page.
- **Motion**: state changes only (hover and press 140 ms, a disclosure 240, a card arriving 360, the ring landing 560, fade 900). Nothing loops. Progress is a count, not a spinner.
- **Components**: `lockup` and `glyph` (`apps/dashboard/src/components/Lockup.tsx`; rules in `brand/README.md`), `icon` (`Icon.tsx`: fourteen icons on a 16 px grid, 1.5 px stroke, currentColor; never inside a primary button, never decoration), `navitem` (icon, label, count), `listrows` and `listrow` (`Rows` and `Row` in `ui.tsx`: 44 px, the whole row is the target when it goes somewhere, actions on hover and focus, always visible on touch), `confirm-row` (`ConfirmRow`: the inline Forget it / Keep, safe choice focused, Escape means Keep, consequence printed), `hero-insight`, `screenhead` (title, at most one printed limit, the badge), `inline-banner`, `status-line`, `stop-button`, `sheet` (account menu, More, Settings: the layers that carry a shadow), `crumb` (the breadcrumb that replaces the frame note), `keyfigure`. `kbd` is the element. The corner pill and card are drawn by the desktop renderer, which mirrors the tokens.
- **Origin badge** (`pill--origin`): sentence case in the body face at 12 px and 600; dashed border means "not real" ("Example data", "Synthetic firm"). One per screen; its explanation is its Hint, except on Evidence and reviewer screens, where the full sentence stays printed.
- **Retired**: the eyebrow slot of `PageHead`, the empty-state mark (`state__mark` shows only in errors, where the cross carries the meaning), `framenote`, `datanote`, the permanent Stop bar, mono capitals outside chart axes and the work ribbon.

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

**Labels.** Sentence case (`.t-label`, `.stat__label`, table heads). The tracked mono capitals (`.t-label--mono`) are kept only for chart axes and the work ribbon.

**Type rationale.** Bricolage Grotesque (display) has an optical-size axis, so big numbers and headings get character while small headings stay calm; used for headings, labels and key figures. Source Sans 3 (body) is quiet, very legible, and has proper tabular figures. JetBrains Mono (data) keeps axes, intervals and labels aligned and distinguishes 0/O and 1/l. Not Inter, not Space Grotesk. Ligatures are off in mono so `<!--` stays literal.

**Do.** Say what will happen, and make "Not now" and "Never for this" as easy as "Yes". Every chart keeps its n, interval, a legend and a `synthetic` badge when it is, one click away for workers and printed for admins. Hairlines for structure; cards only for separate objects (proposal, queue item, notice, insight). Pair colour with text, shape or hatching.

**Don't.** No gradients, glows, sparkles, emoji markers, accent bars on cards, pies, 3D, dual axes, hover-only popovers, the `title` attribute as an explanation, or looping decorative motion. Do not hard-code hex values in components; add a token.

**Rebuild the preview.** Edit `tokens.css`, `components.css` or `design-system.src.html`, then `node packages/design/build.mjs` (inlines the CSS and regenerates the colour table with contrast ratios).
