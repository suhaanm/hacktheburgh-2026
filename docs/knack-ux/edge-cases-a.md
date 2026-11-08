# Edge cases, Track A (the desktop shell)

State, what Knack does, and the test or manual step that covers it. "Test" means an automated test in `apps/desktop` (unit, or the hidden harness `scripts/knack-check.mjs` and `scripts/knack-e2e.mjs`, which show nothing on the screen). "Manual" means it needs a real screen and the owner; the lead runs it at the first launch together.

## Displays, windows, Spaces

| State | What happens | Covered by |
|---|---|---|
| A second display | The window opens on the display holding the pointer and remembers its place per display. The corner column, the permission card and the wake cards go to the display holding the pointer (the card of the one that opened first stays where it is until it goes). The Ask bar centres on the display holding the pointer. The background pills sit top right of the pointer's display. | Test: `window-bounds`, `mainwindow.test.ts`, `ask-ipc.test.ts` (second display), `agent-pills-model.test.ts` (second display), `toast.test.ts` |
| A display unplugged while a run works | The corner column, the pills and the cards find the pointer's display again within half a second (they listen for display changes). The window is brought back if it sat on the display that went. Nothing about the run changes. | Test: `mainwindow.test.ts` (display that goes away), `agent-pills-model.test.ts`, hidden check (corner column placement); manual with a real second display |
| A display plugged in mid-run | Nothing moves (a window already on a display stays); the next time the column appears it may use the new display if the pointer is on it. | Manual |
| The window is off every display after a change (a saved place that no longer exists, a layout change) | If less than 60 percent of it is on any one display it is moved inside the nearest display, keeping its size as far as that display allows. A hidden, minimised or full-screen window is left alone. A saved place is only restored when 60 percent of it is on a display. | Test: `mainwindow.test.ts`, `window-bounds` |
| A full-screen app in front | Every overlay (column, cards, Ask bar, pills, Cue) is on every Space and over full-screen apps, hidden from capture, out of the task bar; none but the Ask bar can take the keyboard. Knack's own window never minimises itself from full screen. | Test: `edge-cases-a.test.ts` (every overlay window); manual |
| Stage Manager | The overlays are panels (they do not join a Stage Manager group). Minimising the window when a run starts removes it from the stage; the Dock icon or the pill brings it back. | Manual |
| Another Space | The overlays follow every Space. The window itself belongs to the Space it was opened on; the Dock icon or Open Knack brings it to the current one. | Manual |
| The worker is in a call or sharing the screen | The pill and the cards are held (not drawn) while a screen is shared; Stopped and safety items still show. | Test: `shell-machine.test.ts`, hidden check |
| A password field has the focus (secure input) | The pill still shows; cards wait and come back when the field loses the focus. | Test: hidden check ("a password field with focus holds the card") |

## Sleep, wake, clocks

| State | What happens | Covered by |
|---|---|---|
| The Mac sleeps with a run active | The power-save blocker held for the run is released by the system; nothing is held after the run ends. On waking, the silence of the service during the sleep is not counted as an outage (the count towards "Lost contact" starts again), the window is brought back onto a display if the displays changed, and the next poll (2 to 10 s) shows the truth. | Test: `edge-cases-a.test.ts` (wakes from sleep), `keep-awake.test.ts` |
| The clock is set back or forward while a pill shows | A done check or an error never stays for ever (a pill that began "in the future" counts as old enough); a silent service is still an error after the limit; the timer that clears a check never waits longer than the check itself. | Test: `edge-cases-a.test.ts` (a clock set back), `activity.test.ts` |
| A run record that a dead process left behind | Never work: older than 15 minutes (the service caps a run at 15) counts as a ghost; it never shows a pill, never says "n of m", never holds back Cue or Hey Knack. | Test: `activity.test.ts`, `pill-state` via the activity tests, `agent-activity.test.ts`, the hidden end-to-end run (two ghost runs listed; the pill must stay away) |
| "n of m" with a total of one or none | Never said: the words alone. | Test: `activity.test.ts` |

## The services

