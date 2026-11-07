# Demo runbook: the tutor that tries to get fired

The story in one line: Alongside is an assistant that teaches instead of doing it for you, and it is built to make itself unnecessary. Every chapter below shows one piece of that.

## Start and stop

- Ask `main` to "start the demo". It runs `bash scripts/start-demo.sh` in the background. You can also run `npm run showtime` yourself.
- It builds only if `out/` is older than the sources, opens the app on a dedicated profile (`~/.alongside-demo`), and the practice desktop appears fullscreen. The tour starts by itself about 3 seconds later. The panel (dock) is shown for the tour even if it is normally hidden.
- Flags: `--full` (extended tour, about 4:25), `--live` (live-model scam check and file search), `--mute` (captions only, no narration audio), `--debug` (opens the local debug port 7777; off by default), `--interactive` (no autopilot: you talk to the live assistant on the practice desktop, see `docs/DEMO_SCRIPT_INTERACTIVE.md`; also `npm run demo:interactive`).
- Stop: `bash scripts/stop-demo.sh` (stops only the app it started, gracefully; your profile and settings are put back), or press Esc, or the Stop button, or the menu bar item. It says if an agent holds the Electron lock.
- It refuses to start a second copy and tells you how to stop the running one.

## What is scripted and what is live (be explicit)

- Scripted (default): timings, narration, the rings and ticks, the stalled step, the scam report, the file search result, the "Marcus" and "Amelia" greetings, the demo approval click in chapter 7. The badge "Scripted walkthrough on a practice desktop" stays on screen. Say so out loud.
- Real in the scripted tour: the dock, the overlay, the level chip and the level engine (it decides the level, not the model), the profile you can read and delete, the confirmation toast, the progress chart view, the settings changes, Stop.
- Live only with `--live`: the scam check (the real analyst on the stage message) and the file search.
- Fully live: `--interactive`, or the normal product by voice on a real screen.
- The hints chart numbers (5, 3, 1) are seeded demo data. Say so if asked.

## Controls during the tour

Space pauses and resumes. Left and Right arrows go back and forward a chapter. Esc stops. The panel has Back, Pause, Next and Stop demo; the menu bar item says "Stop the demo walkthrough". The big Stop in the panel always works.

## Per chapter (core cut, about 2:50)

| Time | Chapter | What the audience sees | TEACHING callout | Say |
|---|---|---|---|---|
| 0:00 | 1. Say its name | "Hey Marcus", listening light, a greeting | The opening problem: people left behind. It teaches instead of doing it for you. | "Millions of people get left behind. This helper teaches, so one day they stop needing it." |
| 0:13 | 2. It shows, you do | Numbered ring and arrow per step, a tick after each click, then a spoken teach-back | Rung one of the help ladder: walk with me. Then it asks you to explain the green button in your own words. | "It never clicks for you. After the task it asks you to say it back, because that is what makes it stick." |
| 0:43 | 3. Less help as you learn | Level chip drops from Walk with me to Nudge me; a stall gets a glow, a clue, then an arrow; Progress opens | The ladder out loud: watch me, walk with me, nudge me, on my own. Plain code fades the help. Fewer hints is the proof. | "The chip stepped back because you did two steps clean. If you get stuck it helps a little more, then fades again." |
| 1:08 | 4. Scam Shield | A text arrives, a checking chip, red marks on the rushing, the threat and the odd link | The marks are the lesson: here is how to spot it yourself. It never says safe and points to the number on your card. | "It is teaching you the red flags, not just blocking the message." |
| 1:28 | 5. Second helper | "Hey Amelia", different voice and colour | Choice and control: two helpers, same rules. | "Pick whichever voice you find easier." |
| 1:37 | 6. Teach me anything | A question with no saved lesson; one ring on the mute button | It works out a one-step lesson from your screen, and still points rather than does. | "For anything unplanned it plans one step and checks it." |
| 1:52 | 7. I can do it for you | Top-right toast asks first; it opens the page; the log and the count appear | Doing it for you is the learner's choice, and it is counted so dependence is visible. Pay, send, delete and sign in always stay yours. | "It offers to do it or show me. It counts every time, so we can see if you lean on it." |
| 2:06 | 8. Your files | Search result for the GP letter | Reads only folders you chose. | "Only reading, only folders you picked." |
| 2:13 | 9. Type instead | Chat view, no voice | Same teaching without speaking, for anyone who prefers typing. | "Same helper, quieter." |
| 2:21 | 10. You're in control | Look and feel changes, a profile line is forgotten, Stop is ringed | The profile is the learner's: read it, change it, delete it. Stop is always there. | "You own the file. Watch it forget this line." |
| 2:37 | 11. Progress | Things you can do now, hints per task falling | Success is needing the helper less; the closing line connects to digital confidence. | "My goal is to be unnecessary. Every step you do alone is confidence you own. Now ask it anything." |

After chapter 11 the app is back to normal live mode and the practice desktop stays up for questions until you press Stop.

## Q and A

- Does it do things for me? Only if you say so, one task at a time, with a real click on the top-right toast. Every use is logged and counted. It never pays, sends, deletes or signs in.
- How do you know it teaches? The hints per task chart. The level is decided by plain code from clean attempts, stalls and your teach-back, not by the model. In demo mode one clean attempt steps up (default on today; we say so).
- What does it see? The screen only while a session is active (visible indicator), sent without being stored. On-screen text is treated as data, never as instructions.
- Is it a scam detector? It points out warning signs and never calls a message safe. It tells you to ring the number on your bank card.
- Who owns the data? A plain file you can read, edit or delete. Carer sharing is off by default.
- Is this real or a video? The tour is a scripted walkthrough on a practice desktop, labelled as such. The interactive mode and the product are live.

## If something goes wrong

- Narration silent or odd: restart with `--mute` (captions only). A missing or stale clip already falls back to captions.
- Tour stuck or wrong chapter: press Esc, run `bash scripts/stop-demo.sh`, start again.
- Another copy running: run `bash scripts/stop-demo.sh` first.
- Practice desktop not in front: press `F` on it, or restart.
- Last resort: play the recorded video.
