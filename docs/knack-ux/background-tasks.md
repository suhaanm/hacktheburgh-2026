# Background tasks and live updates (Track C)

Owner requests of 8 Nov 2026 (`docs/OWNER_REQUESTS.md` 4.15 and 4.16): a task that finishes in the background shows as finished with no refresh, and tasks look as minimal as Claude Code's task list.

## What a worker sees

One line per task, on Routines (top of Running) and wherever Home draws `<BackgroundTasks limit={3} />`:

| Part | Content |
|---|---|
| Icon | A spinner while it runs, a check when done, a dash when stopped, a cross when it did not finish, a dot when it waits for the worker. The shape carries the state; the state word is read out by a screen reader. A spinner is a still ring under reduced motion. |
| Task | The job in plain words (at most 60 characters). |
| Note | While it runs: the current step. When done: the one result line. When waiting: "Needs your OK." or "Has a question." (the card is in Needs you). When stopped or failed: that, and that nothing was changed (or the service's own reason). |
| On a click | The steps as a plain list of checkmarks; for a task from the tasks service also **Stop** (running) and **Open folder** or **Open file** (done, when it made one). |
| Never | An id, a budget, a lease, "step 0 of 1", a count the worker cannot act on. Those are the admin's Background runs (Admin only, More). |

Order: running first, then ones waiting for the worker, then a task that finished in the last minute (so the finish is seen); everything else finished and created in the last 24 hours is under a closed "Done today (n)". At most four lines show on a screen that asks for four; the rest are counted.

**What is never listed (owner, 8 Nov: "why are there so many background tasks running?").** The agent service lists persisted run records with their last state, so a process that died left some 'planning' or 'running' for ever. A *ghost* is a task that is not finished and started longer ago than anything can last: a run record after 15 minutes (the service's cap), a task row after its longest cap (120 minutes) plus a margin, a card waiting for the worker after a day, or anything with no usable start time. A ghost is dropped everywhere: not listed, not counted as running (so the page does not poll fast for it), no detail read, no stream, no Needs you item. Nothing is deleted. A finished task created more than a day ago is old history and is not listed. What the built-in sample says about runs is never a task: only a service that answered can name one. The clock is a parameter of every rule (`isGhost`, `isOld`, `pickTasks` in `src/lib/tasks.ts`), so each is tested with a fixed time.

**Routines vs tasks.** The Routines tab is called 'Your routines' and counts routines only. A routine's words say how it is set ('Watch first', 'Asks first', 'Away runs'; 'Set to watch first. No practice runs yet.', 'Watched: 13 of 14 practice runs match.'), never that it is executing right now. Tasks are the only thing that 'works in the background'.

## Where the data comes from

`src/lib/useTasks.ts` is the only place. When the tasks service answers (Track T, contract v1: `GET /agent/tasks`, `GET /agent/tasks/{id}` for the steps, `POST /agent/tasks/{id}/stop`, `/open`) the list is the worker's own tasks. Until it answers, the agent service's run list (`GET /agents/runs`) stands in. A task that needs the worker (`waiting_consent` with a card, or a question) is also an item in Needs you, rendered as a consent card with Allow and Not now (real clicks, one weight, none primary) and the wider choice behind More; `POST /agent/tasks/{id}/consent` carries `worker_approval` and the proxy adds the token.

## How it stays live (`src/lib/live.ts`)

1. **Event streams.** The tasks service's `GET /agent/tasks/events` (snapshot, task_started, task_progress, task_finished; heartbeats are ignored) and the run page's `GET /run/{id}/stream` for a run the dashboard started. Each event asks for one refresh of the screen's own data, at most one every 400 ms; a stream that breaks is dropped and tried again after 30 s.
2. **Polling.** Every 2 s while any task or run is active, every 15 s otherwise. A poll waits for the one before it, so a slow engine is not hammered; a hidden tab is not polled.
3. **Focus.** The window gaining focus, or the tab becoming visible, refreshes at once.

A refresh calls the screen's own `reload`, which keeps the last good data on screen: an open row stays open and the scroll does not move. A finish is a quiet check on the line and one polite sentence for a screen reader ("Chart builder finished.", "3 tasks finished."), never a toast. Screens that use it: Routines, Needs you, Background runs (admin), and Home through `BackgroundTasks`.

## Tests

`src/lib/live.test.ts` (fake clock, fake stream), `src/lib/tasks.test.ts`, `src/components/routines/BackgroundTasks.test.ts`, the Needs you task cases in `src/components/needsyou/rows.test.ts` and `src/screens/NeedsYou/model.test.ts`, and the smoke block "Live" (a mocked tasks service flips a task from running to done while the page is open).
