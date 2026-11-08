# Design system, word budgets and the Knack mark

> Calm, uncluttered and measured: word, click and contrast budgets are tests, and the mark is a disc with an offset ring.

**Capability:** A calm product: window, attention, context · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Design system with budgets as tests, The Knack mark and brand.

## Design system with budgets as tests

**Status:** built (tokens, components and check scripts merged to main; screens still being brought to budget by their tracks) · **Page:** `docs/features/design-system.md` · **Targets:** G-Research

### What it does

One token file and ten rules govern every screen: one hero per screen, details behind a disclosure or a short Hint, at most seven rows in a list, no gradients, glows or emoji. The limits are numbers a script checks, so a screen cannot grow back.

### How it works

Budgets: a hero sentence of at most 16 words; a card with 8 words of title, 20 of body, a button of 3 (a hero action 5 words, decision D56); Home at most 70 words above the fold and 6 controls (D66: the task box added one control and four words), Needs you 120, Growth 60, first run 90 words and 10 controls; no paragraph over two lines in a default view; at most one badge above the fold; a sidebar of the five worker rows and More, with no hint words. check-copy.mjs reads the running screens against these budgets; check-clicks.mjs replays the ten jobs and fails above their click budget; a copy lint rejects banned phrases and a visible old product name; contrast is tested at AA in both themes. Weights are 400 and 600 only; icons are 14 inline SVGs; mono capitals appear only on chart axes and the work ribbon. A Hint (a small accessible 'i') may hold a unit, a definition or an interval and is never the only copy of a fact: consent text, consequences, errors and limits stay printed.

**What is different.** Word, click and contrast budgets are tests that fail the build, and a Hint may never hold the only copy of a fact.

### Where to see it

Every screen; docs/knack-ux/before and after hold the screenshots; packages/design/design-system.html is the preview.

### Demo moment

Show Home before and after, side by side: 173 words and 10 controls above the fold became 47 words and 4 controls. Then press the Hint beside a number to show the interval one tap away.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Before: median 173 words above the fold across 20 worker screens (214 across 8 admin screens); 9 of 20 worker screens exceeded 400 words in total; measured at 1440 by 900 in the live mock | design measurement, one engine in mock mode, one browser, no users | `docs/KNACK_UX.md (section 2)` |
| After, on the static prototype: Home 47 words, Needs you 103, Routines 45, Growth 53, Firm 80, first run 20 | design measurement of a prototype; the real screens land a little above | `docs/knack-ux/after/after-measurements.json` |
| A friend's published design system was diffed line by line against ours: its tokens were byte-identical to ours; the enhancement was in components and density (sentence-case labels, one calm card family, collapsed chart footers, a play-through for the work ribbon). Three of its moves would have broken our honesty rules and were adapted, not adopted | design comparison, no users | `docs/DESIGN_DIFF.md (section 1)` |

### Honest limit

These measure the interface, not people. The budgets are our choice. The after numbers are a prototype's headline content; the screens being built will land a little above them, and some screens were still over budget when this was written (a pending list in the copy lint shrinks as tracks land). The Evidence page is exempt from the word budget by decision D45.

### Hackathon target

- **G-Research (make the invisible visible)**: the invisible made visible without clutter

## The Knack mark and brand

**Status:** built · **Page:** `docs/features/design-system.md` · **Targets:** G-Research

### What it does

The mark is a solid disc with a ring offset behind it: the worker, and the understudy shadowing them. It appears in the sidebar, the Dock, the menu bar and the corner pill.

### How it works

The lockup is the glyph then the word Knack in the display face at weight 600, with the disc as tall as the capital K and one disc radius between them. The ring is never recoloured for status; status is the pill's words and the menu-bar badge. The menu-bar template has six states in a fixed priority (stopped, needs you, glance, working, paused, idle). The Dock icon is an ink tile with a teal ring on the macOS canvas. There is no tagline in the app.

**What is different.** Nothing new is claimed; it is a design choice.

### Where to see it

Sidebar top, first-run screen, Dock, menu bar, corner pill; docs/knack-ux/knack-brand-sheet.svg.

### Demo moment

Show the brand sheet, then the menu bar changing from idle to a working dot when a routine starts.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measurement; the mark was already in packages/design/brand, and the dashboard had not used it before the Knack pass | no evidence yet (design) | `docs/KNACK_UX.md (section 6)` |

### Honest limit

A visual decision, judged by eye. Menu-bar states depend on desktop wiring that the owner has not seen on a real menu bar.

### Hackathon target

- **G-Research (make the invisible visible)**: a calm identity for a product that watches work

## 30-second spoken script

> Knack is meant to feel calm, so the calm is measured. Every element has a word budget, every screen a click budget, and a script fails the build if one is exceeded. Home went from a hundred and seventy-three words above the fold to forty-seven. Details live one tap away in a short hint, but the things you must see, like where the data came from and what cannot be undone, are always printed.

## Slide bullets

- Ten rules, one token file, two themes designed together.
- Word, click and contrast budgets are tests, not guidelines.
- Home: 173 words above the fold became 47 (prototype measurement).
- A Hint never holds the only copy of a fact; origin and consequences stay printed.
- Mark: a disc and an offset ring: the worker and the understudy.

## Sources

- `packages/design/README.md`
- `docs/KNACK_UX.md (sections 2, 5, 6)`
- `docs/knack-ux/budgets.json`
- `docs/knack-ux/clutter-1440x900.json`
- `docs/knack-ux/after/after-measurements.json`
- `docs/knack-ux/knack-brand-sheet.svg`
- `docs/UI_DIRECTION.md`
- `docs/DECISIONS.md (D45)`

## Related pages

`home-insights.md`, `knack-shell.md`, `needs-you.md`
