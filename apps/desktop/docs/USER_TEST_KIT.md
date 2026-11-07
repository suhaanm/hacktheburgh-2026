# Real-user test kit (5 minutes, one real person)

Goal: get **one real person** to use Alongside before 15:00 so the demo can say "we tried it with <first name>" truthfully. One honest person beats any claim. Ideal: someone who is not on the team and finds computers harder than you do (a relative, an organiser, a volunteer, a staff member). Any adult who agrees will do; say plainly in your report who they were.

You need: the app running on a laptop with a headset or a quiet corner, this page, a pen or a notes file, 5 minutes.

## 1. Before they sit down (facilitator, 3 minutes)

Use an isolated profile so the export contains only this person's data and your demo seed is untouched.

```bash
# Terminal 1 (from the repo root; the folder is gitignored)
ALONGSIDE_USERDATA="$PWD/.userdata-test1" npm run dev
# Terminal 2
npm run stage          # practice desktop at http://127.0.0.1:5180
```

1. Open `http://127.0.0.1:5180` full screen. Everything on it is fake (a video-call app, a messages app, a settings app). Do not use real accounts, banking or messages.
2. Leave settings at their defaults (`demoMode` on, captions on, big annotations on). **Write down the settings you used** in the notes. Do not use the demo seed profile for a real person: a fresh profile starts every skill at L1 "Watch me" (a ghost cursor shows each step first, then they try), and the assistant stays quiet unless spoken to, so they must ask for something. If you reuse a profile folder, `rm "$ALONGSIDE_USERDATA/profile.md"` returns it to a blank first-time learner.
3. Check it works once yourself with the hotkey `Cmd+Alt+Space` (the persona should greet), then press Stop. Reload the practice desktop.
4. Decide how they start a session: **say the wake name** (see `src/shared/personas.ts`), or you press the hotkey for them if the room is noisy. Note which you used.

## 2. Consent (read this out loud, wait for a yes)

> "We're building an assistant that teaches people to use a computer, and I'd like you to try a short test of **it**, not of you. If anything is confusing, that is our fault, not yours. It takes about five minutes. Everything on this screen is a practice screen, nothing is real, and you won't type any passwords or bank details. I'll take notes, and I'd like to use what you say, with your first name only, in our demo. I won't record you. You can stop at any moment and that's completely fine. It's an AI, not a person. Is that OK?"

- If they say no to being named, report them as "a participant". If they say no to the test, thank them and stop.
- Do not photograph or record without a separate, explicit yes.

## 3. The test (5 minutes)

| Time | What | You say | You do |
|---|---|---|---|
| 0:00-0:30 | Before | "Quick one first: how confident do you feel using video calls and spotting dodgy messages, from 1 (very worried) to 5 (very confident)?" Write the number. | Start the timer. |
| 0:30-1:45 | **Task 1: video call** | "Imagine you'd like to video call your granddaughter Lily. Ask the helper for that." | Say nothing else. Wait. Mark every hesitation. |
| 1:45-3:00 | **Task 2: spot a scam text** | "A text has just arrived. Ask the helper whether it's a scam." | Press `S` on the practice desktop (or run `window.__stage.deliverScam()` in the page console) to deliver the staged text. |
| 3:00-4:00 | **Task 3: bigger text** | "The writing on this screen is small for you. Ask the helper to make it bigger." | Say nothing else. |
| 4:00-5:00 | Feedback | Ask the six questions in section 5, in order. | Write their words, do not correct them. |

Rules for you: do **not** help, point, or explain. If they ask you for help, say "ask the assistant." If they are stuck for over a minute, or look upset, press Stop, say "that one's on us," and move on. Safety first: stop at any time they want.

## 4. What to observe (fill in per task)

