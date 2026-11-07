# 08 The window, the pill and the menu bar as one machine

One app, `Knack.app`. It has a Dock icon always, a menu-bar item always, one main window (the dashboard) that comes and goes, one corner column (a pill and at most one card), and the older coach layers (ring overlay, Cue panel) underneath. This file is the state machine; `docs/KNACK_UX.md` section 7 holds the numbers and the list of code that changes.

## Three regions that move independently

```
 WINDOW    absent ──open──▶ open ──minimise──▶ minimised ──dock click──▶ open
              ▲               │ close (red, Cmd-W)                          │
              └───────────────┴─────────────────────────────────────────────┘
 CORNER    none ◀──▶ pill ◀──▶ pill + card        card only: stopped, error (always visible)
 ACTIVITY  idle ──▶ working ──▶ done ──▶ idle        working ──▶ error    any ──kill──▶ stopped ──resume──▶ idle
                     │  voice (listening, thinking, speaking) uses the same pill
```

## Launch

```
 not running ──launch (first)──▶ FIRST RUN ──3 clicks──▶ IDLE, window open on Home
             ──launch (returning, by hand)──▶ IDLE, window open on Home at last size and place
             ──launch at login──▶ IDLE, no window (menu bar and Dock icon only)
```

On every launch Knack starts its engine (7700) and agent (7710) as child processes, polls health, shows nothing until three seconds have passed, then a quiet "Starting Knack, about 20 seconds" in the content area. On quit it ends both. If a service is already listening on its port (a developer started it), Knack uses it and does not stop it on quit.

## Transitions (the table the implementer builds the state reducer from)

| # | Event | Window | Corner | Menu bar | Dock |
|---|---|---|---|---|---|
| 1 | Run starts and uses the real screen, and the main window is focused | minimise itself after 400 ms (to the Dock, not hide) | pill appears, first label "Starting" | working dot | icon stays, no bounce |
| 2 | Run starts, window not focused (open behind, minimised or closed) | unchanged | pill | working dot | unchanged |
| 3 | Run is a sandbox job (Agents, background) | unchanged | pill | working dot | unchanged |
| 4 | Progress | unchanged | pill label (at most 5 words) and "n of m" when known; no animation | unchanged | unchanged |
| 5 | A decision blocks the run (approval, blocked target, paused for safety) | unchanged, never restored by itself | one card above the pill (priority table below) | count "1" | badge 1 |
| 6 | Worker clicks Review on the card | restore or open and focus, on Needs you at that item | card closes | unchanged | badge unchanged |
| 7 | Run finishes without needing anything | unchanged (it does not pop back) | pill turns into a check for 2.5 s, fades in 240 ms, window hidden | dot off | unchanged |
| 8 | Run fails or stops on its own | unchanged | pill turns error and stays until acknowledged, then a marker | count or marker | badge if it needs a decision |
| 9 | Kill (Option-Shift-Command-K, pill Stop, menu Stop everything, Command-Shift-K in the app, Shift-Esc in the window) | in-window banner "Stopped at 14:03. Nothing will run." with Resume, no restore | "Stopped" card replaces the pill until Resume | square | unchanged |
| 10 | Resume | banner off | card off | idle | unchanged |
| 11 | Hold Option-Space (voice) | unchanged | pill "Listening", then "Thinking", "Speaking"; End instead of Stop | unchanged | unchanged |
| 12 | Tap Option-Space | Ask bar opens (a separate small window, not the main one) | cards held while it is open | unchanged | unchanged |
| 13 | Worker returns after 30 minutes away | unchanged | the digest as one card, once ("While you were away: 2 runs finished, 1 needs you") | count | badge |
| 14 | Close (red button, Command-W) | hide (renderer kept alive for a fast reopen) | unchanged | unchanged | icon stays |
| 15 | Minimise (yellow, Command-M) | to the Dock | unchanged | unchanged | icon stays |
| 16 | Dock icon click, or Activate | open, restore from the Dock, or bring to front; at last size and place; Home | unchanged | unchanged | unchanged |
| 17 | Quit (Command-Q, Dock menu, menu bar) | if nothing is running, quit; else a sheet: "Knack is working. Stop it and quit? [Stop and quit] [Keep working]" | pill stays until the choice | | |
| 18 | Quit while an away-routine is scheduled in the next 24 hours | sheet adds one line: "Routines set to run while you are away will not run until you open Knack." | | | |

