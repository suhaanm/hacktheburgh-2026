# Design audit (7 Nov 2026, DESIGN-SYNC track)

What was cluttered on every screen, what was done, and what was handed to the owner of each screen. Rules applied are the ten in `packages/design/README.md` ("Rules for new components"); the reconciliation of tooltips is D45 (`docs/DESIGN_DIFF.md` section 7). Screenshots: `apps/dashboard/qa/design-sync/before/` and `.../after/` (demo-fixture mode, full page, `<screen>-<light|dark>-<1440|390>.png`, all nine edited screens in all four variants). Measured with a script on the demo fixtures at 1440 (words in the main column, paragraphs over two lines, `title=` attributes, pills, page height).

## Edited here (the nine finished screens)

| Screen | Words | Paragraphs over 2 lines | `title=` | Pills | Height (1440) | What changed |
|---|---|---|---|---|---|---|
| Genome | 1097 to 902 | 8 to 7 (all 7 are the Explain panel, DASH-LIVE) | 5 to 0 | 7 | 3733 to 3472 | Lede from 3 lines to one with the 95% interval behind a Hint; three printed n/split/interval footers became one "About this data" each (origin badge stays visible); the two skipped-step notes and the per-step consequences list sit in a closed "What skipping a step costs"; "Change the comparison" shortened; slider caption one line; legend shortened (the hatched item now says a skipped step counts as time saved) |
| Growth | 1075 to 812 | 10 to 6 (5 are the skill rows' button text, 1 a card sentence) | 14 to 4 to 0 | 11 | 3423 to 3021 (390 px: 6097 to 4840) | Chart readout is one line (interval, n, help level, cue behind a Hint; the full sentence stays in a live region for screen readers); chart footer is "About this data"; the three measure cards show title, figure and an interval bar, with the definition behind a Hint on the title and the interval and bar scale behind a Hint on the figure; trend and independence intervals behind Hints; "How to read these numbers" and "Limitations" are one closed disclosure; ledger and offloaded paragraphs one line; offloaded list shows 5 then "Show all 8"; mono capital labels now sentence case |
| Presence | 369 to 232 | 1 to 0 | 3 to 0 | 3 | 1703 to 1534 | Lede one line; footers became "About this data"; idle-capacity interval and definition behind a Hint (the interval bar stays); forecast and quiet-hours text one line each, the away-run reminder behind a Hint |
| Graph | 141 to 105 | 1 to 0 | 2 to 0 | 2 | 1115 to 1046 | Uses the friend's three node colours (`--node-routine/skill/memory`) with automation in ink; lede one line; footer "About this data"; the strength explanation behind a Hint. The node shapes already encode the type, so the glyph-in-node idea was not needed here |
| Routines | 615 to 464 | 2 to 0 | 5 to 0 | 9 to 5 | 2851 to 2467 | The default "Not decided" and "A0" pills are gone (a pill shows only when the state is not the default); "What I saw" is one sentence, the rest sits in "Why this?" beside the rung explanation; "How often" minutes and the hours-saved interval and money behind Hints (the interval bar stays); "It touches" is a sentence with "+N more", "It will never" is printed whole on one line; the four choices keep their one-line explanations (shortened), so Not now and Never are still as easy as Yes |
| Queue | 284 to 270 | 0 | 15 to 0 | 27 to 17 | 1935 to 1836 | Lede one line; each card has one pill, only when the risk is not "Review"; the kind moved into the muted time line; run and routine ids moved into the Evidence disclosure; audit log uses the shared disclosure |
| Today | 75 to 62 | 0 | 2 to 0 | 1 | 900 | "Why this" uses the shared disclosure; the fading explanation is a Hint on its label; the level chip lost its tooltip |
| Memory | 332 to 308 | 1 to 0 | 2 to 0 | 8 to 7 | 1721 to 1674 | Lede shortened with the "web page text can never change it" sentence behind a Hint; full path behind a Hint; rule explanation one line plus a Hint; the version and status pill appears only when the status is not "proposed" |
| Onboarding | 145 to 142 | 0 | 0 | 0 | 900 | Already one idea per screen; two helper lines removed or shortened; the progress label is sentence case |

Honesty check on these: origin badges are visible on every chart footer (`ChartFoot variant="about"` keeps the badge outside the disclosure); every printed n, split and interval level is still one click away (About this data, or a Hint beside the figure) and still printed on Evidence; the limitations disclosure on Growth is one click away; "It will never" and the consent choices on Routines are fully visible.

## Shared code touched (additive, backward compatible)

`components/common.tsx`: `ChartFoot variant="about"` (default unchanged), `SourceNote also=...`, no `title=` on OriginBadge, ExampleBadge, RungPill, TierPill and CheckChip (visible text plus screen-reader text instead). `components/ui.tsx` and `components/Hint.tsx` are new. `lib/graph.ts`: node colours point at the new tokens (DASH-LIVE's folder; four constants).

## Screens applied by their owners from the change lists (measured at 19:40, demo fixtures, 1440)

| Screen (owner) | Words | Paragraphs over 2 lines | `title=` | Pills | Height | Notes |
|---|---|---|---|---|---|---|
| Week (DASH-LIVE) | 788 to 494 | 4 to 0 | 6 to 0 | 24 to 12 | 3309 to 2655 | lede, "gap" line, intervals in "About this data", suggestion = first sentence + "How this was worked out" |
| Git habits (DASH-LIVE) | 409 to 291 | 2 to 0 | 3 to 0 | 15 to 9 | 1722 to 1501 | counts behind a Hint, no suggestion pills |
| Briefing (DASH-LIVE) | 486 to 391 | 1 to 0 | 2 to 0 | 12 to 3 | 2313 to 2039 | risk pill only when not Normal, one muted "From ..., expires ..." line, consequence of a non-normal card stays printed |
| Agents (DASH-LIVE) | 434 to 274 | 1 to 0 | 2 to 0 | 17 | 2325 to 2184 | nearest-limit budget by default, "Budget, lease and tools" disclosure, 5 helpers then "Show all" |
| Models (DASH-LIVE) | 634 to 480 | 2 to 0 | 10 to 0 | 3 | 3124 to 2864 | fallback rule in a Hint beside the job name, sentence-case chain labels |
| Privacy (DASH-LIVE, honesty lines restored by DSN) | 634 to 469 | 2 to 0 | 10 to 0 | 28 to 4 | 2791 to 2464 | one-line lede, frame note once, one muted meta line per row, 7 rows then "Show all" |
| Evidence (DASH-LIVE) | 6051 to 5947 | 54 to 48 | 197 to 0 | 126 | 19304 to 19019 | 2-line lede, map first view, tabs sentence case; the page stays long on purpose (it prints everything a reviewer needs) |
| Genome Explain panel (DASH-LIVE) | Genome 1097 to 672 | 8 to 3 | 5 to 0 | 7 | 3733 to 2897 | three sentences visible, "where this comes from" as a Hint, limits and "all the numbers" in closed disclosures |
| Notices (DSN, taken over) | 474 to 370 | 1 to 0 | 2 to 0 | 3 | 2653 to 2351 | one-line lede, one example-data line, the "what does this setting do" sentence is a Hint on each kind |
| Home, Firm, Predictions, palette, tour (ADMIN-UI) | Home 164 words, one hero with three pointers; Firm "seven things to know"; Predictions 591 | 0, 0, 2 | 0, 0, 2 | 2, 0, 11 | Home 1084 | Built on InsightCard, Hint, Details and the shared tables; looked at in light and dark at 1440 and 390 (Home, Firm, palette fine; Predictions' baseline subtitle is 3 lines and 2 `title=` remain: small fixes left to ADMIN-UI) |
| Repeats (HITLIST) | 219 words | 0 | 0 | 5 | 958 | calm; three small fixes sent (one-line lede, one-line footer, move "Start counting again" into the disclosure) |
| Desktop shell (DESKTOP-2, copy edits by DSN) | n/a | n/a | n/a | n/a | n/a | long hints and consents shortened (Settings, Onboarding mic-denied, Files, Gemini consent), eyebrow labels sentence case; dock itself was already calm |

## Honesty statements restored after the first pass (smoke test, 19:33)

The smoke test caught four honesty statements that the first pass had moved behind closed disclosures or Hints, so their text was no longer on the page. They were put back in short form, visible, with the detail still in the disclosure: (1) Evidence map: "Simulated participants are language models playing workers. They are not people." is a visible line under the map; (2) Privacy: the canary reading ends "That is evidence from a test, not a proof." and the engine's scope note ("Calls for steps you asked for are listed too") is printed; (3) Explain: "These are example answers. They do not change with what you ask." prints in the same paragraph as the example-data line (`SourceNote alsoInline`); (4) Explain: a visible "Checked by code against the data. That shows the words come from the data, not that the data is right." under the provenance pills. A fifth catch: the engine's sentence on an example-data note was behind a Hint for every kind, which hid "this feature is switched off, start it with ...=1" and engine errors; those two kinds now print in full (`SourceNote`). Rule recorded: a Hint never holds the only copy of an instruction, an error, a limit or an origin (D45). No smoke assertion was loosened; checks changed only to open a disclosure where the text is one tap away by design.

## Where the friend's rules conflicted with the honesty rules, and how it was resolved

1. **n and the interval behind a hover with no fallback** (the friend's "How was this measured") against "every chart shows its n and its interval": resolved by D45. On worker screens they sit behind a Hint beside the figure or one "About this data" disclosure that works by keyboard, tap and screen reader; on admin screens, Evidence and the limitations register they stay printed; the origin badge is never hidden.
2. **"It will never" cut to one word plus "+2 more"** on the routine card: kept whole on one line (the safety promise must be readable without a click).
3. **The routine card's "Why this?" deleted and its three equal choices replaced by a drop-down plus Confirm**: kept our three labelled buttons and "Why this?" (the select hides the options and adds a step, against "Not now and Never as easy as Yes").
4. **Ribbon bubbles replacing the red bars**: the bubble drops the per-step whisker (the interval across the references), so the bars with whiskers stay; the friend's play-through already existed in Genome.
5. **Hover-only node names and a hold-to-approve button**: node names show on focus, on tap and when selected; hold-to-approve is allowed only on an irreversible step in a pop-up and never as the only path.
6. **Automation nodes recoloured to ink** against "`--good` means automation": confined to the graph (a glyph or shape carries the type), `--good` keeps its meaning everywhere else.

## Still to do

Small ones: ADMIN-UI (Predictions subtitle and two `title=`), HITLIST (three Repeats fixes), CUE-UX (cue chip `title="Dismiss (Esc)"`, `text-transform: uppercase` in cue.css and hud.css). Final smoke, tsc and vitest counts are in the track's final report.
