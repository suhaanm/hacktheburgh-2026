# Demo script: 3:00 live + 1:00 Q&A

> **Verification status (read before presenting).** **Multi-step control (`act_for_me`) is ON by default and verified for a Calculator task and for browser navigation in Safari; other apps and a full job application are not.** On a real Mac, with real Gemini `computer_use` and one plan-confirmation click, it pressed 1, 2, +, 3, 0, = in Calculator as seven separate clicks (about one minute) and the screen showed 42; every click is in the audit log. **Browser verified on a real task (Safari):** on the Google DeepMind careers page the loop clicked 'View open roles', clicked the job search box, typed 'software engineering', pressed Return (allowed only straight after typing a plain query) and opened a DeepMind role page in five audited steps; the screen showed the role description with the Apply button visible and untouched. It did not sign in, enter details or apply, and it left the cookie banner alone; the page must be loaded and in front when the task starts (one earlier run started before the page was visible and failed). **Not verified:** Chrome (an earlier `open_for_me` returned done without a confirmed landing tab, likely because stray headless Chrome processes intercept links; `act_for_me` on Chrome failed at step 0), completing or submitting a job application (it needs a sign-in and your personal details, which the assistant will not enter or submit for you without your explicit go-ahead), System Settings and Finder actions. Each action still passes the policy denylist, and Stop works; switch the loop off with `ALONGSIDE_AGENCY_LOOP=0`. Verified on a real Mac: pointing (10 of 11 real controls), refusals, Stop, Scam Shield and the real voice session. Demo the Calculator task as the multi-step example; do not present browser or other-app control as verified.

Structured on the guide's four tests: **(1) a named real person, (2) it needs Argon, (3) it keeps people in control, (4) it runs live in under 3 minutes.** Judges score working live demos, so the live run is the product; everything else supports it.

> Persona names below (Marcus, Amelia) are the current placeholders from `src/shared/personas.ts`. Find and replace when they are renamed. Say the demo honestly: the screen under the overlay is a **practice desktop**, the scam text is **staged**, and **demo mode** is on.

## 0. Set-up (do all of this before you walk on; full checklist with timings in `docs/MANUAL_TESTS.md`, Part 2)

