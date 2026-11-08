# One app, one window, one pill, a short first run

> Knack is one app: a calm window, a menu-bar item, and a small corner pill that says what is happening in five words and offers Stop.

**Capability:** A calm product: window, attention, context · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Navigation note (landing).** The lead's views rule (`docs/knack-ux/views.md`, from owner requests 4.1, 4.2, 4.11, 4.12 and 4.17 at about 00:50 UTC) is reorganising where screens live. Where this page says 'More, <screen>', check `apps/dashboard/src/components/home/navModel.ts` on main for the final place. The account menu holds the worker's name and role, View as, Settings (including Connections and Advanced), Set up again and Change role (owner requests 4.8 and 4.9, landing).

This page covers One app, one window, one corner pill, First run: role, consent and a first look, Command palette and keyboard.

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

## First run: role, consent and a first look

**Status:** built (the spec is three clicks; decision D58 (00:45 UTC) adds a permissions step and a Try it step, still landing) · **Page:** `docs/features/knack-shell.md` · **Targets:** G-Research

### What it does

First launch asks two questions and shows one summary: a role card, one capture consent, and 'Show my week'. Everything else takes the role pack's safe defaults and is editable in Your data. Decision D58 (owner, after the first launch showed the old eight-step wizard) makes this the only onboarding: it opens on the first launch whatever the engine knows, adds three equal consent cards, a permissions step (microphone, speech, screen) and a Try it step, and the legacy wizard never renders in the Knack shell.

### How it works

Click 1 picks a role (three cards from the packs); the pack's tools, risky actions set to 'never without me', short tone, gradual pace and hours are written to the memory file. Click 2 is the one consent: 'It records when you are active, never what you read: no page text, no URLs, no field values. The record stays on this laptop.' Yes, Not now and Never have equal weight; Not now asks again once after a week; Never never asks again. Click 3 shows four plain lines from the file just written and opens Home. Screen glances, the microphone, Accessibility, Screen Recording and Open at login are each asked once, in context, when first needed. The role card will also offer connection presets (landing), which adds one click.

**What is different.** Two questions and one summary, with a consent whose three buttons weigh the same.

### Where to see it

The first window on first launch (no sidebar yet). Settings, Set up again reruns it.

### Demo moment

Launch fresh: role card, the consent with three equal buttons, 'Here is what Knack will remember', then Home with the example insight badged Example data.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| In the spec: about 20 clicks over 15 screens before; 3 clicks after. Words on the first screen 159 to 20. D58 adds steps, so the shipped count is higher and has not been re-measured | design measurement of a prototype | `docs/knack-ux/07-first-run.md; docs/knack-ux/after/after-measurements.json` |

### Honest limit

Measured on a prototype and by the reducer's tests; no person has done it, and the D58 steps are not in the measurement. Permission dialogs (Accessibility, Screen Recording, Microphone) can only be granted by the owner in System Settings.

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

> Knack is one app. A calm window with five destinations, a menu-bar item, and when an agent starts working on your real screen, the window gets out of the way and a small pill in the corner says what is happening in five words and offers Stop. It does not pop back on its own. First launch is a short first run: your role, a consent with three equal buttons, the permissions Knack needs, and a first look at your week.

## Slide bullets

- One app: window, Dock, menu bar, corner pill; five destinations.
- Window minimises when an agent works; the pill says it in five words and offers Stop.
- One interrupting surface at a time; never over a password field.
- First run: the spec cut about 20 clicks over 15 screens to 3; D58 adds a permissions step and a Try it step.
- No keystroke ever approves anything.

## Sources

- `docs/KNACK_UX.md`
- `docs/knack-ux/08-window-states.md`
- `docs/knack-ux/07-first-run.md`
- `docs/knack-ux/shell-transitions.json`
- `apps/desktop/KNACK_BUILD.md`
- `docs/DECISIONS.md (D51)`
- `docs/FIRST_LAUNCH.md`

## Related pages

`stop-everything.md`, `attention-router.md`, `connections.md`, `your-data.md`
