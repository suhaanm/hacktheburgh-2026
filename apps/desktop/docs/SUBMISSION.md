# Submission checklist

**Hard deadline 16:00 GMT. Revised clock (TEAM_BRIEF_V2, 14:25): features integrated and green by 15:25, final regression and docs 15:40, submit 15:50.** The older plan (freeze 15:10, submit 15:40) is superseded. Stage demos 16:30.

What the event asks for (from the event page and the team's planning notes): the submission goes in **via GitHub or Kaggle**. *Not verified from a primary page by DOCS:* the exact form fields (track, team name box, video link), whether a demo video is required, and any IP or licence terms for submissions. **Open the event/submission page and confirm each field before 15:25.** If anything below conflicts with the event page, the event page wins.

We submit a **GitHub repository**: `https://github.com/suhaanm/deepmind-hackathon` (remote `origin`, branch `main`). If you submit through Kaggle, follow the event page's instructions and link this repo plus the README; do not duplicate the code.

## Checklist (tick as you verify; the right-hand column is how)

| # | Item | How to verify |
|---|---|---|
| 1 | **Repo is public** (it is **private** right now) | `gh repo view suhaanm/deepmind-hackathon --json visibility` prints `PUBLIC`; open the URL in a private window while logged out |
| 2 | **README** renders: pitch, problem with sourced stat, what it does, why Argon, diagrams, quickstart, limitations, credits | Open the repo page; the two mermaid diagrams must draw (if not, the text above each still stands) |
| 3 | **`.env` is not committed and is ignored** | `git check-ignore -v .env` prints a `.gitignore` rule; `git ls-files .env` prints nothing |
| 4 | **No secrets anywhere in history** | Run the scan below: it must print `0` |
| 5 | **`.env.example` has no real key** | `grep '^GEMINI_API_KEY=' .env.example` shows an empty value |
| 6 | **Builds and tests pass from a clean clone** | In a fresh folder: `git clone <repo> && cd deepmind-hackathon && npm install && npm run typecheck && npm test && npm run build` |
| 7 | **Licence** present | `LICENSE` is MIT (user decision, 15:29). Check the README says MIT and `package.json` has `"license": "MIT"`. Optionally replace "The Alongside authors" with team names |
| 8 | **Third-party notices** complete | `THIRD_PARTY_NOTICES.md` lists every `Adapted from` file (check: `grep -rn "Adapted from" src apps scripts`; 16 files at 14:50 GMT: 11 from farzaa/clicky including `src/main/agency/policy.ts` and `audit.ts`, 5 from the Gemini Live example); Sentient OS (AGPL) is listed as "not used" (`grep -ri sentient src` prints nothing). `npm run submit-check` runs the same coverage check |
| 9 | **Team names** in the README | The README has a Team line; confirm every member is named (open point: names not yet supplied to DOCS) |
| 10 | **Demo video fallback recorded** (60-90 s, with sound) | Recorded with `ALONGSIDE_OVERLAY_CAPTURABLE=1 npm run dev` so arrows show; plays from the presenting laptop and the second laptop; link it in the README or the form if the event allows |
| 11 | **Nothing large or private committed** | `git ls-files | wc -l` is a few hundred; no `node_modules`, `.userdata*`, audio, screenshots of real people; `git count-objects -vH` size is modest |
| 12a | **Screenshots contain no personal info** | Look through every image under `docs/*shots*/` and `docs/*.png|jpg` before the repo goes public: real-screen shots show the macOS menu bar (username, clock, other apps). `docs/overlay-shots/real-*.jpg|png` are already gitignored (only `real-check.json` is kept as evidence); check the rest by eye |
| 12 | **Real-user evidence** (if you have it) is consented and trimmed | `docs/evidence/*` reviewed per `docs/USER_TEST_KIT.md`; otherwise leave it out of the repo |
| 13 | **Claims match the build** | README "Why Argon" and `docs/DEMO_SCRIPT.md` list only things that are live in the build; anything mocked is labelled. V2 items to state honestly: `act_for_me` is flagged off (`ALONGSIDE_AGENCY_LOOP=1`); no real click, keystroke, type or scroll has run (macOS Accessibility never granted to a test run); files search and first-run setup have not been run in a real Electron window; the Showtime walkthrough is scripted, not live, and says so with a badge. See `docs/AGENCY.md`, `docs/FILES.md` and `docs/reports/` |
| 14 | **Submit** on the page (GitHub link / Kaggle) and screenshot the confirmation | Save the commit SHA you submitted: `git rev-parse HEAD` |

### Read-only verification commands

```bash
cd <repo root>

# 3. .env ignored and untracked
git check-ignore -v .env
git ls-files .env                      # must print nothing

# 4. secrets: any Google API key shaped string in the working tree (excluding .env) and in every commit
grep -rIlE 'AIza[0-9A-Za-z_-]{30,}' . --exclude-dir=node_modules --exclude-dir=.git --exclude=.env
for c in $(git rev-list --all); do git grep -IlE 'AIza[0-9A-Za-z_-]{30,}' "$c"; done | wc -l    # expect 0
git log --all --name-only --pretty=format: | grep -E '(^|/)\.env($|\.)' | sort -u            # only .env.example is OK

# 6. quality gate
npm run typecheck && npm test && npm run build
```

(These print file names or counts only, never the secret.)

## Commit and push steps (for the user; DOCS does not run them)

State when this was updated (14:50 GMT): two commits (`bb56f5d` "WIP: Alongside scaffold, contracts and first modules" and `ff7b7b0` "WIP checkpoint: real dock, live controller, services, scam agents, voice audition") exist locally; whether they are on `origin/main` was not checked by DOCS. Much later work, including all V2 features, is uncommitted. The repo was private when last checked. Fallback tag `stable-1357` exists (from the team brief).

```bash
cd <repo root>

# a) See what you are about to commit; make sure .env is not in the list
git status --short
git check-ignore -v .env                       # must print a rule; if it prints nothing STOP

# b) Stage, then double-check the staged list for secrets or junk
git add -A
git diff --cached --name-only | grep -E '(^|/)\.env$' && echo "STOP: .env is staged" || echo "ok: .env not staged"
git diff --cached --name-only | grep -vE '^tools/voice-audition/' | grep -E 'node_modules|\.userdata|\.wav$|\.aiff$|\.log$' && echo "STOP: junk staged" || echo "ok: no junk"   # tools/voice-audition/*.wav (about 7 MB) is intended

# c) Commit and push
git commit -m "Alongside: final submission (docs, demo script, test kit, notices)"
git push origin main

# d) Make the repo public (required for submission) and check it
gh repo edit suhaanm/deepmind-hackathon --visibility public --accept-visibility-change-consequences
gh repo view suhaanm/deepmind-hackathon --json visibility,url
git rev-parse HEAD                              # note the SHA you submit
```

If the push is rejected (someone pushed from another machine): `git fetch origin && git status`, then `git pull --rebase origin main` and push again. Do **not** `git push --force` unless you know exactly what you are overwriting.

**If a secret was ever committed:** rotate the key first (Google AI Studio), then fix the repo. Because history is short, the safest repair is to delete and recreate the GitHub repo from a clean commit. Do not leave a leaked key live in the meantime.

**Editing after the push:** you can push again any time before 16:00; tell the form which commit you submit. Do not change the README claims after the demo run without re-checking them.

## Licence

**Decision (user): MIT.** `LICENSE` (MIT, "The Alongside authors", 2026) is in the repo root, `package.json` declares `"license": "MIT"`, and the README states it. Adapted third-party code keeps its own notices (`THIRD_PARTY_NOTICES.md`). To put real names in, edit the copyright line in `LICENSE` and the README line "Alongside's own code".

## Before recording the fallback video, and on the second laptop

- **Permissions follow the responsible app.** macOS attributes Screen Recording and Microphone to the app that launched Electron, not only to the binary. Launch `npm run dev` from a Terminal (or IDE) that has **Screen & System Audio Recording and Microphone** enabled, or enable `node_modules/electron/dist/Electron.app` (it shows as "Electron") under both. Launching via `open -n -a .../Electron.app` is denied unless that app was granted itself. After toggling a permission, fully quit and relaunch (quit the host Terminal completely).
- **Record with `ALONGSIDE_OVERLAY_CAPTURABLE=1 npm run dev`.** The overlay is protected from capture by default, which makes it invisible to QuickTime, OBS and screenshots.
- **Present the practice desktop in fullscreen (F)** so the macOS Dock cannot hide targets at the bottom.
- **First capture can look dead.** The first screen capture in a fresh process sometimes returns nothing (capture retries 3 times); wait 5 seconds and try again.
- **Pointing check before you record or present:** start the app, wake it, ask it to point at something and confirm a ring appears.

## What to have open at 15:25

Event submission page, this checklist, the GitHub repo URL in a logged-out window, the fallback video file, and the team's names spelled correctly.
