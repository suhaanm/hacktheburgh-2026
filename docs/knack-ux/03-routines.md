# 03 Routines (today's Routines and Repeats in one place): before and after

Before screenshot: `before/worker-routines.png`. Today a routine reaches the worker in three ways: the HUD proposal card (the corner), the Routines screen (a proposal card with four choices), and the Repeats page (the ranked list of repeated actions).

## Before (Routines, measured 1440 by 900)

```
 Routines                                                         (eyebrow)
 2 routines are waiting for your decision                         (title)
 Suggested between tasks. Nothing runs until you say so.          [SYNTHETIC]
 ┌──────────────────────────────────────────────────────────────────────┐
 │ Enter the household into three calculators                           │
 │ Enter the household into all three calculators and read back each    │  2-line sentence
 │ result, then stop.                                                   │
 │ ───────────────────────────────────────────────────────────────────  │
 │ How often (i)                 Hours saved                            │
 │ about 58 times in 3 weeks     4.0 to 7.0 h over 4 weeks (i)  ▬▬|▬▬   │
 │ It touches GovCalc, Quick Estimator +2 more                          │
 │ It will never submit, submit to claimant record                      │
 │ [Not now]            Ask me again later.                             │
 │ [Never for this]     Stop suggesting this.                           │  4 buttons,
 │ [Watch first]        It practises beside you. Nothing is saved or sent.│ 4 sentences
 │ [Run with my approval]  It works in the background and asks before ...│
 │ > Why this?                                                          │
 │ ┌ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ┐  │
 │ ¦ ▸ Separate choice  Run while I'm away (off)                      ¦  │  dashed box
 │ └ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ┘  │
 └──────────────────────────────────────────────────────────────────────┘
```

183 words above the fold, 9 controls, page 1596 px tall. The same four-way decision is drawn again in the HUD card, in a different order and with different words.

## After

The decision itself lives in Needs you (see `02-needs-you.md`): three equal buttons and "More ways to say yes". Routines is the place to manage what already exists, plus the ranked "could automate" list.

```
 Routines                                                         (title, 22 px)
 [ Running 3 ]  [ Could automate 2 ]                              (two tabs, 2 words)
 ────────────────────────────────────────────────────────────────────────────
 Enter the household into three calculators                       (row, 44 px)
   Watching: 12 of 20 practice runs match.        Asks first ›    (state in words)
 ────────────────────────────────────────────────────────────────────────────
 Copy the agreed results into the case note
   Asks before it submits.                        Runs while away ›
 ────────────────────────────────────────────────────────────────────────────
 ...   (at most 7 rows, then Show all)

 Opening a row expands it in place:
   It touches GovCalc, Quick Estimator and 2 more. It will never submit.
   Autonomy: [ Watching ] [ Asks first ] [ Runs on its own ]    (one segmented control; a step up
                                                                 is offered only when the record earned it)
   [ Run now ]  [ Pause ]  [ Stop for good ]                      (Run now: window moves aside, pill shows)
   Record ›     Run while I'm away: off  [switch]
```

`Could automate` is today's Repeats page, one row per repeated action, ranked by minutes saved a week (the engine's ranking is kept):

```
 Read the case, then open the calculators          about 25 min a week   Automate ›
 Copy results into the case note                    about 18 min a week   Automate ›
 ... at most 7 rows, then "Show all N"
```

"Automate" opens the existing inline "Watch first" peek (never runs anything). The interval and n stay behind the Hint beside the figure (D45). Hidden and "Already automated" folds stay, in a single "More" disclosure.

## Rules this screen proves

- The word "rung" and the codes A0 to A2 leave the default view. The state in words: Watching, Asks first, Runs on its own (and "while I'm away" as its own switch). The code is in Details for reviewers.
- Revoke is renamed "Stop for good" and keeps its confirm (inline, two clicks). Pause is the cheap reversible one. Proposed: if the engine has no pause state, ship without the button rather than inventing one.
- A step up the autonomy control is enabled only when the record earned it (the existing skill gate); a disabled step says what it needs ("Needs 8 more matching practice runs"), printed, not in a Hint.
- "Run now" (starts the routine in its current mode; the implementer checks that the engine or agent has the endpoint, otherwise the button is not drawn) is the only way the worker starts a routine from the window. It minimises the window (section 7) and shows the pill.
- A routine row never shows more than one sentence and one state. Everything else is behind the row.

Measured target: Home to a routine decision is 2 clicks (Needs you, then a choice); to manage a running routine 2 clicks (Routines, open the row). At most 100 words above the fold.