Rules inside the table:

- Rule 1 applies only to runs that click or type on the worker's own screen or browser. A sandbox job never moves the window.
- Rule 1 is the setting "Move aside while Knack works" (on by default). Off: the window stays and the pill still shows.
- The window never restores itself except through row 6 (the worker clicked Review). A result that needs a look raises the badge and the Needs you list; it does not interrupt.
- Closing the window never quits, never hides the Dock icon, never stops a run. Quit is the only way out, and it stops the run only after the worker agrees.

## Corner priority: one interrupting thing at a time

The corner column holds at most one pill and at most one card. A card is any interrupting surface: the order below decides which one is drawn; the others wait or are dropped by the attention router's own rules (docs/ATTENTION_DESIGN.md).

| Priority | Surface | If it loses |
|---|---|---|
| 1 | Stopped card (kill) | never loses |
| 2 | Safety card (injection pause, irreversible decision) | never loses; replaces a lower card |
| 3 | Approval that blocks a running job | waits (held), badge shows |
| 4 | Time-sensitive card (blocked run, deadline) | waits for a natural break, one reminder |
| 5 | Digest card (morning, return) | held to the next break |
| 6 | Cue card or chip with no on-screen target (it would dock in a corner) | dropped (Cue is a "now" item) |

Cue cards anchored to an on-screen target are part of the annotation layer, not the corner column. They are dropped (reason `agent_acting`) while Knack is acting for the worker, and while any corner card is up. The Ask bar, while open, holds every card except priority 1 and 2.

Passive markers that never count as a surface: the pill (it is a status, not an interruption), the ring on a target, the menu-bar state, the Dock badge, the in-window banner.

## What shows where (the full set of surfaces after the merge)

| Surface | Today | After |
|---|---|---|
| Main window | none: the dashboard is a browser tab opened from the menu bar at the Today screen | the dashboard, 80% by 84% of the work area, centred, remembered |
| Dock panel (chat, profile, files, settings, set-up) | 320 by 64 or 360 by 580 always-on-top panel, bottom-right | not drawn. A hidden window stays only as the host of the microphone and the Live voice audio until that code moves. Its jobs: chat becomes the Ask bar and the voice pill; profile becomes Your data; settings become Settings; files become Settings, Folders; set-up becomes first run |
| Corner pill and card | the HUD: Stop pill, proposal card, notice card, bottom-left | one corner column, bottom-right (HUD, extended) |
| Permission prompt (confirm) | separate toast window, top-right, 400 px | a card in the corner column (priority 3); the answer is still a real click validated by the confirm broker |
| Ring overlay | full-screen, click-through | unchanged; annotation only; hidden while the Knack window is focused; no label while the agent acts |
| Cue panel | chip and card beside the target, bottom-corner fallback | unchanged beside a target; the fallback uses the corner column |
| Ask bar | none | new, 560 by 64, upper third, centred, closes on blur or Esc |
| Menu bar item | up to 17 rows; a click shows or hides the dock panel | 8 rows; a click opens the menu |
| Dock icon | present, does nothing on click | present, restores the window, badge and menu |

## Menu bar menu (8 rows; a ninth, the glance state, only while a glance mode is on)

```
 Knack is working: filling in calculator B        (status line; "Idle" when idle; one line)
 1 thing needs you                                 (only when true; opens Needs you)
 ────────────
 Open Knack
 Ask Knack…                              ⌥Space
 Pause for 1 hour                        ⌥⌘P     (becomes "Resume now")
 Stop everything                         ⌥⇧⌘K    (becomes "Resume after stopping")
 ────────────
 Settings…                               ⌘,
 Quit Knack                              ⌘Q
```

Screen glances (off, when stuck, now and then) are a setting in Your data. A status row under the first line says "Screen glances: off" (or the mode) only while a glance mode is on, so the privacy state is visible without opening anything.

## Dock menu (right-click the Dock icon)

`Needs you (n)` (when n is above 0), `Pause for 1 hour`, `Stop everything`. Nothing else; the Dock never bounces.