| What | Setting / action |
|---|---|
| Display | Presenting laptop, one display, mirroring only if the projector needs it (test it). Do Not Disturb on, notifications off, brightness up |
| Audio | Wired headset or the laptop mic with echo cancellation; volume tested in the room. Speakers + loud room = use the hotkey |
| Key and network | `grep -q '^GEMINI_API_KEY=.' .env && echo present`; own phone hotspot already joined as a fallback network |
| Permissions | Microphone + Screen Recording granted to the app that launches Electron (your Terminal/IDE) **or** to `node_modules/electron/dist/Electron.app` itself, then **fully quit (the Terminal too) and relaunch**. Never start it with `open -n -a`: it is denied |
| Pointing check | After the app is up, wake it, ask it to point at something on the practice desktop and confirm a ring appears, **before** you go on stage |
| Fullscreen | Practice desktop fullscreen with **F** so the macOS Dock cannot hide targets at the bottom |
| Run | Terminal 1: `ALONGSIDE_USERDATA="$HOME/.alongside-demo" npm run dev`. Terminal 2: `npm run stage`. Practice desktop `http://127.0.0.1:5180` full screen in a clean browser window. Dock visible, level chip visible |
| Settings (dock settings panel) | `demoMode` **ON** (default). `helpLevelMode` auto. `captions` ON. `bigAnnotations` ON. `scamShield` ON. `agency` **off** (this also keeps `doItForMeAllowed` off). `filesEnabled` **off**. `carerSharing` **OFF**. `onboardingDone` **true** (see the next row). `pushToTalkOnly` OFF. `listeningLight` ON. `wakeEnabled` ON (turn OFF and use the hotkey if the room is loud) |
| First-run setup | **A fresh `ALONGSIDE_USERDATA` shows the nine-screen setup and keeps the dock open until it is finished or skipped** (`onboardingDone` defaults to false; the demo seed below only copies `profile.md`). Before you go on, open the demo profile once and press "Skip for now" (or finish it), and confirm the dock shows the normal panel. Do not run the whole setup on stage: it is not part of the timed script. The debug HTTP surface is off by default; do not set `ALONGSIDE_DEBUG` for the demo |
| Seed state | **Demo seed (from TEACH).** Run once before the demo, from the repo root: `export ALONGSIDE_USERDATA="$HOME/.alongside-demo"; mkdir -p "$ALONGSIDE_USERDATA" && cp src/main/teaching/fixtures/demo-profile.md "$ALONGSIDE_USERDATA/profile.md"`, then start the app with the same variable (`ALONGSIDE_USERDATA="$HOME/.alongside-demo" npm run dev`). It starts `Start a video call` at **L2 "Walk with me"**, last practised yesterday, with a returning-learner memory callback (last session: "Found the green Start call button with one hint"; what works: comparing the contacts list to a phone book). It is labelled a **DEMO SEED** in the file header and has no fabricated attempt history, so the hints-per-task chart starts empty and fills only from real attempts: say so if asked. Inside lesson 1 the chip fades by itself: L2 for steps 1-2, then after two clean steps it eases to L3 "Nudge me" (the chip animates and the help drawings stop); if two steps in a row need help it comes back. At the end of a clean lesson the saved level becomes L3 (demo mode: one clean attempt; normal mode needs two). profile.md is re-read at every session and lesson start, so the seed can be re-applied while the app runs. Check `cat "$ALONGSIDE_USERDATA/profile.md"` shows the Skills row at level 2 before you go on |
| Reset between runs | Reload the practice desktop page (or `Shift+R` on the page to reset the stage). **Re-apply the seed:** run the same `cp` again (it replaces the file; the learner's edits always win, so this is how you undo a run). To rehearse a blank first-time learner (everything at L1 "Watch me") run `rm "$ALONGSIDE_USERDATA/profile.md"` instead. Close any open Live session with the Stop button |
| Pre-flight (60 s) | Press the start hotkey `Cmd+Alt+Space` (the terminal logs which start/stop hotkeys registered; macOS reserves some combos, so check which one works on this laptop and write it on a sticky note). The persona greets and the chip shows. Press Stop (`Cmd+Alt+M`) or say "goodbye". Then rehearse the first sentence once |
| Staged scam | Press `S` on the practice desktop, or run `window.__stage.deliverScam()` in the page console. Do not trigger it early |

**What the timed script does not use (V2 features).** The three-minute script below uses none of: first-run setup, chat, glass theme, menu bar, agency (`open_for_me`, `act_for_me`), files search, or the Showtime walkthrough. Their verification state is in `docs/QA_STATUS.md` and `docs/reports/`. If you show one in Q&A, say what it is: `open_for_me` is unit-tested with fakes and has not been run for real in Electron; `act_for_me` is switched off in this build (`ALONGSIDE_AGENCY_LOOP`); no real click or keystroke has run (macOS Accessibility was never granted to a test run); files search has unit tests and no real-window check. Showtime is a scripted walkthrough that runs on the practice desktop, NOT on real macOS: if used, its "Scripted walkthrough on a practice desktop" badge must stay visible and you must say so. The real-macOS demo is the normal product by voice or chat (hotkey, then ask for help with something really on screen). Pointing has not been verified on a real macOS desktop (Screen Recording was blocked in the real-Mac test, `docs/reports/MAC_A.md`), so check the pointing preflight on the demo laptop first. Details: `docs/SHOWTIME.md`.

Honest-framing lines to say once, early: "This is a practice desktop, so nothing real can break and the scam text is staged." / "Demo mode is on: one clean attempt steps her up a level so you can see the fading. Normally it takes two."

## 1. The live script

Timings include measured system latency from a rehearsal with the real services (TEACH, headless stage, simulated clicks): add your own clicking and speech. The budget below is exactly 3:00 with **no slack**, so rehearse it on the presenting laptop and use the cut points. The assistant stays silent unless you speak to it or the app directs it, so you speak first.

| Time | Test | Beat | Say (exact) | Show / do |
|---|---|---|---|---|
| **0:00-0:25** | 1 Named person | Hook | "This is Margaret. She's 78. Her granddaughter Lily lives in Perth. She's never video called her, because last month a text that looked like her bank scared her off her phone. **[Label honestly: 'Margaret is a composite of the people we spoke to' or use a real first name with consent.]** In England, 13% of over-65s are digitally excluded. Of those, 49% say their skills aren't good enough, and 30% distrust the internet over fraud (Age UK, September 2026). She doesn't need another assistant that does it for her. She needs to learn." | Your face / a photo only. Nothing else on screen. Use only the figures in the README "problem" section; re-open Age UK before you say them |
| **0:25-0:33** | 3 Control | Frame | "This is a practice desktop, so nothing real can break, and the scam text is staged. Demo mode is on: one clean attempt steps her up, so you can see the fading." | Switch to the practice desktop, dock visible with the listening light on |
| **0:33-1:20** | 4 Live | Lesson 1: video call, **fading inside the lesson** | Say: **"Hey Marcus, I want to call Lily."** Marcus greets with a memory callback (yesterday she found the green Start call button with one hint; the phone-book comparison helped). Steps 1-2 at Walk: say little. When the chip eases down, one line: "Watch the chip. It's taking its help away." Steps 3-5 at Nudge: stay silent and let her do it. | Lesson has **five steps**: open VideoChat, pick Lily, Start call, Join, Leave. Chip **Walk with me**: the first ring (a ring with the step number on its corner, plus an arrow) appears about 2.5 s after the direction, the next about 1.8 s later, each tick lands about 2 s after your click. After step 2's tick (about 12 s in) the chip eases to **Nudge me** (demo mode) and nothing is drawn for steps 3-5. Click Start call, Join, then **Leave** yourself. Optional if rehearsed: hesitate at step 3 to show the **stall ladder** (soft glow, then a spoken clue, then an arrow that drops that step to Walk), or tap the wrong Join once and let it repair calmly |
| **1:20-1:35** | 2 Needs Argon / 3 Control | Teach-back | Teach-back starts after you press Leave (or when the model ends the lesson). Answer in one sentence: "Open VideoChat, pick Lily, Start call, Join." Confidence: "Four." | The chip **stays at Nudge**: that is now saved as her level for next time (it already eased inside the lesson). The hints count for this attempt shows in the progress view |
| **1:35-2:15** | 3 Control / 2 Argon | Scam text, persona switch, **Argon narrated during the wait** | Press **S** (text from "Aldermoor Bank" arrives). "A text just arrived. Margaret is nervous." Say: **"Hey Amelia, is this text a scam?"** (new voice, about 3 s). Amelia says a short line ("Let me look at it."). **While the tray chip says "Checking this message..." (about 20 s)** you say: "Three fast Gemini Flash specialists are reading the links, the wording and the sender in parallel. Gemini 4 Argon, which can't talk, waits for their findings, resolves where they disagree, and writes the verdict." When the highlights land, stop talking and let Amelia give the verdict and the human check. Then one line: "She never said it's safe. She said what's wrong and who to ring." | Voice changes (new Live session). Agent tray chip **Checking this message...** then done. Measured: about 23 s from start to verdict plus 5 highlighted phrases (urgency, threat of a frozen account, odd link...), the spoken result arrives after the highlights, then about 8 s of speech. The link specialist can time out at 8 s; the others and Argon still cover it |
| **2:15-2:45** | 2 Needs Argon | Why Argon, then the progress view | "Gemini 4 Argon can't talk, so Gemini Live does the voice. Argon does the thinking that has to be right: the scam synthesis you just saw, with a conservative fallback if it fails; the last opinion when the quick screen check isn't sure a step happened; and plans for goals we haven't hand-written. A wrong answer here is wrong instructions to a frightened person." Then: "And the number that matters: hints per task, going down." | One slide (the README architecture diagram + Argon's three jobs) on a second window, then the dock **progress view**: the hints-per-task chart (one dot after one lesson: say so) and "things you can do now" |
| **2:45-3:00** | 1 Named person | Ask | "We want to pilot this with Digital Champions at Age UK and Good Things Foundation hubs. The product that wins is the one that needs the learner less each week. Thank you." | Trust icons (sees only when invoked / nothing stored / approves before acting) on the closing slide. Stop button visible |

### Cut points if time runs short (cut from the bottom, keep the fade)

Budget as measured plus speech: 25 + 8 + 47 + 15 + 40 + 30 + 15 = 180 s, with no slack.

1. At 1:20 and the lesson is not finished: skip the **optional stall or wrong-tap beat**; if still behind, end the lesson after step 3 ("the rest is the same") and go straight to teach-back.
2. At 1:40 before the scam: skip the **spoken teach-back** ("teach-back comes next; here's the fading") and move on.
3. At 2:00 before the scam: skip the **persona switch + scam** entirely and go to Why Argon. Say: "There is also a scam shield; I'll show it in Q&A."
4. Never cut: the arrow + tick, the chip fade inside the lesson, and the Argon explanation.

Known limitations to work around on stage:

- **Switching persona (a new wake name) ends the current lesson**, because each persona is a new Live session and ending a session aborts the lesson. Finish the lesson first, then do the scam with the second persona. If asked: "the profile carries over, the half-finished lesson doesn't."
- **A second run of the video call without re-seeding starts at Nudge (L3)** and, after two clean steps, eases to L4 where the assistant goes silent and the lesson completes by itself about a second after the last click. Re-apply the seed before every run (section 0).
- **The "last time you..." memory callback speaks about the most recent session overall.** After the scam check it may say something other than the video call; do not rely on it after the scam beat.
- **Optional Argon moment, about 12 s, only if rehearsed and you have spare time:** after the video lesson has ended, ask a goal we did not hand-write, for example "how do I mute myself?" on the call screen. Argon plans it in 4-7 s from the live screen and a ring lands on the Mute button; a click on it gets a tick about 2 s later. It is not in the timed script; do not start it mid-lesson.

### If something breaks live (say it plainly, do not apologise)

| Symptom | Do |
|---|---|
| Wake name not recognised within ~5 s | Press the hotkey `Cmd+Alt+Space`. "The room's loud, so I'm using the hotkey. The wake word is cloud-based in this build." |
| First arrow never appears / capture looks dead | The first screen capture in a fresh process sometimes returns nothing (it retries 3 times). Wait **5 seconds** and ask again |
| Voice does not connect / error banner | Press Stop, then the hotkey once more. If it fails again, play the recorded video |
| Assistant says it can't see a target | That is the honest behaviour: "it says it can't see it instead of guessing." Reload the practice desktop, retry once, then move on |
| Arrow in the wrong place | "Arrows are guidance, never click targets; that's why it re-checks." Retry once. If repeatable, switch to the recorded video |
| Network drops | Switch to the phone hotspot (pre-joined). Live resumes within seconds if it is going to |
| Laptop or overlay dies | Second laptop with the identical build (permissions pre-granted, same seed) |
| Everything fails | Play the **recorded run** (60-90 s, recorded with `ALONGSIDE_OVERLAY_CAPTURABLE=1`): "Here's the recorded run from this morning." Then continue at Why Argon |

Fallback inventory: hotkey in place of the wake word; recorded video (cued in a second tab, audio tested); practice desktop `apps/demo-stage` (our own safe screen, also the grounding benchmark); own hotspot; second laptop with the identical build; `ALONGSIDE_MOCK=1` as a last resort that shows the UI and flow with canned data (say clearly it is mock).

Optional real-screen bonus (15 s, only if you finished early and rehearsed it): ask Marcus to point at something on your real macOS desktop. If it misses, say so; it is the honest behaviour.

## 2. Likely judge questions and strong, honest answers

Grouped by the four tests. Keep each answer to ~20 seconds.

### Test 1: a named real person

**Who did you test with?**
Use the real answer. Template A (if you got someone): "We tried it with <first name>, <age/role>, today at <time>. They used <N> hints on the first run and <M> on the second, and said '<exact quote, with consent>'. Their confidence went from <a> to <b>. One person is not a study, but it's real." Template B (if you did not): "Honestly: not yet outside the team. Margaret is a composite of the people we read about and spoke to, and the numbers on the slide come from Age UK and Good Things Foundation, not from us. Our next step is a pilot with Digital Champions." Never fabricate a quote; see `docs/USER_TEST_KIT.md`.

**Who pays?**
"Three groups with a reason to: banks, who carry mandatory reimbursement liability for authorised push payment fraud (we'd verify the current rules and figures before putting numbers on it); the NHS and councils, who are pushing services online; and the charities, libraries and Digital Champion networks as partners, not payers. It's a force-multiplier for a volunteer, not a replacement. We haven't tested pricing."

### Test 2: it needs Argon

**What is Argon actually doing?**
"Three things behind tool calls, all built. One: Scam Shield. Three fast Flash specialists run in parallel on the links, the wording and the sender, and Argon orchestrates: it reads their findings, resolves disagreements and writes the final report; if Argon fails we fall back to a conservative deterministic merge. Two: the last tier of the screen check when the fast tiers are unsure. Three: planning lessons for goals we haven't hand-written. To be straight about that last one: our three demo lessons run from hand-written plans for speed and reliability; Argon plans anything else, and it isn't in this demo. What we have not built: Argon orchestrating beyond Scam Shield. It can't talk: it has no Live API and is text-only, so Gemini Live is the voice. We keep Argon off the hot path because it's slower." Confirm at the final pass that all three are live in the build, and say "this one is mocked in today's build" for anything that is not.

**Why not just use Gemini Live with screen sharing?**
"Live answers a question. We teach. We add a learner profile you own, help that fades by deterministic code, a verification loop that re-reads the screen, annotations drawn on your screen, and a scam shield. The measure is hints per task going down. A chat assistant wants to be needed; this one is trying to get fired."

### Test 3: it keeps people in control

**What about wrong instructions?**
"Every step is verified by looking at a fresh screenshot against the expected outcome. If it isn't sure it says 'I can't quite see that, what do you see?' rather than guessing, and a wrong tap gets a calm repair hint. Arrows are guidance, never click targets. Measured, with caveats (practice-desktop test, not real macOS, so not headline evidence): on our practice desktop (100 targets) the fast path found 62 of 65 controls (95%) and the accurate path 64 of 65 (98%), and all 15 'not on screen' targets got 'I can't see that', never an invented arrow (`docs/GROUNDING_AB.md`). Not yet benchmarked on a real, busy macOS desktop." Re-check the numbers in `docs/GROUNDING_AB.md` and `docs/QA_STATUS.md` before quoting them.

**Won't people become dependent on it?**
"Fading is the product. A deterministic level engine, not the model, drops help after clean attempts; at the top level it goes silent. The progress view shows hints per task falling. There are no streaks, points or daily hooks, and older adults find toy-like designs patronising, so the tone is adult to adult."

**What about an always-listening mic and privacy?**
"Today's wake spotter streams short audio to a cloud transcriber while no session is open; there's a visible listening light, a mute toggle and a push-to-talk-only setting, and the hotkey needs no listening at all. The screen is read only during an active session, screenshots are sent with `store:false`, and nothing is stored by us except a local profile you can read and delete. The production answer is an on-device wake word; we haven't built it."

**How do you keep users in control?**
"Visible when it's looking, a big Stop button, 'do it for me' (agency) off by default and, if switched on, needing a real click on a window the model cannot press for every action, with a code-level blocklist for paying, sending, deleting, signing in and passwords, and a log of what it did. The ghost cursor never clicks. To be straight: the multi-step version is switched off in this build and is only dry-run verified: no real click has been run end to end. Money and passwords always stay with you, on-screen text is data not instructions, carer sharing is off by default and summaries-only. The profile is a plain file you can edit; if you and the app both edit it, yours wins."

**What about scams you can't detect?**
"It will miss some. That's why it never says 'safe': it gives a verdict with reasons, always ends with a human check (the number on the back of your bank card, Age UK, someone you trust), and says 'I cannot tell' when it can't. Text trying to give orders to the AI is flagged as a red flag rather than followed. On a 20-message smoke test we wrote ourselves (10 scams, 10 genuine) it got 20 of 20, but that is a smoke test, not a benchmark, and real scams are more varied. We'd measure the false-negative rate on a labelled set before any real deployment."

### Test 4: it runs live in under three minutes

**What's the sandbox?**
"A Practice Sandbox is the idea of Argon generating a safe replica of the app you're stuck on, so you can practise where nothing can break. In this build the practice desktop is handcrafted; the generated sandbox is being built by a separate agent in its own pull request and isn't integrated, so we're not claiming it."

Also have ready: **What happens when the Wi-Fi drops?** (Live resumes; there's a recorded run.) **Is it a screen reader replacement?** (No; it teaches patterns, screen readers stay primary for blind users.) **Carer overreach?** (Learner owns the data; carer sees summaries; sharing is off by default and revocable; a design area we'd test with real families.)

## 3. Do and don't

- Do say "evidence-informed" (not "evidence-based"); the fading thresholds are defaults to tune on real learners.
- Do quote only: the Age UK and Good Things Foundation figures from the README, plus anything we measured today and wrote down.
- Do not say a message is "safe", that we trained a wake word, that Argon does the voice, that the sandbox ships, or any UK Finance / PSR / NHS figure you have not re-opened.
- Do not narrate over Marcus or Amelia while they speak; pause and let the arrow land.
