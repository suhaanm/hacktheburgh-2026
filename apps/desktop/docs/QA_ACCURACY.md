# point_at accuracy on the real screen (QA)

Run: 2026-10-31T14:29:21.907Z | mode: real | stage window 1728x999 css px at (0,33) (work area) on a 1728x1117 display (scale 2)

Capture path: REAL desktopCapturer of the primary display (Screen Recording status: granted)

Method: the demo-stage is shown in a frameless window on the work area of the primary display (exact content bounds, so ground truth maps to display-normalised coordinates); the capture path named above grabs it; `point_at` is called with the stage's own `targetDescription`; the box handed to the overlay is compared with `__stage.rects()[targetId]` (mapped to display-normalised 0-1000 through the window content bounds).

## Summary

| Metric | Value |
|---|---|
| Present targets tried | 13 |
| Found (a box was drawn) | 13/13 |
| Hit-rate: predicted box centre inside the true rect | 12/13 (92%) |
| IoU >= 0.5 | 10/13 (77%) |
| IoU >= 0.3 | 12/13 (92%) |
| Median IoU (found) | 0.87 |
| Median centre distance to true centre (0-1000 scale; 10 = 1% of the screen) | 2.9 |
| Absent targets: correctly found:false | 2/2 |
| Latency p50 / p95 (ms, whole point_at incl. capture) | 108 / 134 |
| point_at calls / Google API requests | 15 / 24 (budget 150) |

Note: IoU is conservative here. The true rect is the element's whole hit area (desktop icons include their label, window buttons include padding) while the model boxes the visible glyph, so a correct point can score IoU 0.2-0.5. The pointing metric that matters is "centre inside true rect" and the centre distance.

## Per target

| Group | Target id | Found | IoU | Centre hit | Centre dist (0-1000) | Pred box | True box | ms | Description |
|---|---|---|---|---|---|---|---|---|---|
| video_call | desk.icon.video | yes | 0.45 | yes | 6 | 18,81,52,153 | 7,76,65,169 | 134 | Teal rounded-square icon with a white video-camera symbol and the labe |
| video_call | video.contact.lily | yes | 0.90 | yes | 2 | 120,234,331,296 | 122,234,327,291 | 118 | Row labelled Lily with the subtitle Granddaughter and a green dot, sec |
| video_call | video.start_call | yes | 0.97 | yes | 0 | 548,622,642,667 | 548,622,641,667 | 109 | Large green button reading Start call with a camera icon, in the right |
| video_call | video.precall.join | yes | 0.98 | yes | 0 | 491,750,546,794 | 491,750,546,794 | 114 | Large blue button reading Join, below the camera preview and the switc |
| video_call | video.call.hangup | yes | 0.96 | yes | 0 | 663,841,715,897 | 664,841,715,897 | 107 | Red button with a white phone-handset icon and the word Leave, right-m |
| spot_scam | desk.icon.messages | yes | 0.61 | yes | 8 | 15,173,57,257 | 7,176,65,270 | 107 | Blue rounded-square icon with a white speech bubble and a small red 1  |
| spot_scam | messages.conv.scam | yes | 0.87 | yes | 3 | 83,215,294,280 | 83,213,297,287 | 108 | Top row of the conversation list, name Aldermoor Bank in bold with a b |
| spot_scam | messages.msg.scam.0 | yes | 0.98 | yes | 1 | 312,191,648,289 | 313,190,646,289 | 107 | The grey message bubble from Aldermoor Bank (the blue underlined web a |
| spot_scam | messages.thread.menu | yes | 0.69 | yes | 4 | 960,117,984,163 | 961,127,983,161 | 110 | Small round button with three dots in the top-right corner of the open |
| spot_scam | messages.thread.report | yes | 0.29 | NO | 37 | 853,172,983,292 | 857,176,980,213 | 113 | First item, Report junk with a warning-triangle icon, in the dropdown  |
| bigger_text | desk.icon.settings | yes | 0.49 | yes | 5 | 20,280,55,356 | 7,277,65,370 | 119 | Grey rounded-square icon with a white gear symbol and the label Settin |
| bigger_text | settings.nav.display | yes | 0.89 | yes | 1 | 86,210,239,253 | 86,211,238,250 | 106 | Second item, Display with a monitor icon, in the vertical list on the  |
| bigger_text | settings.text_larger | yes | 0.79 | yes | 3 | 924,240,968,303 | 926,248,967,301 | 104 | Button with a big letter A and the word Larger, to the right of the sl |

## Absent targets (must say found:false)

| Found | ms | Note | Description |
|---|---|---|---|
| no (good) | 108 | There is no orange button labelled 'Download report' in the  | orange button labelled Download report in the top right corner |
| no (good) | 107 | No Print icon is visible next to the window title. | a Print icon next to the window title |

## Render check (what the overlay window really painted, from overlay.png, device px)

Method: flood-fill from the centre of the box handed to the overlay; the painted ring encloses it and the fill bounds are the ring hole. Compares the hole with the requested box (norm -> overlay window -> display pixels mapping) and reports whether the TRUE target centre is inside the ring.

| Target | Requested box (x,y WxH px) | Painted ring hole | Ring painted | Hole vs requested IoU | Centre offset px | True target centre inside ring |
|---|---|---|---|---|---|---|
| video.contact.lily | 415,523 729x139 | 401,508 757x168 | yes | 0.79 | 0 | yes |
| video.start_call | 1894,1390 325x101 | 1880,1355 353x169 | yes | 0.55 | 0 | yes |
| messages.conv.scam | 287,480 729x145 | 273,466 757x174 | yes | 0.80 | 0 | yes |

## Earlier runs (kept for the record)

| Time (GMT) | Capture path | Targets | Centre inside true rect | Median IoU | Median centre error | Latency p50 / p95 | Absent targets |
|---|---|---|---|---|---|---|---|
| 14:03 | stage-window capturePage (Screen Recording not yet granted), ground truth viewport-normalised, stage fullscreen | 34 (14 flow steps + 20 catalog items over 7 screens) | 33/34 (97%) | 0.51 | 2.6 of 1000 (0.26% of the screen) | 1461 / 4804 ms | 5/5 found:false |
| 13:59 | same, earlier prompt wording | 34 | 30/34 (88%); 3 of the 4 misses were label-only descriptions shared by a desktop icon and a task-bar item ("VideoChat"), which are ambiguous for a human too | 0.47 | 4.1 of 1000 | 1467 / 5350 ms | 5/5 |

What the misses were: `messages.thread.report` (dropdown item) is boxed as the whole dropdown (IoU 0.29, centre 3.7% off) in every run. That is the one repeatable grounding weakness found: tall menus.