| State | What happens | Covered by |
|---|---|---|
| A service Knack started stops by itself | Started again after 2 s, then 4 s, then 8 s; the stack stays ready; after three stops in ten minutes the window goes to the plain page with one sentence and Try again. A service stopped on purpose (quit, the models switch) is never restarted. A service Knack did not start is never touched. | Test: `stack.test.ts` |
| A port that something else holds | Said at once, before anything starts: "Another program is using a port Knack needs." with the way out (quit it, or set `ENGINE_PORT` and `AGENT_PORT`). A port held by our own running service is attached to. | Test: `stack.test.ts` |
| The engine is slow | The starting page says "Starting Knack..." and after 30 s "Still starting Knack..." (the first start can take a minute); the engine gets 90 s, the agent 90 s; then one plain sentence and Try again. On quit each service gets 4 s to stop after SIGTERM, then is forced (a service still answering a slow request at that moment is forced). | Test: `shell-pages.test.ts`, `stack.test.ts` (timeouts); the real-services run (`knack-e2e.mjs --real-services`): quit in about 4 s |
| The data folder cannot be written (read-only home, full disk) | "Knack cannot write to its data folder." in plain words, no system message, no path. A lost settings write is logged and never thrown (the app keeps running on what it holds); a lost window-position write only forgets the position. | Test: `stack.test.ts`, `edge-cases-a.test.ts` |
| First launch with no key | Example data, the one line "Running with example data", nothing asked, nothing fails. | Test: `model-mode.test.ts`, `edge-cases-a.test.ts` |
| A key removed since the last start | The same as no key at the next start; a running app keeps what it started with. | Test: `edge-cases-a.test.ts` |
| uv is not on the path (a Dock-launched app has a short PATH) | The path is widened to the usual places (Homebrew, `~/.local/bin`, `~/.cargo/bin`); if uv is still not found, one plain sentence. | Test: `stack.test.ts` |
| The services were started by someone else (the lead's `make live`) | Attached to; never stopped; the data directory is chosen by what the agent says it uses. | Test: `stack.test.ts`; hidden check |

## Saved state and settings

| State | What happens | Covered by |
|---|---|---|
| A profile from an earlier build | Valid keys are kept (the worker's own choices survive, even where the new default differs), unknown keys are dropped, new keys take their defaults. The old persona becomes the one identity. | Test: `edge-cases-a.test.ts` |
| A damaged settings file | Read as the defaults; the next change writes a good file. A file of the wrong shape (a list, a number, null) is the same. | Test: `edge-cases-a.test.ts` |
| A damaged window file | Read as far as it is valid (bad rectangles dropped), else empty. | Test: `edge-cases-a.test.ts`, `window-state.test.ts` |
| The old side panel's set-up | Pinned done in the Knack app: no file, patch or script brings its eight steps back. | Test: `knack-settings.test.ts`, the hidden end-to-end run |

## Running work and quitting

| State | What happens | Covered by |
|---|---|---|
| Quit with a run active | One sheet: "Knack is working. Stop it and quit?" Stop and quit, Keep working (the default); a routine due within 24 hours adds one line. Stop and quit stops everything first. | Test: `mainwindow.test.ts` (quit), hidden end-to-end run (clean quit) |
| Quit by a signal (the Mac shutting down, `kill`) | The app quits by itself, exit code 0, stopping only the services it started. | Test: hidden end-to-end run, with and without real services |
| The kill switch while a run works | The pill becomes the Stopped card, the machine ignores new runs until Resume. | Test: `shell-machine.test.ts`, hidden check |
| The service stops answering while a run works | After 15 s the pill says "Lost contact" (an error held until opened); the top-right pills for tasks say "Lost contact" and stay until clicked. | Test: `pill-state.test.ts`, `tasks-client.test.ts` |
| A task stream that is down | The pills read GET /tasks every 3 s; a stream silent for 25 s is dropped and reopened; a fresh snapshot replaces what was held. | Test: `tasks-client.test.ts`, `sse.test.ts`, hidden check |
| A second copy of Knack is opened | The first copy comes to the front; no second copy runs. | Test: `mainwindow.test.ts`; manual |
| The window is closed (red button, Command-W) | It hides; the app, the Dock icon, the menu bar item and every run carry on; the Dock icon brings it back. | Test: `mainwindow.test.ts`, hidden check |
| Typing in the Ask bar with no open conversation | The line becomes a task: the bar closes and a card asks first (a real mouse click only). When the task cannot be taken the bar stays open with the text kept and one plain sentence under it: "Too many tasks are running. Stop one or wait.", "Everything is stopped. Resume from the menu bar.", "The task service is not answering. Try again soon.", or the service's own reason for a request it would not take. The line goes only to the agent service on this Mac. | Test: `wake/controller.test.ts` "typing a task in the Ask bar", hidden check (the line stays under the input and the window grows to fit it), `ask-ipc.test.ts` |
| A stranger window calls a bridge (permissions, ring, settings, Ask, pills) | Refused: each bridge answers only its own page. | Test: hidden check |
