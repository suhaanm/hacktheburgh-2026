# 07 First run: three clicks to the first insight

Today there are two set-ups. The desktop panel has 8 steps (Hello, About you, How you like to learn, Make it comfortable, Look and feel, Allow what I need, Helping hands, All set). The dashboard then asks 7 questions (role, tools, risky actions, tone, pace, hours, capture) with a live memory preview. That is at least 15 screens and about 20 clicks, plus the macOS permission prompts, before anything is shown.

After: one window, three screens, three clicks. Everything else takes the role pack's safe defaults and is editable later in Your data. The window is the normal Knack window (1152 by 735 on a 1440 by 900 display) with no sidebar yet.

## Screen 1: role (click 1, advances by itself)

```
┌─ ● ● ● ──────────────────────────────────────────────────────────────────────────┐
│                                                                                    │
│   ◖● Knack                                                                         │
│   ───────────────────────────────────────────────  1 of 3  (thin progress line)   │
│                                                                                    │
│   What work do you do?                                       (display, 40 px)      │
│                                                                                    │
│   ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐          │
│   │ Benefits processor │  │ Data analyst       │  │ Programmer         │          │
│   │ Cases and          │  │ Queries and        │  │ Commits and        │          │
│   │ calculators        │  │ reports            │  │ reviews            │          │
│   └────────────────────┘  └────────────────────┘  └────────────────────┘          │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

- One idea. No sidebar, no Next button: choosing a card moves on after 240 ms. Back is the arrow keys and a quiet "Back" text at the bottom left from screen 2.
- The cards come from `api.packs()` (a pack is a card; at most 5; the third is never "Other"). Each has a name and one line of at most 4 words.
- Knack starts its engine and agent in the background from the moment the app opens. Nothing on this screen waits for them.

## Screen 2: the one consent (click 2)

```
│   ◖● Knack
│   ──────────────────────────────────────────────────  2 of 3
│
│   Let Knack learn from your work?
│
│   It records when you are active, never what you read: no page text,
│   no URLs, no field values. The record stays on this laptop.
│
│   [ Yes, learn my times ]    [ Not now ]    [ Never ]            (three equal buttons)
│
│   Times only ›                                                    (Details: the fields recorded)
│   You can change this any time in Your data.
```

- Capture is never pre-selected; Not now and Never weigh the same as Yes (UI_DIRECTION, consent rule). "Not now" asks again after the first week, once; "Never" never asks again.
- Words: about 48 on the screen. The sentence "The record stays on this laptop." is printed; the field list is in the disclosure.
- Screen glances (a frame sent to a model), the microphone, Accessibility and Screen Recording are not asked here. Each is asked once, in context, the first time it is needed, with one sentence and one "Open System Settings" button (macOS requires the owner for the last two; a human-only step).

## Screen 3: ready (click 3)

```
│   ◖● Knack
│   ──────────────────────────────────────────────────  3 of 3
│
│   Here is what Knack will remember.
│
│   · Short summaries, plain voice
│   · Usual hours 09:00 to 17:30, Monday to Friday
│   · Never without asking: submitting a case note
│   · Tools: calculators, case note page
│
│   Edit any line later in Your data.
│
│   [ Show my week ]
```

- The four lines are the pack's defaults (tools pre-selected, risky actions set to "never without me", short tone, gradual pace, the pack's hours), rendered from the memory file that was just written. They are plain sentences, not Markdown.
- Click 3 opens Home.

## Home on the first run (the first insight)

```
│   Week of 9 November                                      ┌ Example data ┐
│
│   Example: on the cliff check you usually take about 35
│   seconds longer than the expert.
│
│   This is an example. Knack starts counting now.
```

The example comes from the synthetic firm and carries the "Example data" badge. It is the only place where an example stands in for the worker's own insight, and it is replaced by the first real pointer as soon as the engine has one (after the first week of the worker's real steps; "Knack is learning your work" is the honest state until then and is shown instead when the worker chose Not now or Never on capture).

## Budget

| Measure | Today | Target |
|---|---|---|
| Screens | at least 15 | 3, then Home |
| Clicks to the first insight | about 20 | 3 |
| Words on the first screen | 159 (measured, dashboard role screen) | about 26; at most 50 on any first-run screen |
| Questions asked | 7 in the dashboard, plus the panel's choices | 2 (role, capture) |
| Permission dialogs | up to 4 at set-up | 0 at set-up |

Tests: `first-run.test.ts` drives the reducer (three states, a click per state, no state needs a text field); `check-clicks.mjs` replays "launch to Home" and fails above 3.
