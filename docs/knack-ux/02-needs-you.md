# 02 Needs you (today's Queue, Briefing and routine proposals in one list): before and after

Before screenshot: `before/worker-queue.png`.

## Before (Queue, measured 1440 by 900)

```
 Queue                                                             (eyebrow)
 2 things need your approval                                       (title)
 Anything that cannot be undone, or reaches outside, waits here for one click.   [SYNTHETIC]
 ┌────────────────────────────────────────────────────────────────────────────┐
 │ Submit case note CN-2041        Waiting at an irreversible step · 7 Nov, 13:03│  mono, 11 px
 │ ( Cannot be undone )                                                          │  pill
 │ ┌──────────────────────────────────────────────────────────────────────────┐ │
 │ │ The three calculators agree. The note is written and waiting for your click│ │  grey box
 │ └──────────────────────────────────────────────────────────────────────────┘ │
 │ > Evidence                                                                    │
 │ [ Approve and submit ] [ Reject ]                                             │
 └────────────────────────────────────────────────────────────────────────────┘
 ┌─ (the second card, the same shape) ────────────────────────────────────────┐
 What ran while you were away                                      (a third section)
 1 run finished   2 waiting for you   0 failures   1 yield when you came back   (mono)
 Ran / benefits-workflow  ok  12 min  ( tier 2 ) ...
```

Measured: 157 words above the fold, 6 pills, 6 controls, 1169 px tall. Separate screens hold the other things that need a decision: Routines (proposals), Briefing (up to three prepared actions), Agents (paused runs). A worker who wants "what needs me" visits three screens.

## After (Needs you)

```
 Needs you                                                         (title, 22 px)
 ────────────────────────────────────────────────────────────────────────────
 ◔ Submit case note CN-2041                              13:03   (1 row = 44 px)
   The three calculators agree. The note is written, waiting for your click.   (2 lines max)
   Cannot be undone.                                                     (3)
   [ Approve and submit ]  [ Reject ]            Evidence ›              (4)
 ────────────────────────────────────────────────────────────────────────────
 ◔ Shadow run differed from yours                        13:04
   Calculator B gave 214 where your entry gave 241. Nothing was saved.
   [ Accept its answer ]  [ Keep mine ]                     Evidence ›
 ────────────────────────────────────────────────────────────────────────────
 ↻ Enter the household into three calculators         new routine     (5)
   Seen 58 times in 3 weeks. Could save 4 to 7 hours.                  (Hint: interval)
   Touches GovCalc and 3 more. It will never submit.
   [ Watch first ]  [ Not now ]  [ Never ]       More ways to say yes ›
 ────────────────────────────────────────────────────────────────────────────
 Since you were away: 1 run finished, 0 failed.            Details ›     (6)
```

Annotations:

1. One list, one row shape. The glyph says the kind (decision, routine, paused run, prepared action); the order is the attention table's order: safety, then time-sensitive, then the rest, newest first inside a class. At most 7 rows, then "Show all N".
2. A row opens by itself only when there are one or two rows; with more, rows are collapsed to title and time and open on click (so the list stays scannable). The first row is always open.
3. The consequence stays printed ("Cannot be undone.", "Reaches outside.") as plain text, never a pill, never behind a Hint. A row with the normal risk class prints nothing.
4. Buttons say what they do (existing labels, kept). The primary is never the destructive-looking one; Reject and Keep mine are secondary and equal in size.
5. A routine proposal is a row in the same list. Three equal buttons: Watch first (the opt-in, safe: it practises beside you, nothing saved or sent), Not now, Never. "More ways to say yes" opens inline: Run with my approval, Run while I'm away (its own switch and confirm on the card). Not now and Never weigh the same as Watch first. All four modes and the rung rules survive; only the layout changes.
6. The overnight report is one line; Details holds the tally, the ran/failed/yielded lists and the audit log.

Empty: title "Nothing needs you." Body: "Knack asks when a step cannot be undone." One line, no illustration, no action.

## Rules this screen proves

- One list for everything that waits on the worker. A badge in the sidebar, the menu bar and the Dock counts the same number.
- Approvals can only be a real click (no keyboard shortcut approves). Keys move focus (up, down), Space opens the evidence.
- A pending item that blocks a running job also appears in the corner card; this screen is where the decision is taken.
- Evidence (screenshots, found against expected, tier log, run id) is one tap away and printed in full when opened.

Measured target: 2 clicks from Home with several items, 1 click when Home's hero is the single pending item. At most 120 words above the fold with two rows open.
