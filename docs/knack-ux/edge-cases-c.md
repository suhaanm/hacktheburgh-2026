# Edge cases: Needs you, Routines, Background tasks, Your data, Settings

Track C's screens, one row per odd thing the data can be. The tests are in `apps/dashboard/src/edge-cases-c.test.ts` (static markup, fixed clocks); the test named by an id is `[ID] ...`. A last test fails if this table and the tests drift apart. Page-level states (loading, error, partial, empty) are checked in the browser by `apps/dashboard/qa/knack/edge-c.mjs`, listed at the end.

The rules behind every row:

- A field the engine left out leaves out its own line. It never prints `undefined`, `NaN`, `null` or an empty paragraph.
- A number that makes no sense (negative hours, a count below zero, NaN) is never printed as a fact: it becomes zero, or the line is left out.
- A time that is not a real time, or is more than a day ahead, prints as "time unknown". A stale time prints as the date it is.
- A list is paged, never drawn whole: Needs you draws at most 60 rows and then pages of 50; Routines 7, then 50, then 50 more; the call list 4, then 200; memory lines 4, then 200; skills 200.
- An id that comes twice is one item (the first). An entry that is not an object is skipped. An item with no id is keyed by its place.
- Text is cut on a whole character (never half an emoji or an accent), and a cut always ends in an ellipsis. Memory lines are the worker's own words and are never cut.
- Nothing here guesses: an unknown number of steps stays unknown (no "of N").

## Safe text

| ID | State | What is shown | Test |
|---|---|---|---|
| TX-01 | Emoji, accents, combining marks, right-to-left text at a cut | Cut on whole characters, ellipsis at the end, right-to-left text kept whole | clip cuts on a whole character |
| TX-02 | Not text, not a count, not a list | Nothing; a count below zero or NaN is 0; a duplicate id once | clip, count and uniqueBy treat anything else as nothing |
| TX-03 | Invalid, empty, future (more than a day ahead) and stale times | "time unknown" for the first three; the date for a stale one | a time shows as a date and a clock when real |

## Needs you

| ID | State | What is shown | Test |
|---|---|---|---|
| NY-01 | Zero items (and every source missing) | No list, no headline, the empty state; the badge says 0 | no items |
| NY-02 | One item | "1 thing needs you." | one item |
| NY-03 | Hundreds of items (300, a third of them safety) | At most 60 rows, safety first; "Show 50 more" pages; the headline and the badge still say all 300 | hundreds of items |
| NY-04 | Duplicate ids (approvals, proposals) | One row each; every key distinct | a duplicate id is one item |
| NY-05 | Items with no id | Each kept, each with its own key | items with no id |
| NY-06 | Entries that are not objects, a source that is not a list | Skipped | entries that are not objects |
| NY-07 | No title; a 500-character title | "An approval"; cut with an ellipsis | an approval with no title |
| NY-08 | Unicode title (accents, emoji, Hebrew) | Kept whole | unicode in a title |
| NY-09 | No summary | No empty paragraph | an approval with no summary |
| NY-10 | Stale, future and invalid created times | "time unknown" in the evidence; an invalid time sorts last | a stale, future or invalid time |
| NY-11 | A proposal with no value and no frequency | Title and the two choices; no "Could save", no hint, no empty line | a routine proposal with no value |
| NY-12 | Hours saved: negative, reversed, NaN, missing, equal, a string; net money negative | No line, reordered, no line, no line, "about 2 hours", no line; "-£120" | hours saved |
| NY-13 | Evidence with 100 fields; none at all | 30 shown and "70 more fields are in the run."; only what exists | evidence with a hundred fields |
| NY-14 | A prepared action with no text, title, reason, ranking, sources | Its three choices and "A prepared action" | a prepared action with no prepared text |
| NY-15 | A paused run with no start time and no kind | No clock; "Paused: Background run" | a paused run with no start time |
| NY-16 | An away report with lists missing, empty, or full | Nothing, nothing, "Since you were away: 2 runs finished, 1 failed." | an away report |
| NY-17 | The word swap given null, a number or an object | An empty string, never a throw | the word swap accepts anything |

## Routines and background tasks

