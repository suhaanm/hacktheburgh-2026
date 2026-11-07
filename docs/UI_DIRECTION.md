# UI direction

**The owner wants our own, great-looking, uncluttered, standout interface. Follow this document. When it conflicts with a generic template, this document wins.**

## Intent

Understudy should feel like a calm instrument, not a dashboard. The person is doing real work; the interface should help, then get out of the way. The product's own idea is that help fades, so the interface should fade too: quiet by default, specific when it speaks.

Three things must stand out and be memorable:
1. **The work ribbon**: two aligned traces, expert above novice, gaps hatched, seconds lost in red beneath. It is the signature visual.
2. **The work graph**: nodes that link, combine and fade as routines form, skills are mastered and habits lapse. Motion carries meaning here: fading is literal.
3. **The presence heatmap**: a person's working rhythm over a week, with intervals, and the free hours it reveals.

## Principles

1. **One main idea per screen.** One hero visual or one task. Everything else is secondary and out of the way.
2. **Fewer elements, better made.** If a control is not needed on the first view, move it behind a click. No card soup, no 12-widget dashboards, no decorative panels.
3. **Every visual property encodes something true.** Size, colour, opacity, position and motion each mean one thing, and a legend says what. No ornament.
4. **Plain language.** Short sentences, specific verbs, no marketing. Say what happened and what the worker can do. Errors say what went wrong and how to fix it.
5. **Honesty is visible.** Synthetic data carries a badge. Every chart shows its n and its interval. The limitations register is a first-class screen, not a footnote.
6. **Calm motion.** Motion shows state change (a node fading, a ring landing, a card arriving). Nothing loops for decoration. Respect reduced motion.
7. **Direct manipulation.** The worker can open, edit, pause and delete things (a graph node, a memory line, a consent) without a settings maze.

## What to avoid

- Generic AI looks: purple-to-blue gradients, glowing orbs, sparkle icons, chat-bubble clutter, emoji as section markers, centred hero banners, `rounded-lg` and soft shadows on everything, accent bars on cards.
- Inter or Space Grotesk as the "safe" face, and a cream background with a serif and a terracotta accent.
- Charts without scales, labels or intervals. Pie charts. 3D.
- Dense tables as the first thing a person sees.
- Modal after modal. Prefer inline expansion and side panels.
- Dark patterns around consent. Consent screens say plainly what will happen and make "not now" and "never" as easy as "yes".

## Visual language (starting point, refine it)

The plan page at https://claude.ai/artifact/R1WPdfux2A6riEx4kbmd6H uses an early version of this language. Keep its logic, and improve it where you can.

**Tokens** (define on `:root`, redefine for dark; give `body` an explicit background):

| Token | Light | Dark | Meaning |
|---|---|---|---|
| `--bg` | `#f4f6f9` | `#0e1319` | canvas |
| `--panel` | `#ffffff` | `#161d26` | raised surface, used sparingly |
| `--fg` | `#141922` | `#e7ebf1` | text |
| `--muted` | `#566074` | `#9aa6b8` | secondary text |
| `--line` | `#d8dee8` | `#283341` | hairlines |
| `--accent` | `#0a7c78` | `#4fd1c5` | the one accent: focus, links, primary action |
| `--expert` | `#b5650a` | `#f0a04b` | expert trace and memory nodes |
| `--novice` | `#4150c9` | `#8b98ff` | novice trace and skill nodes |
| `--good` | `#1a7f45` | `#5ad08a` | automation, success |
| `--warn` | `#a86a00` | `#f0b24b` | caution |
| `--bad` | `#b3261e` | `#ff8a80` | cost, error, time lost |

Design both themes with equal care. Contrast must pass WCAG AA.

**Type.** One characterful display face used with restraint for headings and key numbers, a calm body face, and a mono face for data and labels. A starting set: Bricolage Grotesque (display), Source Sans 3 (body), JetBrains Mono (data). You may change them if you can make a better pairing; do not use Inter or Space Grotesk. Keep body text near 65 characters wide, use tabular figures wherever numbers align, give headings balanced wrapping.

**Space and layout.** Generous whitespace, a 4 px base unit, a clear type scale, one column of reading width on text screens, a wide canvas on visual screens. Build with flex and grid and `gap`. Make it work at 1440 by 900 and 390 by 844 with no horizontal page scroll.

**Components.** Cards only where an element is a separate object (a proposal, a queue item). Pills for state (rung, consent, tier). Hairline separators. Focus rings that are visible. Buttons say what they do ("Approve and run", "Not now", "Never for this").

## Screens

| Screen | Hero | Secondary |
|---|---|---|
| **Onboarding** | A single question at a time, large type, progress as a thin line | Role cards (3 to 5 visible), a preview of the memory file being written |
| **Today** | The current task and the one thing the coach is saying | Level chip, a small "why" link, Stop |
| **Routines** | The proposal card: what I saw, how often, hours saved with interval, what it touches, what it will never do | Rung display, consent switches, per-routine unattended opt-in |
| **Genome** | The work ribbon with the gap waterfall | Placebo and null controls, the transition graph toggle, replay scrubber |
| **Graph** | The work graph, full canvas | Legend, node detail panel with edit and delete |
| **Presence** | The 7 by 96 heatmap with intervals | Idle-capacity hours, quiet-hours editor, window forecast |
| **Memory** | The Markdown file, readable and editable | History of rule proposals |
| **Queue** | Morning approvals, one card each with an evidence bundle | Report of what ran and what failed |
| **Evidence** | Calibration, risk-coverage, off-policy recovery, injection table | Limitations register, n and origin on every chart |

## Signature interactions

- **Fade.** When help fades after mastery, the coach's UI visibly recedes: smaller, then a dot, then gone. A returning worker sees it come back.
- **Link, combine, fade.** In the graph, related nodes draw a thin link; two routines that always run together slide into one composite node; unused nodes lose opacity along the same decay curve the level engine uses.
- **Ring landing.** The overlay ring eases onto the target, and hides if the screen changed (no stale arrows).
- **Proposal arrival.** A routine card slides in at a natural break, never mid-task, and leaves if ignored.
- **Kill switch.** Always reachable. One press stops everything and says so.

## Definition of done for any UI task

1. Look at it rendered, in light and dark, at 1440 by 900 and 390 by 844.
2. It has one clear focal element. Count the controls on first view; remove any that are not needed.
3. Every colour, size and motion has a meaning that the legend or copy states.
4. Text is plain and specific. No placeholder copy.
5. Keyboard focus is visible. Contrast passes. Reduced motion is respected.
6. Empty, loading and error states are designed, not blank.
7. Synthetic data is badged and every chart shows n and its interval.

## Update, 7 Nov 2026 (design sync, decision D45)

The shared system now follows the quieter, merged version (`packages/design/README.md`, "Rules for new components" and "Word budgets"; the diff is `docs/DESIGN_DIFF.md`, the per-screen audit `docs/DESIGN_AUDIT.md`). What changes for this document: (1) principle 2 is stricter: one hero per screen, at most one short helper line under a title, details behind a "Details" disclosure or a small accessible Hint, at most 7 rows in a default list. (2) "Every chart shows its n and its interval" now reads: on worker screens they are one hover, focus or tap away (a Hint beside the figure, or one "About this data" disclosure; the origin badge stays visible); on admin screens, the Evidence page and the limitations register they stay printed. (3) A Hint is an info button with a one or two sentence note, never the only copy of a limit, a consent, an error or an origin; the `title` attribute is not used to explain anything. (4) Labels are sentence case in the display face; the mono capitals stay only for chart axes and the work ribbon.

