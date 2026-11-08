# Needs you

> One list for everything that waits for a decision: approvals, paused runs, routine proposals, prepared actions.

**Capability:** Routines and automations · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** built (merged to main; seen in a harness and in hidden end-to-end runs; owner has not used it) · **Page:** `docs/features/needs-you.md` · **Targets:** Wordsmith

## What it does

Approvals, paused runs, routine proposals and prepared actions are one list with one row shape, so a worker looks in one place. A decision never costs an extra click to open: each row carries its own buttons.

## How it works

Order is the attention layer's: safety first, then time-sensitive, then the rest, newest first inside a class. Three rows show by default plus any safety or blocking row, then Show all. The consequence is printed as plain text ('Cannot be undone.'), never a pill or a Hint. Evidence (screenshots, found against expected, the tier log, the run id) opens in place. An approval can only be a real click: no keystroke, and no voice, approves anything. The same number is in the sidebar, the menu bar and the Dock badge.

**What is different.** Everything waiting for a decision is one list with one row shape, the consequence printed as plain text, and approval possible only by a real click.

## Where to see it

Needs you in the sidebar (second item); a blocking approval also appears as a corner card.

## Demo moment

Open Needs you with one approval and one routine proposal: 'Submit case note CN-2041. Cannot be undone.' Approve and submit (sandbox only), then the proposal's Watch first.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| The after-state prototype measures 103 words above the fold for three decisions (the old Queue had 157 for two), 12 controls, 0 pills, 0 paragraphs over two lines | design measurement of a static prototype, no users | `docs/knack-ux/after/after-measurements.json; docs/KNACK_UX.md (section 2)` |

## Honest limit

Measured as a prototype and checked in hidden runs, not by a person. Approvals in the demo are sandbox only. The default row count was cut to three after the first draft. Two gaps found by the demo run (docs/KNACK_DEMO.md, G11 and G6): approving marks the queue item approved but nothing in the dashboard or the desktop calls the route that presses the real submit button, so the sandbox note stays Draft until it is called; and the corner approval card names no item, so Review opens Needs you with the newest item on top.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: the human decision point of an approval-gated agent

## 30-second spoken script

> Everything waiting for you is in one list. An approval, a run that paused for safety, a proposed routine, a prepared action. Each row has its own buttons, so a decision never costs an extra click. If something cannot be undone, it says so in plain text. And an approval is always a real click: no key and no voice can approve anything.

## Slide bullets

- One list, one row shape: approvals, paused runs, proposals, prepared actions.
- Each row carries its own buttons; evidence opens in place.
- 'Cannot be undone.' printed, never hidden behind an icon.
- An approval is a real click; no key or voice approves.
- Same count in the sidebar, menu bar and Dock.

## Sources

- `docs/knack-ux/02-needs-you.md`
- `docs/KNACK_UX.md (sections 3, 4)`
- `docs/ATTENTION_DESIGN.md`
- `docs/knack-ux/after/after-measurements.json`
- `docs/FIX_LEDGER.md (section H)`

## Related pages

`routines.md`, `attention-router.md`, `security-layers.md`
