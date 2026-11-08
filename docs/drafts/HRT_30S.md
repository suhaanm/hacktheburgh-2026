# HRT 30-second cut (predictions and decisions)

Written by Track H, 8 Nov 2026. Replaces the HRT row of `docs/KNACK_DEMO.md` section 4.3 with shots of the two new Evidence blocks. Every number carries its row in `docs/drafts/CLAIMS_HRT.md` (generated from the reports); `tests/hrt/test_brief.py` checks that each number in the voiceover below appears in the generated files. Everything on screen is from generators we wrote and says so; the live study has not run.

**Where.** Knack, Admin view, More, Evidence (the page is a reviewer's row, not a worker screen). The blocks are "Does it hold out of time?" and "Does the rule beat the naive one?". Take it with the engine answering, or in the example view, which reads the same report.

| Shot | Time | Screen and action | Voiceover (spoken) | Hold on screen | Source |
|---|---|---|---|---|---|
| H1 | 0:00 to 0:09 | Evidence, scroll to "Does it hold out of time?". The reliability diagram and the large figure | "Every forecast is written to a ledger before its outcome exists, then scored forward in time. Where the model was fitted it beats the best naive predictor by 0.079 nats, and we print that its intercept is off." | the figure -0.079 with its interval [-0.085, -0.074]; the intercept line "+0.075 [0.002, 0.162]" | C91, C92 |
| H2 | 0:09 to 0:18 | Open "The worlds, one row each". The three shifted rows, then the Guard flags column | "Change the generator and the same model is worse than a one-line baseline, up to 0.513 nats. A guard that watches the ledger flags 8 of 8 deployments, and 0 of 8 where nothing changed." | the "model worse than" lines and the flags column "8 of 8", "0 of 8" | C93 |
| H3 | 0:18 to 0:26 | Scroll to "Does the rule beat the naive one?". The four figures | "Each decision is scored against a naive policy and an oracle, four contrasts registered in advance. All four win, and building at once beats our own build-timing rule." | the four cards; the note "Four wins is what one expects when the same people write the generator and the rule" | C96, C97 |
| H4 | 0:26 to 0:30 | Back to the first headline | "Eight of ten registered claims passed. The two that did not are on this page." | the headline "8 of 10 registered claims passed; P2 and P6a did not" | C90 |

Spoken length is about 80 words, which is tight for 30 seconds; cut the second clause of H1 if the take runs long (the intercept line stays on screen).

**Do not say.** That the stuck model "works" or "generalises": scored forward in time on other generators it is worse than the best naive predictor (C93). That any of this is measured on people (it is not; C70). That four wins of four is evidence the rules are good: we wrote the generators, the costs and the oracles (C96).

**If it fails.** The blocks are `pending` until `evals/report.json` carries the `hrt_ledger` and `hrt_decisions` sections (`python -m understudy_engine.eval --merge --only hrt_ledger,hrt_decisions`, then `node apps/dashboard/scripts/sync-eval-fixture.mjs` for the offline fixture); a pending block says why in one line. Never show the dev result: `evals/hrt/results/dev_*.json` is for debugging only and is never read by the report.