| Task | Time taken | Hints used (arrows/clues after a stall) | Wrong clicks (errors) | Where they hesitated (>10 s) | Did the arrows/ticks help? | "I can't see that" or "can't tell" heard? | Worried phrases ("I'm stuck", "oh no") | Exact quotes |
|---|---|---|---|---|---|---|---|---|
| 1 Video call | | | | | | | | |
| 2 Scam text | | | | | | | | |
| 3 Bigger text | | | | | | | | |

Also note: wake word recognised first time? hotkey used? voice too fast or slow? did the voice talk over them? did they speak to it naturally? did they say "show me again" or "let me try"? Did the level chip change?

The app records hints, errors, stalls, teach-back and confidence per attempt in the profile (section 6), so you can cross-check your tally against it.

## 5. Feedback form (read out, six questions)

1. **Confidence.** Before: ____ / 5 (asked at 0:00). After: "Same question again, 1 to 5?" ____ / 5.
2. **What was confusing?** (open) ______
3. **Did the arrows and ticks help?** Yes / a bit / no. "What would you change?" ______
4. **Would you use it?** "On your own, at home, for something like this?" Yes / maybe / no. "Why?" ______
5. **Voice speed.** Too slow / about right / too fast. Too quiet / about right / too loud.
6. **Did it do anything that felt unsafe or pushy?** (open; includes "anything you didn't expect it to look at") ______

Thank them. Tell them what you'll use (first name, quotes, numbers) and that they can change their mind.

## 6. Export the result as demo evidence

The profile is one readable Markdown file, `profile.md`, with the skills table, the confidence log and the **attempt history** (hints, errors, stalls, teach-back, confidence per attempt).

```bash
# With the isolated profile used above:
cat .userdata-test1/profile.md
mkdir -p docs/evidence
cp .userdata-test1/profile.md docs/evidence/test1-profile.md
```

Without `ALONGSIDE_USERDATA` the file is in the app's user-data folder, `~/Library/Application Support/alongside/profile.md`. The same content is available in the app over the `learner:markdown` channel (the dock's profile view, if shipped; see `docs/MANUAL_TESTS.md`). Also screenshot the dock **progress view** (hints-per-task chart) if two attempts were made.

Before you put anything in the repo: delete any line the participant would not want shared, keep first name only, and **do not commit it without their yes**. If in doubt, keep the file local and quote only the numbers.

## 7. How to report honestly

- **One person is a story, not a result.** Say "we tried it with Priya, who used two hints on her first video call and none on the second", not "it works for older adults".
- **Use their real words, exactly, with consent.** Never invent, polish, merge or "improve" a quote. If you did not write it down, you cannot use it.
- **Label composites as composites.** The demo's Margaret is a composite unless you used a real first name with permission. Say "Margaret is a composite of the people we spoke to" (or whatever is true). Never present a persona as a real person.
- **Report the settings.** Say demo mode was on ("one clean attempt steps you up a level, so you'll see fading quickly") if it was.
- **Report failures too.** "She didn't notice the arrow on the first step until it was repeated" is more credible than a clean story, and judges (and the Imperial ML judge) value calibration.
- **Do not claim improvement from one session.** Confidence moved from 2 to 4 in five minutes is an observation, not an effect size.
- **Separate what we measured from what we read.** The Age UK and Good Things Foundation numbers come from them, not from us.
- **If you got nobody**, say so: "not yet outside the team", and show this kit as the plan.

Results card to paste into the demo notes (fill it in only with true values):

```
Who: <first name only, with permission> (<age/role, if they agree>)   When: <time>   Settings: demoMode <on/off>, start by <wake word/hotkey>
Confidence before -> after: <a> -> <b> (1-5)
Hints: video call <n>, scam text <n>, bigger text <n>   Wrong clicks: <n>
Hesitated at: <where>        Arrows helped: <yes/a bit/no>        Would use: <yes/maybe/no>
Voice speed: <too slow/right/too fast>      Felt unsafe: <none / what>
Quote (exact, consented): "<...>"
```
