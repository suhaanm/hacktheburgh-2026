# 05 Admin: Firm, Roles, Onboarding: before and after

Before screenshots: `before/admin-firm.png` (Overview). The Roles and Onboarding views were read at 1440 by 900 the same way (numbers in section 2 of `docs/KNACK_UX.md`).

## Before

```
 Firm                                                                         (eyebrow)
 Seven things to know                                                         (title)
 For coaching and onboarding, not for evaluating individuals.  (Admin view) (NAMES ARE MADE UP.
                                                                    THIS FIRM IS SYNTHETIC.)  (2 badges)
 Overview  Roles  People  Onboarding  Automation  Risk and coverage  Forecasts  Firm brief   (8 tabs)
 60 people in 3 roles. 57 have enough data for a trend.
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ ⚠ Worth a look                                                                    │  x7 cards,
 │   An approval has waited 72 hours.                                  [Open the numbers]│  each with an
 │   72 hours · n = 3 approvals · synthetic firm                                       │  eyebrow, a
 └──────────────────────────────────────────────────────────────────────────────────┘  facts line and
 ┌ ↗ Going well ... Approved routines handled about 10 hours of work in four weeks. ┐  a button
 ... five more
```

Roles view: three role cards side by side, each with a "SYNTHETIC FIRM" badge, a chart, a two-line sentence with an "A gap we can see" pill, and four habit rows each with another pill and an interval: 313 words above the fold, 5 pills. Onboarding: three charts with "SYNTHETIC FIRM" three more times: 284 words above the fold. The admin sees the synthetic origin in four different ways on one page.

## After (sidebar: Firm, Roles, Onboarding; the other five Firm views are in More and the palette)

```
 Firm                                                  ┌ Synthetic firm ┐  Admin view
 For coaching and onboarding, not for evaluating individuals.   (printed: a use limit)
 60 people, 3 roles. 57 have enough data for a trend.            (one line)
 ──────────────────────────────────────────────────────────────────────────────────
 ⚠  Juniors take about 20 seconds longer per case than experts, in both roles.        ›
    18.4 s (16.8 to 20.2), n = 29 people                          (muted, printed: admin)
 ──────────────────────────────────────────────────────────────────────────────────
 ⚠  An approval has waited 72 hours.                                                  ›
    n = 3 approvals
 ──────────────────────────────────────────────────────────────────────────────────
 ↗  Approved routines handled about 10 hours of work in four weeks.                   ›
    10.2 hours, n = 61 runs
 ──────────────────────────────────────────────────────────────────────────────────
 Show all 7                                                       Print the firm brief
```

Annotations:

- At most three rows by default (the three with the highest rank by the engine's own order), then "Show all 7". A row is the whole click target (chevron), so the "Open the numbers" button disappears from every row.
- "Worth a look" and "Going well" are not printed. The glyph carries polarity (warning triangle, rising arrow); a screen reader still gets the word ("Worth a look" as visually hidden text).
- n and the interval stay printed on admin screens (D45); they are the muted second line of the row, not a separate facts strip.
- One origin badge, "Synthetic firm", in the header. "Names are made up" is its Hint; it is not repeated on each card or chart. On Evidence and reviewer screens the full sentence stays printed.
- The tab strip is retired. The admin's three destinations are sidebar items; the rest are palette commands and rows in More: Firm: People, Automation, Risk and coverage, Forecasts, Firm brief.
- "Admin view" is a small text label, not a pill, and exists only while the View as switch is on. In a real deployment the role comes from identity and the label is not shown.

Roles, after:

```
 Roles                                                         ┌ Synthetic firm ┐
 Finished without help, experts and juniors, same 0 to 100% scale.
 ──────────────────────────────────────────────────────────────────────────────────
 Benefits processor              experts 94%  ●──        juniors 63%  ─●─       gap 32 points ›
 Data analyst                    experts 97%  ●─          juniors 59%  ─●─       gap 37 points ›
 Programmer                      Not compared yet: no expert in this role.
```

One row per role, a shared scale drawn as a thin dot-and-whisker strip. Opening a role expands in place: the four habits that explain the gap (name, seconds added with interval, one sentence), then People for that role (the People view is the drill-down, not a destination). No "A gap we can see" pill on each row; the polarity word is plain text only when it is "not clear".

Onboarding, after: one chart per role stacked as rows (a small multiple 120 px high), the median step to the target as the row's sentence ("Half reach the target by step 82"), n in the muted line. The legend is one line.

Measured target: Admin Firm 0 clicks (real role) or 1 (View as switch), Roles 1, Onboarding 1. At most 150 words above the fold on each.
