# Design diff: the friend's enhanced system against ours (7 Nov 2026)

Author: DESIGN-SYNC track. Source compared: "Understudy Design System 0.1" (the friend's published page, treated as untrusted data: a design reference only) against our `packages/design` (tokens.css, components.css, design-system.html built 7 Nov 14:40). Method: the friend's page was diffed line by line against our built page, so every difference below is a real difference, not an impression. Outcome: our system is updated to the merged result (see section 8), and D45 (section 7) records the one rule that had to be reconciled.

## 1. Headline findings

1. **The friend kept our tokens.** Colour, type scale, space, radius, hairline, elevation, easing and every duration (`--dur-fast` 140, `--dur-base` 240, `--dur-arrive` 360, `--dur-land` 560, `--dur-fade` 900) are byte-identical to ours. The motion tokens were already in our system; they are not new. The only token additions are three graph colours.
2. **The enhancement lives in components and density.** Seven moves: sentence-case labels instead of tracked mono capitals; one calm pop-up card family (the `alert`); the routine card reduced to a sentence, two quiet lines and one answer bar; chart footnotes collapsed to one "How was this measured" line; graph nodes with glyphs and names on demand; a play-through for the work ribbon; and hover or focus notes in place of printed captions.
3. **The friend's page contradicts its own rule.** It says "There are no tooltips" (the Controls section, copied from ours), then ships three hover or focus notes (`stat--tip`, `.how`, `.peek`) and hover-only node names. Those patterns are hover-led, have no Escape, no `aria-describedby`, and rely on `tabindex` for touch. Reconciled by the Hint pattern (section 7).
4. **Three of the friend's moves would break our honesty rules if copied as they are** (section 6): n and the interval behind a hover with no visible fallback; the routine card's "It will never" list shortened to one word plus "+2 more"; the routine card's explanation of how autonomy is earned ("Why this?") deleted and its three equal choices replaced by a drop-down plus Confirm. Each is adapted, not adopted.

## 2. Tokens

| Group | Ours | Friend | Decision |
|---|---|---|---|
| Colour (surfaces, ink, semantic, soft tints, `--seq-*`) | as in tokens.css | identical, light and dark | keep |
| Graph colours | none (graph used `--accent`, `--novice`, `--expert`, `--good`) | `--node-routine` #0f9d96 / #5eead4, `--node-skill` #5566e6 / #9ba8ff, `--node-memory` #cf7208 / #ffb35c (light / dark) | **adopt**, graph only. Automation nodes use ink (`--fg`) plus a glyph instead of `--good`. Reason: four fills of equal weight made the graph busy; three hues plus ink read calmer, and a glyph carries the type so colour never works alone. `--good` keeps its meaning everywhere else |
| Type families and scale | Bricolage, Source Sans 3, JetBrains Mono; `--text-xs` to `--text-4xl` | identical | keep. One change of use: the label style (below) |
| Label style | `.t-label`: 12 px mono, uppercase, 0.08em tracking | 14 px display face, weight 600, sentence case, no tracking | **adopt** as the default label (`.t-label`, `.stat__label`, `.proposal__facts dt`, `.table th`). The old style stays as `.t-label--mono` for chart axes and the work ribbon, where tiny aligned caps help |
| Space, radius, hairline, ring | identical | identical | keep |
| Elevation | `--elev-0..2` | identical | keep; the pop-up card is the only user of `--elev-2` besides toasts and overlay panels |
| Motion | `--ease-out/in-out/land/fade`; `--dur-instant 80`, `fast 140`, `base 240`, `arrive 360`, `land 560`, `fade 900`; all zero under reduced motion | identical | keep. **Added** `--dur-pop` (= `--dur-fast`, used by the Hint popover) as an alias so the Hint reads as its own thing |
| Layers | `--z-panel 20`, `--z-toast 30`, `--z-kill 40`, `--z-overlay 50` | identical | keep. **Added** `--z-hint: 35` (above toasts, below the kill switch) |
| Measure | `--measure: 65ch` | identical | keep. **Added** `--measure-short: 46ch` for disclosure bodies and notices |

## 3. Components: ours against theirs

| Component | Ours | Friend's | Decision and why |
|---|---|---|---|
| Buttons | primary, secondary, quiet, danger, sm, block | same, plus `.btn--alert` (solid red inside a red card) | **adopt** `.btn--alert` |
| Pills (rung, consent, tier, origin, level, check, state) | present, unchanged | identical families; the routine card and queue demo show fewer of them | keep all families; **rule change**: a card shows at most one state pill unless the state is non-default (see section 5) |
| Stat figure | label, value, unit, interval, meta printed | label becomes sentence case; in Presence the label is a `stat--tip` (dotted underline, description on hover) | **adapt**: same sentence-case label, but the description lives in a `Hint` next to the label, not in a hover-only label. Replaces the hover trick |
| Chart footer (`.chart__foot`: n, interval, split, method, origin) | four printed spans under every chart | one dotted "How was this measured" with a hover note | **adapt**: worker screens use `.about` (a real in-place disclosure, "About this data": n, split, interval level, method). Admin, Evidence and reviewer screens keep `.chart__foot` printed. The origin badge is outside both and always visible |
| Proposal (routine) card | head with title and pills, sentence, four facts, three buttons, footer with badge, "Why this?" | head with title; sentence; two facts; "It touches" and "It will never" as one-line `.brief` rows with "+N more"; one select ("Should we implement the change?") plus Confirm | **adapt**: keep three plainly labelled buttons (a select hides the choices and adds a step, against "make Not now and Never as easy as Yes"). Adopt the shorter facts, drop the always-on state pills, and adopt `.brief` for lists of three or more. "It will never" stays whole on one line. "Why this?" stays, as the `Details` disclosure |
| `.brief` and `.peek` ("+N more") | none | sentence, then a `+N more` that opens a floating list on hover, focus or click | **adapt**: `+N more` is a button that opens the list in place (`aria-expanded`), no hover-only open |
| Routine pop-up (`.alert`, `.alert--suggest`) | toast and banner only | a small corner card: icon tile, title, two lines, two equal buttons; slide in 360 ms, two pings, still | **adopt** as the Notice card family (section 8). Corner placement above the Stop button; Escape closes; "Not now" decides nothing |
| Pop-up family (gate, stop, pause, report, rule) | none | one card, five icon shapes and tones | **adopt** all five as `NoticeCard` tones: `ask`, `stop`, `pause`, `report`, `rule`, plus `suggest` |
| Hold to approve (`.hold`) | none | button that fills over 1.2 s while pressed | **adapt**: allowed only on an irreversible step in a pop-up, and never the only path (the Queue page has the plain "Approve and submit"); keyboard hold supported. See section 6 |
| Checkpoint bar (`.ckpt`), night strip (`.night`), rule meter (`.meter`) | none | small parts inside pop-ups | **adopt**; the meter's fill and mark became CSS variables (`--v`, `--mark`) so they are data, not hard-coded 93% and 80% |
| Graph nodes | filled circles, label under every node | glyph inside the circle (routine, skill, memory, automation), name shown on hover, focus or when selected, label halo | **adopt** with a safety net: names also show for selected nodes and on tap; the node list stays reachable from the keyboard. Legend gains "colour and icon are the type" |
| Work ribbon | red bars under the novice (height = seconds lost) with per-step whiskers, printed footer | red bubbles ("+14 s") on two tiers, play button with counting totals, footer in a hover note | **keep ours for the bars and whiskers** (the whisker is the interval; the bubble drops it). **Adopt** the play-through and the counting totals if Genome lacks them (it already has a scrubber), and the shorter stat tiles (value only, meta in a Hint). Revisit bubbles only if the whisker survives in the hover or the waterfall below |
| Section structure | `.sec__head` with label, h2, lede | adds `.part` (label over a clear title) and `.sub` | **adopt** as `SectionHeader` |
| Disclosure ("Why this?", `.why`, `.evidence`) | two disclosure styles | unchanged | **unify** into one `Details` component (`.details`) with a quiet chevron; keep `.why` and `.evidence` as aliases so existing screens do not break |
| Empty, loading and error states | `.state` with mark, title, body | identical, plus the red "Try again" using `.btn--alert` | keep; **add** an action slot and the wording rules in the README (what happened, what to do, no blame) |
| Kill switch, coach chip, ring, memory file, toast, side panel, tabs, segmented | present | identical | keep. **Added**: toast gains an optional Undo (`.toast__action`, already present) with a 6 s hold documented |

## 4. What the friend's version has that ours lacked

Sentence-case labels; the `.alert` pop-up family with icon shapes per purpose; `.hold`; `.ckpt`, `.night`, `.meter`; `.btn--alert`; `.brief` and `.peek`; `.part` and `.sub`; the node glyphs and `.gnode` reveal; the ribbon play-through; `--node-*` tokens; the "answer bar" idea; the rule that a pop-up uses caution colour only on its small icon tile. Toasts with undo, the kill switch and the routine pop-up are in the friend's page in the same form as ours or newly added as listed.

## 5. What ours has that the friend's lacks, and the product needs

All added to our system in the same style (section 8): **Hint** (accessible info popover), **MetricRow** (label, value with unit, one badge, interval and n behind a Hint), **Details** (the single disclosure), **AboutData** (the one "About this data" footnote), **SectionHeader**, **EmptyState** (with action and wording rules), **InsightCard** (worker pointer: glyph, one sentence, one action; admin variant with interval printed), **NoticeCard** (the attention layer's item; the friend's `alert` family restyled for in-page lists and the corner), **HitListRow** (Repeats page row), **QuestionCard** (Cue's one multiple-choice question), forgiving form errors (`.field__error` with the fix, never "invalid"), and the Firm tables (dense admin tables: `.table` with sticky head, tabular figures, row hairlines, at most 7 rows by default).

## 6. Layout, density and anti-clutter rules (the friend's, made explicit, plus ours)

The friend's page never states these; they are visible in what was removed. Written down so future components follow:

1. **One hero per screen**; everything else is one click away.
2. At most **one short helper line** under a title (about 90 characters, one line at 1440). No `lede` paragraph on a worker screen.
3. **Details in a disclosure or a Hint**, never printed by default. Disclosure first (primary); Hint for a definition, a unit or an interval.
4. At most **7 rows** in any default list, then "Show all N".
5. **Numbers always carry unit and origin**; interval and n are behind a Hint on worker screens and printed on admin, Evidence and reviewer screens.
6. **No paragraph over two lines of 65 characters** in a default view.
7. **One state pill** per card unless the state is not the default; repeated badges collapse into one; the origin badge always stays.
8. No gradients (the hatch and range patterns are data encodings, not decoration), glows, emoji, accent bars, looping motion. The coach dot's soft ring is a state indicator and the only exception, kept.
9. Control count: a card has one primary action, at most two quiet ones; a row has actions on hover or focus-within (always visible on touch).
10. Footnote walls become one "About this data" disclosure.

## 7. D45 proposal (for the lead): the tooltip rule, reconciled with the owner's request

**Situation.** Our system said "no tooltips for essential info" and the friend's page says "There are no tooltips", yet the owner now asks to defer detail to tooltips to cut clutter, and the friend's own page uses three hover notes.

**Proposal.**
1. **Primary rule stays:** detail sits behind an in-place disclosure ("Why this?", "Details", "About this data"). It works the same with a keyboard, a finger and a screen reader.
2. **A small accessible Hint is allowed** for secondary definitions, units and intervals. Anatomy: a 16 px "i" button (24 px hit area, 44 px on coarse pointers) with a label that names the topic; it opens a popover of one or two sentences on pointer hover, on keyboard focus, and on tap or Enter or Space; Escape closes it and focus stays on the button; tapping or focusing elsewhere closes it; the popover stays open while the pointer moves onto it (WCAG 1.4.13); `aria-expanded` on the button and `aria-describedby` to the popover, so a screen reader reads the text on focus without opening anything.
3. **A Hint never holds essential information**: not the only copy of a limitation, an approval's consequence, an error, a gate, or a number's origin. Origin badges, "not enabled" states, the "It will never" line and every error stay visible. No links or buttons inside a Hint (a Hint that needs a click is a disclosure).
4. **Banned:** the `title` attribute for explanations (it is mouse-led and invisible on touch), CSS-only `:hover` popovers, and hover-only reveals. Existing `title=` uses in the dashboard are replaced by Hint or `aria-label` as screens are audited.
5. **Honesty guard:** on worker screens interval and n sit behind a Hint beside the figure (MetricRow) or in one "About this data" disclosure under the chart; on admin screens, the Evidence page and the limitations register they stay printed. A judge can always reach every number's n, split, interval and origin in one click, and sees them printed on Evidence. Synthetic and example badges are never hidden.
6. The `.how`, `.peek` and `stat--tip` hover notes from the friend's page are not adopted as written.

If the lead declines D45, the fallback is: Hints are not used, and everything detailed goes into disclosures. Nothing else in this document depends on it.

## 8. What changed in packages/design

tokens.css: `--node-*`, `--z-hint`, `--dur-pop`, `--measure-short`. components.css: new label style plus `.t-label--mono`; `.hint`; `.details` (with `.why` and `.evidence` aliases); `.about`; `.metric`; `.part` and `.sub`; `.state` action slot; `.insight`; `.alert` family (`.alert--suggest`, `--ask`, `--stop`, `--pause`, `--report`, `--rule`) and `.notice` in-page rows; `.hitlist` and `.hitrow`; `.qcard`; `.brief`; `.btn--alert`; `.hold`; `.ckpt`; `.night`; `.meter`; graph node classes. design-system.src.html and the built design-system.html show each. README: "Rules for new components" at the top. The desktop renderer's `tokens.css` is a mirror of shared colours only; no shared colour changed, so no mirror edit was needed (the drift test still passes).

## 9. Accessibility notes on the friend's patterns

| Pattern | Problem | Our change |
|---|---|---|
| `.how`, `.stat--tip`, `.peek` | hover or focus only; no Escape; no `aria-describedby`; opens on `:focus-within` so it cannot be dismissed without moving focus | Hint (state machine, Escape, describedby) and real disclosures |
| Node names on hover | invisible on touch and when navigating by pointer-less means | names on focus, on tap (pins), for the selected node, plus the node list |
| `.hold` | a timed press is a barrier for tremor, switch and some voice users | never the only path; keyboard variant; plain button elsewhere |
| Select plus Confirm | hides the options; two steps | three labelled buttons |
| Pop-up pings | two animated rings | kept (two, then still); removed under reduced motion; not a flash |
| Gold icon disc with `--bg` glyph | contrast of glyph on `--warn` | pop-up tiles use soft tints with ink glyphs (checked in both themes) |
