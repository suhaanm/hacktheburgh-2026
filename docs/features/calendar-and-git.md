# Calendar layer and git habits

> The same expert-against-learner idea at the week level and in the commit log.

**Capability:** See the work · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Navigation note (landing).** The lead's views rule (`docs/knack-ux/views.md`, from owner requests 4.1, 4.2, 4.11, 4.12 and 4.17 at about 00:50 UTC) is reorganising where screens live. Where this page says 'More, <screen>', check `apps/dashboard/src/components/home/navModel.ts` on main for the final place. 'Git habits' becomes a section of Growth for programmers ('my commits'); the Calendar ('Week') is no longer a worker destination and its new place is not verified.

This page covers Calendar layer (week ribbon, Outlook and Teams adapters), Git habits for programmers.

## Calendar layer (week ribbon, Outlook and Teams adapters)

**Status:** built · **Page:** `docs/features/calendar-and-git.md` · **Targets:** G-Research

### What it does

Compares a worker's week with an expert's: meeting load, focus blocks and review slots. Suggests changes from a fixed catalogue (focus blocks, batching, auto-hold, off-computer breaks). Outlook and Teams adapters read aggregates only and are off by default.

### How it works

Calendars become counts, durations and enums; no titles, attendees or bodies are stored. The expert reference is a hand-authored role template. Suggestions come from a fixed catalogue through the same guard as every other layer, never free text. A real read-only check of the owner's own calendar needs the owner's approval at run time (decision D26) and stores only counts and durations.

**What is different.** The expert-against-learner comparison is applied to a week, with suggestions from a fixed catalogue and adapters that read aggregates only.

### Where to see it

More, then Calendar (address #/week).

### Demo moment

Open Calendar: the week ribbon, the worker's week against the expert's, and one suggestion with its interval. Say the adapters never write and have not been run on a real account.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Planted problems found (eight types, micro-average): precision 93.9%, recall 98.2%; suggestions against the planted cause: precision 96.4%, recall 89.9%; expert weeks with a suggestion: 0 of 24 | synthetic calendars, 28 people | `evals/report.md (Calendar layer)` |
| 0 of 11,104 planted tokens leaked across 169 outbound requests | synthetic, offline | `evals/report.md (Calendar layer)` |

### Honest limit

Synthetic calendars only. The expert reference is generated from the same template that defines the targets, so agreement is by construction. One read-only aggregate check of the owner's calendar says nothing about anyone else.

### Hackathon target

- **G-Research (make the invisible visible)**: the week made visible against an expert's

## Git habits for programmers

**Status:** built · **Page:** `docs/features/calendar-and-git.md` · **Targets:** G-Research, HRT

### What it does

For programmers: finds commit habits that experts do not have (very large commits, tests not changed with code, fix after fix, reverts, vague messages, late nights) and gives five generic suggestions.

### How it works

Reads the git history on the device. Features are counts and times; commit messages are turned into enums by rules, or by a local model on the Mac for the category, and are not sent out. Each learner is compared with eight experts of the same replicate, with a placebo of expert against expert. Commit sessions are aligned, but git records when a commit landed, not how long the work took, so the alignment sees the shape of sessions and not seconds.

**What is different.** The same comparison is applied to commits, with a placebo of experts against experts and thresholds set on separate seeds from the test seeds.

### Where to see it

More, then Git habits (address #/git). Programmer role only.

### Demo moment

Open Git habits on the programmer example: habits against experts with intervals, and the generic suggestion for each. Say the repository is synthetic.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Precision 100% (116 of 116) [96.8, 100.0]; recall 97% (116 of 120) [91.7, 98.7]; specificity 100% (120 of 120) | synthetic, 120 scripted developers, fresh seeds | `evals/report.md (Git habits)` |
| Placebo (expert against other experts): false flags 1% (5 of 480) [0.4, 2.4] | synthetic | `evals/report.md (Git habits)` |

### Honest limit

Every learner and expert is a scripted persona with planted habits; recovering them shows the features and thresholds work on data built to contain them, not how real developers behave. Habits in the message or the clock are invisible to alignment.

### Hackathon target

- **G-Research (make the invisible visible)**: commit habits made visible
- **HRT (best use of data for predictions and decisions)**: decisions with intervals, thresholds set on separate seeds

## 30-second spoken script

> The same idea, applied to your week and your commits. The calendar layer compares your meetings and focus time with an expert's, and suggests a fixed set of changes. The git layer finds habits like very large commits or fix-after-fix. The Outlook and Teams adapters only read counts and have never been run on a real account. Both are tested on synthetic people, and the screens say so.

## Slide bullets

- Calendar: meeting load and focus blocks against an expert; fixed catalogue of suggestions.
- Outlook and Teams adapters: aggregates only, read-only, off by default.
- Git habits: 116 of 116 flagged habits were planted ones (synthetic).
- Placebo: experts against experts, 1% false flags.
- Synthetic personas only; nothing validated on real people.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (14.5, 14.8)`
- `docs/IDEA_BOARD.md (extensions)`
- `evals/report.md (Calendar layer, Git habits, Limitations register)`
- `docs/DECISIONS.md (D26)`
- `docs/FEATURE_CATALOGUE.md`

## Related pages

`connections.md`, `role-packs.md`, `models-and-routing.md`
