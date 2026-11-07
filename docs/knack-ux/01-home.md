# 01 Home: before and after

Screenshot of the before state: `before/worker-home.png` (1440 by 900) and `before/worker-home-390.png`.

## Before (measured 7 Nov, 1440 by 900, Worker view)

```
┌───────────────┬──────────────────────────────────────────────────────────────────┐
│ ▬ Understudy  │  Your week                                         (1) eyebrow    │
│               │  Two things from your week                         (2) title      │
│ Your week     │  9 to 15 November. Chosen by fixed rules,...  [SYNTHETIC FIRM]    │
│  A few pointers  (3) lede + (4) badge                                             │
│ Repeats       │ ┌────────────────────────────────────────────────────────────┐   │
│ Growth        │ │ ⚠ Worth a look · synthetic firm                  (5) eyebrow│   │
│ Routines      │ │   On the cliff check, you usually take about 35    [Open   │   │
│ Queue      (2)│ │   seconds longer than the expert's median.         Growth] │   │
│ Privacy       │ │   Open Growth to see where the time goes.        (6) repeats│   │
│ ─────────     │ │   > Why am I seeing this?                           (7)    │   │
│ Details ⌄     │ └────────────────────────────────────────────────────────────┘   │
│  Genome, Presence, Graph, Week and more   (8) 51 words of sidebar hints          │
│ More ⌄        │ ┌── (second card: the same shape, the same two sentences) ───┐   │
│  Today, Memory, Notices, Briefing and more                                       │
│ Evidence      │ An example week from the synthetic firm stands in for this       │
│               │ profile.                                              (9)        │
│ Local profile │ > Your Monday note   Copy the note                    (10)       │
│  benefits-processor                                                              │
│ ● Live engine, mock mode                                  Growth  How much less  │
│ View as (i) [Worker|Admin]                                Repeats 2 repeated (i) │
│ Search ⌘K  Take the tour                                  > What your admin can  │
│ [Auto|Light|Dark]                       [■ Stop everything  Shift Esc]  (11)     │
└───────────────┴──────────────────────────────────────────────────────────────────┘
173 words above the fold in the content, 51 in the sidebar, 10 controls in the content,
18 in the sidebar, 2 paragraphs over two lines. Content left edge at x = 474 (it is 294
on Routines and 280 on Growth: the page re-centres on every screen).
```

What is wrong, in the order a person meets it: (1) an eyebrow that repeats the nav label; (2) a count title that says nothing ("Two things"); (3) a lede about method that every week repeats; (4) a badge in mono capitals; (5) "Worth a look" repeated on every card; (6) a sentence that repeats the button label, twice; (7) a disclosure per card; (8) 51 words of hints in the sidebar on every screen; (9) a sentence that explains the badge; (10) a Monday-note control that nobody asked for on arrival; (11) a permanent Stop button on a screen where nothing is running.

## After (Knack window 1152 by 735, Worker view, one pointer, one thing needs you)

```
┌─ ● ● ● ───────────────────────────────────────────────────────────────────────────┐
│ ┌────────────┐                                                                      │
│ │ ◖● Knack   │ (a)   Week of 9 November                          ┌ Example data ┐ (e)│
│ │            │                                                   └──────────────┘    │
│ │ ⌂ Home     │ (b)                                                                   │
│ │ ◔ Needs you│ 1     On the cliff check you usually take about 35                    │
│ │ ↻ Routines │       seconds longer than the expert.                       (f) hero   │
│ │ ↗ Growth   │                                                                       │
│ │ ◫ Your data│       Try the expert's order: read, then check.             (g) why   │
│ │            │                                                                       │
│ │ ⋯ More     │       [ See where the time goes ]     Why this?             (h)       │
│ │            │       ──────────────────────────────────────────────────────          │
│ │            │   ◔   1 thing needs you                                   ›   (i)     │
│ │            │       ──────────────────────────────────────────────────────          │
│ │            │   ↻   About 1 hour a week could run for you.                ›   (j)     │
│ │            │                                                                       │
│ │ ◌ status   │ (c)                                                                   │
│ │ Ana  ■ Stop│                                                                       │
│ └────────────┘                                                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Annotations:

- (a) One quiet date line replaces the eyebrow, the title and the lede. Mono capitals are gone.
- (b) The hero is the insight, written as the title (28 px display, two lines). There is no title above it. The word "hero" is the only heading on the page; the sidebar item "Home" is current.
- (c) The sidebar footer is three things: a status line (a dot and "Running with example data", or "Live models"; it opens Settings at "Use live models"), the account button (name; opens View as, Appearance, Settings, Take the tour) and a Stop button (a red square and the word, always reachable). Search is the sidebar's first row on narrow windows and ⌘K everywhere; it is not drawn as a control.
- (e) "Example data" is the origin badge and stays visible. Its Hint holds "An example week from the synthetic firm stands in for this profile." (honesty: D45, the sentence is one tap away, the badge is not).
- (f) Template: `On {step} you usually take about {n} {unit} {longer|less} than {the expert|your peers}.` At most 16 words, one number, one unit.
- (g) One sentence of what to try, at most 12 words, imperative. Absent when the engine has none (never filled with a generic tip).
- (h) One primary action, at most four words, a verb phrase. "Why this?" is the existing Details disclosure and holds: how it was chosen (fixed rules, not a model), the interval, n, the origin sentence.
- (i) Needs-you row appears only when something needs the worker; it is the Inbox's count, one line, and the whole row is the target.
- (j) At most two secondary rows, in this order of claim: the needs-you count (when any), the second pointer (when any), then the best of Repeats and Growth. A hairline, an icon, one sentence of at most 12 words, a chevron. No cards, no hints. The third pointer is not drawn on Home; it is in the palette under "This week".
- Never on Home: a chart, a table, an interval, an n, the Monday note, "What your admin can see", the example-week selector, the data-mode line, the quote of the method. They move: Monday note to the palette ("Copy my Monday note"); admin visibility to Your data; the example-week selector to Settings under Demo; method to "Why this?".

Words above the fold: content 47 plus sidebar 17 = 64 (before: 173 plus 51 = 224). Controls: 1 primary, 2 rows, 1 disclosure, 5 nav, 1 More, 2 footer = 12 (before: 10 plus 18 = 28).

## States (shortest wording)

| State | Title | Body | Action |
|---|---|---|---|
| First week | Knack is learning your work. | Check back in a few days. | none |
| Nothing stands out | Nothing stands out this week. | No number moved far enough to matter. | none |
| Stale | These numbers are out of date. | Knack says nothing rather than something old. | Try again |
| Role changed | Your role changed. | Pointers start again, so you are not compared with your old role. | none |
| Could not load | Could not read your week. | Nothing was changed. | Try again |
| An approval blocks a job | The approval is the hero: its title, one line, "Cannot be undone." when true, [Approve and submit] [Reject], Evidence › | | The week's pointer becomes the first quiet row |
| Loading | (none; the hero area holds its height; "Reading your week" in muted 13 px after 600 ms) | | |

Several pointers: the hero is the highest-ranked one; the second is a secondary row using the same template shortened to 12 words. The engine already caps at three, and "Show the others" is not offered.
