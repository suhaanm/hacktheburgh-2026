## Earlier runs (kept for the record)

| Time (GMT) | Capture path | Targets | Centre inside true rect | Median IoU | Median centre error | Latency p50 / p95 | Absent targets |
|---|---|---|---|---|---|---|---|
| 14:03 | stage-window capturePage (Screen Recording not yet granted), ground truth viewport-normalised, stage fullscreen | 34 (14 flow steps + 20 catalog items over 7 screens) | 33/34 (97%) | 0.51 | 2.6 of 1000 (0.26% of the screen) | 1461 / 4804 ms | 5/5 found:false |
| 13:59 | same, earlier prompt wording | 34 | 30/34 (88%); 3 of the 4 misses were label-only descriptions shared by a desktop icon and a task-bar item ("VideoChat"), which are ambiguous for a human too | 0.47 | 4.1 of 1000 | 1467 / 5350 ms | 5/5 |

What the misses were: `messages.thread.report` (dropdown item) is boxed as the whole dropdown (IoU 0.29, centre 3.7% off) in every run. That is the one repeatable grounding weakness found: tall menus.