| ID | State | What is shown | Test |
|---|---|---|---|
| RT-01 | No routines | Nothing running, nothing turned down, no headline | no routines |
| RT-02 | Duplicate ids and holes | One routine per id | a duplicate id is one routine |
| RT-03 | 400 routines; minutes a week missing, NaN or negative | Sorted by minutes; the odd ones count as none and sort last | hundreds of routines |
| RT-04 | A routine whose steps are unknown (no record, no rung, no proposal) | No total, no NaN, no "undefined" | a routine whose steps are unknown |
| RT-05 | A 500-character title; no title | Cut with an ellipsis; "A routine" | a very long routine title |
| RT-06 | What it touches, lists missing | "" or "Touches A, B and C." | what a routine touches survives |
| RT-07 | The headline with no tasks, negative or NaN minutes | Empty, or the most urgent fact; never a negative number | the headline names the most urgent fact |
| RT-08 | 500 runs; a run with nothing in it | 500 tasks, no error; a finished task | five hundred runs |

The background tasks list has its own tests in `src/lib/tasks.test.ts` (state words, notes, steps, rows from the tasks service, the fade into Done today, finishing, one announcement), `src/components/routines/BackgroundTasks.test.ts` (one line each, icons by shape, nothing for no tasks, steps closed, Done today closed, a retry when it cannot be read) and `src/lib/live.test.ts` (fake clock and fake stream: fast and slow polling, focus, bursts, a broken stream, a stream at an address, no overlap, a hidden tab).

## Your data

| ID | State | What is shown | Test |
|---|---|---|---|
| YD-01 | What it measures with no view; counts negative or NaN | "Reading"; 0, 0, 0 with Export and Forget off | what it measures with no view |
| YD-02 | The call list empty; entries missing fields; non-objects; 500 entries | "Nothing has been sent to a model."; "time unknown" and "model not recorded"; skipped; four rows and "Show all 500" | the call list |
| YD-03 | What the admin sees, no lists | One sentence; no empty headings | what the admin sees with no lists |
| YD-04 | Capture and glances with nothing from the app | One line | capture and glances in a browser tab |
| YD-05 | Memory file: a missing section, not a list, a line with no id, a duplicate id, a non-text line | Handled, in order, one per id | the memory lines |
| YD-06 | The headline: 0, 1, many, negative | "nothing", "1 thing", "12 things"; never a negative | the headline counts what is remembered |
| YD-07 | What it looked at or sent, for a worker | One sentence and one link; no call row | what it looked at or sent is one sentence |

## Settings

| ID | State | What is shown | Test |
|---|---|---|---|
| ST-01 | Interruptions answer with no list of kinds | The three words, none pressed, no groups | an interruptions answer with no list of kinds |
| ST-02 | Zero kinds | The same, no "Each kind" rows | zero kinds |
| ST-03 | A kind at a mode nobody knows | No button pressed; no break | a kind at a mode nobody knows |
| ST-04 | What it learned: a negative count, NaN hours, an hour of 99 | Left out of the sentence | what it learned |
| ST-05 | The app with an empty settings object | Coaching off, move aside on, open at login off, each with its line | an empty settings object |
| ST-06 | Hey Knack: no bridge, and each of its three states | "Available in the Knack app."; the fixed note in all three | Hey Knack |
| ST-07 | 500 skills, a duplicate name, 300-character descriptions | 200 shown, sorted, each once, cut at 140 | five hundred skills |
| ST-08 | The headline with live models on, off, or unknown | Says how Knack is set; empty when it does not know | the headline says how Knack is set |
| ST-09 | Advanced | Closed, last, and the call list not loaded until opened | the Advanced section is closed |

## Admin only

| ID | State | What is shown | Test |
|---|---|---|---|
| AG-01 | A worker at Background runs by its address | "Switch to Admin to see this." and nothing else | a worker who reaches Background runs |

## Page-level states (in the browser)

| State | What is shown | Check (`qa/knack/edge-c.mjs`) |
|---|---|---|
| Loading, slow engine | "Loading what needs you", "Loading your routines", "Loading your data": one line, no spinner storm | loading |
| The engine or the agent is down | The built-in sample, badged "Example data", with one short reason ("The engine is not answering.") and its engine message behind a hint | down |
| Partial: the queue answers, routines do not | The live approvals and an "Example data" badge with the reason for the routines | partial |
| Empty | "Nothing needs you." / "Nothing runs yet." | empty |
| A task finishes while the page is open | The line changes to a check with its result, an open row stays open, the scroll does not move, one polite sentence is announced | the smoke block "Live" |
| The event stream breaks | Polling carries on every 2 s (running) or 15 s (not), and the stream is tried again after 30 s | `live.test.ts` |
