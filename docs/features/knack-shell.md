# One app, one window, one pill, a short first run

> Knack is one app: a calm window, a menu-bar item, and a small corner pill that says what is happening in five words and offers Stop.

**Capability:** A calm product: window, attention, context · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Navigation note (on main since 02:05 UTC).** The lead's views rule (`docs/knack-ux/views.md`) is implemented: a worker has five sidebar rows (Home, Needs you, Routines, Growth, Your data); Growth is one page with the sections My progress, Where my time goes, My steps, How my routines connect and My commits; the Admin view has Firm, Brief, Forecasts, Roles, People, Onboarding, Automation and Risk, then More: Models and cost, Evidence, Background runs. Old addresses redirect (`apps/dashboard/src/routeRedirects.ts`). The final list is `apps/dashboard/src/components/home/navModel.ts`. The account menu (name and role, View as, Settings with Connections and Advanced, Set up again, Change role) is on main in the dashboard shell (owner requests 4.8 and 4.9).

This page covers One app, one window, one corner pill, First run: role, three consents and a check, Command palette and keyboard.

## One app, one window, one corner pill

**Status:** built (merged to main; hidden end-to-end run passes; first visible launch with the owner pending) · **Page:** `docs/features/knack-shell.md` · **Targets:** Wordsmith

### What it does

Knack.app is the dashboard in its own window with a Dock icon and a menu-bar item. When a run that uses the worker's real screen starts from the window, the window minimises itself and a 32-pixel pill in the bottom-right corner says what is happening and offers Stop. It never pops the window back on its own. (The state table says a pure sandbox job leaves the window where it is. Routines, Run now is specified to minimise it, but the demo run found that a run in the agent's own browser shows the pill and does not move the window, because the shell treats only the desktop's own acting as 'real screen' (gap G3 in docs/KNACK_DEMO.md); until that is decided, Command-M does it by hand.)

### How it works

Window: 80% by 84% of the work area, centred, remembered per display; closing hides it; the Dock icon brings it back; quitting while a job runs asks first. The pill sits bottom-right, 16 pixels from the edges, holds a label of at most five words, and is never over a password or payment field. Only one interrupting surface shows at a time, and an approval raises a card, never a modal. A pure state machine of 18 transitions decides what the window and pill do, with kill always winning. The app starts its own engine and agent: live models if a Gemini key is present, example data otherwise, with a status line that says which. Settings (Command-comma) holds Use live models, Interruptions (Rarely, Balanced, Often), Coaching, Move aside while Knack works, Open at login, Appearance and Views. Unsigned local app and dmg build with electron-builder; a signed release needs the owner's Apple Developer ID.

**What is different.** Only one interrupting surface shows at a time, the pill is a status and not an interruption, and the window never pops back on its own.

### Where to see it

The app itself: window, Dock icon, menu bar, corner pill. The sidebar status line reads Live models or Running with example data.

### Demo moment

Start a routine from Routines: the window minimises to the Dock after 0.4 s, the pill reads what Knack is doing and shows Stop; when it finishes the pill becomes a check, fades, and Needs you shows the result. The window does not come back by itself.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Sidebar rows 9 to 6 and sidebar words 51 to 17 on Home; the 18 window and pill transitions are each a test | design measurement and offline tests | `docs/KNACK_UX.md (sections 2, 7); docs/knack-ux/shell-transitions.json` |
| A hidden run of the real Electron app with stand-in services checks the window size, the corner column (bottom-right, 16 px, card above pill, secure-input hold, Review, done, error, voice, Stopped, resume) and writes a picture of each page | offline hidden check; no real input or capture | `apps/desktop/KNACK_BUILD.md` |

### Honest limit

Not yet seen by the owner on a real desktop with real windows behind it; the corner approval card carries fixed words only and names no item (gap G6); per-display overlays for the ring are a known limit; multi-display pill placement is a spec, not a tested behaviour. The app is unsigned.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: an agent that works in the background and tells the worker in five words

## First run: role, three consents and a check

