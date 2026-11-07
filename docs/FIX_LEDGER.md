# Fix ledger (lead, from Sat 7 Nov 2026, about 19:40 GMT)

One list of everything known to be broken, unverified or unfinished, with an owner and a way to know it is closed. The lead updates it at every checkpoint. **Closed** means the lead saw the check pass, not that an agent said so. Owner-only items are at the bottom.

## A. Safety of real-desktop actions (reviewer: evals/review/safety_actuator.md; reproducers in evals/review/safety/)
| id | what | owner | closed when |
|---|---|---|---|
| S-25, S-26 | chord sets canonicalised; DOM read in an isolated world | agent-core (done) | reviewer re-verified 19:27 |
| S-30 | frame captured and encoded in memory only (D30) | agent-core (done) | 48 tests pass, R0 ran with it |
| S-28 | type or fill with an unreadable focus is needs_human; walk same-origin frames | AGENTIC-2 | **closed 7 Nov ~20:00: reviewer 172 of 172 pass** |
| S-27 | check_path also resolves the full path (realpath, stat identity) | AGENTIC-2 | **closed (same run)** |
| S-29 | unnamed AX roles (outside a small allow-list) are needs_human; AXPress counts as a button | AGENTIC-2 | **closed (same run)** |
| queue title | approver title from class and host, never the page label | AGENTIC-2 | test added |
| second read | CDP DOM hit test compared with the isolated-world read; disagreement is unreadable | AGENTIC-2 | test added |
| small items | zero-width and look-alike letters (strip_invisible, mixed script); tighten the BENIGN_SUBMIT prefix list; lock the owner-token consume; RunPermit single use | AGENTIC-2 after the above | tests added |
| gate hash | sha256 over security/*.py, tiers/computer_use.py, safety.py, facts.py recorded in ITERATIONS.md | AGENTIC-2 (last step) | hash in the confirmation run |

Real-click ladder (evals/agentic/REAL_CLICKS.md): R0 ran once on 7 Nov (zero events, capture works, scale agrees, point covered by the Claude window: stop and report). Next: owner moves the window, second R0 (owner go), then the R1 preflight in the owner's terminal. R2 stays NO-GO until R1 is reported and S-28 and S-29 are closed.

## B. Agentic long-horizon (evals/agentic/)
Owner: AGENTIC-2. LH-2 checkpoint and WorkingMemory.snapshot, carry-over across escalation, reader digest memo, StepRecord.verified, FrameRetention and call_context meter wiring, LH-4, LH-5, Gemini comparison, old-goal comparison. Then the lead runs the held-out confirmation (clean n = 4 on seed 9137, injected n = 20 on seed 9138) after the reviewer re-test. Spend so far US$8.54 of the US$20 track (total cap US$60).

## C. Dashboard
| item | owner | closed when |
|---|---|---|
| tsc clean, vitest 465 pass | lead saw 19:3x | done |
| smoke: 4 FAIL (Evidence map, Privacy canary wording, two Explain checks) | DSN | smoke all PASS, honesty wording intact |
| Repeats: delete preview.html and preview.tsx; plain "example data" line instead of a raw engine sentence; richer demo seed | HIT (resumed) | seen in the real shell |
| Home, Firm, Predictions, palette, tour: crash "Element type is invalid" | ADMIN-UI | each renders in the shell, light and dark, 1440 and 390 |
| design sync: remaining screens, Notices | DSN | docs/DESIGN_AUDIT.md complete |

## D. Desktop app
DESKTOP-2 done and committed (7 Nov ~20:00): legacy-remote gating, awareness, Cue and attention wiring, rect content without sensitive controls, S-18 guarded click against fakes, desktop vitest 2651 pass, tsc clean. Open: the 19-check rehearsal (headed Chromium plus the app in dry-run; I cancelled the queued run and will run it myself at a planned time); CueGrounder.recheck (CUEUX, from step.target, landed b8b8fa4); extension/dist rebuild after ROLES' `npm run gen`; tray listening badge and HUD timer for the Live session (cut-line item, Live is flagged off). Not built (owner-blocked): the screen-change watcher (Screen Recording).

## E. Engine, evaluation and honesty
- INSIGHTS: dev evaluation, freeze, then the single held-out run by the lead. Plan committed 7 Nov.
- ATTENTION: frozen config committed (d884d5d); held-out run once; report the cost of the quieter budget.
- ML v2: held-out hazard, controls, ablation, genome; force-add heldout outputs; M5 transfer result stays as reported (failed, simulated participants).
- STUDY-SIM run 5, ROLES (programmer, analyst) pilot, REALISM matrix: agents running; plans are committed; results labelled simulated, never in the live study section.
- ENGINE-EVAL: wire evidence, insights, mlv2, cue, attention, hitlist, realism and roles sections; then `make eval` once, regenerate report and the dashboard fixture.
- Full suites: engine and agent run 19:40 (logs in the session scratchpad); every failure triaged to an owner here.
- Cue: `target.zone` on GET /cue/next is a deferred contract change (D-note by DESKTOP-2).

- ADMIN-UI done and committed. Owner decisions recorded: (1) OWNER ANSWERED: the synthetic firm shows random realistic human names, not pseudonyms. Dashboard side: ADMIN-UI (fixtures by script, `person.name ?? person.label`, visible "Names are made up. This firm is synthetic."). Engine side AFTER the held-out Insights run finishes: INSIGHTS adds a deterministic `name` to admin rows (display only; label stays the stable id), regenerate samples, tests; (2) default landing stays `home`, the demo script opens `#/genome` by deep link; (3) OWNER ANSWERED: keep the old cohort sentence ("new juniors are behind the onboarding target"), no reword; (4) OWNER ANSWERED: remove the word "demo" from every visible frontend string ("Demo view" becomes "View as", "Admin view (demo role)" becomes "Admin view", "Demo data" becomes "Example data": the honesty badge stays, only the word changes); a vitest forbids /\bdemo\b/i in visible strings. OPEN QUESTION to the owner: does "or anything" also mean the example-data and synthetic badges? Those are an honesty requirement (CLAUDE.md), so they stay unless the owner says otherwise in writing.

## F. Integration (lead)
Restart the dev stack on current code (needs the owner's go: the dev agent shows "killed" from the earlier stray kill file and I will not clear it by a back door); set UNDERSTUDY_EXTENSION_ID; flip flags on only after the lead's own end-to-end check; checkpoint commits; README rewrite (it still says the Alongside module list will come later; definition of done needs it, plus how to run and what is new; NARRATIVE agent near the freeze); THIRD_PARTY_NOTICES; CLAIMS.md; README disclosure; `make demo` with wifi off.

## G. Claims that must be corrected before the freeze (lead; NARRATIVE agent near the freeze)
- docs/drafts/{DEVPOST,DEV_POST,README.draft,CLAIMS}.md quote the stuck model's v1 headline (0.436 vs 0.509). Add, next to every quote: the edge over time-since-progress falls from 0.071 to 0.008 to 0.015 nats per bin on three harder synthetic generator families, a v1-trained model is worse than that baseline there, and v1 and v2 both fail on the simulated-participant traces (M5). C04 and C05 get the same sentence.
- The simulated study is a null at the floor (run 4; run 5 pilot stopped): the drafts must say it validated the pipeline and enforcement (zero nudges in post-tests), not that it measured the coach.
- No claim that the gate resists hostile pages from the text-only injected condition (S-19, S-26, S-28 are offline tests).

## Owner-only
Screen Recording and Microphone permissions (R0 needed neither for the display size; later rungs will), moving the Claude window for the second R0, the R1 preflight in the owner's terminal (it needs a real YES and a physical hotkey press), Auth0 domain and client ID, chrome://extensions id, Devpost facts, the sentences for CLAUDE.md about frames (D37) and admin visibility (D41), real Outlook aggregate check approval at run time, the demo rehearsal and the submission.