**Status:** built (owner decision D58; on main since 02:39 UTC (d9f8929): a role screen, one consent card each for capture, screen glances and voice, and a 'Check it works' screen; the spoken 'Say Hey Knack' Try it step in docs/knack-ux/capabilities-and-permissions.md is not a screen on main (the check screen shows Hey Knack's listening state and a Show me ring instead); not seen end to end by the lead) · **Page:** `docs/features/knack-shell.md` · **Targets:** G-Research

### What it does

First launch asks for a role (a card per role pack, or 'Not sure yet', which picks nothing), then shows one consent card each for capture, screen glances and voice (the last two only where the desktop app can act on them), each with Yes, Not now and Never of equal weight and none pre-selected, then a 'Check it works' screen: the macOS permissions as they are (never a wall: each says what will not work without it), Hey Knack's listening state, and Show me, which draws the annotation ring on a sample. Then 'Show my week'. Every screen has a Skip and skipping picks nothing. Everything else takes the role pack's safe defaults and is editable in Your data.

### How it works

When the second screen is done, the pack's tools, risky actions set to 'never without me', tone, gradual pace and hours are written to the memory file; capture is on only if the worker said Yes. 'Not now' asks again once after a week and 'Never' never asks again; the answers are remembered on the device and an unfinished first run resumes where it stopped. Back is the only way back, and not while the file is being written. With the connection chips for the chosen role (every chip off; only Connect turns on the Example version) there is one more click. A consent is a real click on a card, recorded by the code that handles the click; the first-run file itself never consents to anything.

Permissions are asked one at a time and in context, Screen Recording only when screen glances are on and Knack is asked to find something outside Knack, Accessibility only for 'click for me' after the first supervised test, and Input Monitoring, Automation and Full Disk Access never; a missing permission or key is never silence, it is a card or a status line in plain words with a button that opens the fix (docs/knack-ux/capabilities-and-permissions.md).

**What is different.** Two questions and one summary, with a consent whose three buttons weigh the same.

### Where to see it

The first window on first launch (no sidebar yet). Account menu, Set up again, reruns it; Account menu, Change profile, changes the name and the role.

### Demo moment

Launch fresh: the role cards (and 'Not sure yet'), the three consent cards with Yes, Not now and Never, then 'Check it works' with the permissions as they are and Show me, then Home. The count from the code: 1 click for the role, one answer per consent card and one for 'Show my week', so 3 clicks with capture only, 5 in the desktop app, 6 with connection chips.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The click count is computed by the first-run model (clicksToHome) and covered by its tests; the spec measured about 20 clicks over 15 screens for the old set-up and 159 words on its first screen against 20 after | design measurement of a prototype and unit tests; nobody has done it | `apps/dashboard/src/screens/FirstRun/model.ts; docs/knack-ux/07-first-run.md; docs/knack-ux/after/after-measurements.json` |

### Honest limit

Measured as a design and by the reducer's tests; no person has done it. The permission dialogs (Accessibility, Screen Recording, Microphone, Speech Recognition) can only be granted by the owner in System Settings, and the Hey Knack side of the first conversation (a fixed welcome line and a ring on the Needs you row) is specified in the capabilities document and built in the desktop wake code, but there is no separate Try it screen for it on main.

### Hackathon target

- **G-Research (make the invisible visible)**: nothing recorded without a plain, equal-weight yes

## Command palette and keyboard

**Status:** built (shortcuts and the palette are on main; some of the spec's palette verbs are not) · **Page:** `docs/features/knack-shell.md` · **Targets:** Wordsmith

### What it does

Command-K goes anywhere or runs a command, Option-Space asks Knack (hold to talk), and Option-Shift-Command-K stops everything. No keystroke ever approves anything.

### How it works

In the dashboard today: Command-1 to Command-5 go to the five destinations, Command-comma opens Settings, Command-slash opens About this screen, Shift-Command-K stops everything while Knack is frontmost (a test says no key reaches an approval). Command-K opens the palette, which lists every screen and these actions: Take the tour, Switch to the Admin view (and back) and Print the firm brief. In the desktop: Option-Space (hold to talk), Option-Shift-Command-K anywhere to stop, Option-Command-P to pause or resume for an hour. The spec adds further palette verbs (Pause for 1 hour, Stop everything, Ask Knack, Copy my Monday note, Explain this screen and a palette-only 'Delete my data' with no shortcut by design); they were not on main when this was written. A guided tour of the five destinations is one row in the account menu.

**What is different.** Nothing new is claimed; the one deliberate rule is that no keystroke can approve anything.

### Where to see it

Anywhere in Knack; the palette is Command-K.

### Demo moment

Press Command-K, type the name of a screen and press Return; then press Command-2 to jump to Needs you. Say that no key approves anything.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| No measurement; the click budgets for the ten jobs are tested by a replay script | offline tests | `docs/knack-ux/jobs.json; docs/KNACK_UX.md (section 9)` |

### Honest limit

The tap-to-type Ask bar is a lower-priority item in the build plan and may not be complete; the palette verbs named above are specified, not all built.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: reaching any action without a menu hunt

## 30-second spoken script

> Knack is one app. A calm window with five destinations, a menu-bar item, and when an agent starts working on your real screen, the window gets out of the way and a small pill in the corner says what is happening in five words and offers Stop. It does not pop back on its own. First launch is a short first run: your role, a consent card for each of capture, screen glances and voice with three equal buttons, a check that it works, and a first look at your week.

## Slide bullets

- One app: window, Dock, menu bar, corner pill; five destinations.
- Window minimises when an agent works; the pill says it in five words and offers Stop.
- One interrupting surface at a time; never over a password field.
- First run: a role, three equal-weight consent cards and a check that it works; the old set-up took about 20 clicks over 15 screens.
- No keystroke ever approves anything.

## Sources

- `docs/KNACK_UX.md`
- `docs/knack-ux/08-window-states.md`
- `docs/knack-ux/07-first-run.md`
- `docs/knack-ux/capabilities-and-permissions.md`
- `docs/knack-ux/shell-transitions.json`
- `apps/desktop/KNACK_BUILD.md`
- `docs/DECISIONS.md (D51)`
- `docs/FIRST_LAUNCH.md`

## Related pages

`stop-everything.md`, `attention-router.md`, `connections.md`, `your-data.md`
