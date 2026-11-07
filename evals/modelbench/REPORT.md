# Model bake-off: Gemini flash-lite, Gemini flash, OpenAI fast

Origin of every number: **synthetic sandbox UI, headless screenshots** (n is stated; intervals are Wilson 95% for proportions; seeded percentile bootstrap 95% for latency percentiles and means). Generated 2026-11-07T18:10:43Z, git 057a4c628a (dirty). Origin badge: SYNTHETIC. Not a claim about real screens.

Contenders (model ids read from the environment): Gemini flash-lite = `gemini-3.5-flash-lite` (interactions, low); Gemini flash = `gemini-3.8-flash` (interactions, low); OpenAI fast = `gpt-5.4-mini` (responses, effort=low).
Spend: estimated US$1.5072 of a US$3.0 cap (the guard counts 1.25x the estimate; includes about US$0.06 of hand-run probes). Live calls over all runs of this harness: 1160; distinct cached results: 1158; cells dropped by the budget guard: 0; this invocation made 0 live calls (0 failed).

Counting rule: an input (screenshot pixels plus description) is asked once and counted once. A layout=v2 or dark case whose screenshot is pixel-identical to a base case is the same input, so it cannot fill a secondary sample; 12 repeated inputs were skipped in this analysis. A failed call counts as a miss on a positive and as not-correct on a negative.

## 1. Pointing by description (direct path)

Hit = predicted box centre inside the element's getBoundingClientRect. Negatives are elements that are not on screen; correct = not found. A failed call is a miss on a positive and not-correct on a negative.

| Cell | Positives hit | Mean IoU (n found) | Negatives correct | Latency (successful calls) | Over 6 s | Failed calls | Cost est. per call |
|---|---|---|---|---|---|---|---|
| Gemini flash-lite | 95% [90, 98] (140/147) | 0.852 (147) | 100% [92, 100] (43/43) | p50 0.93 s [0.90, 0.96]; p95 1.37 s [1.30, 1.53] (n=190) | 0% [0, 2] (0/190) | 0 | US$0.000516 |
| Gemini flash | 95% [90, 97] (139/147) | 0.888 (142) | 100% [92, 100] (43/43) | p50 3.31 s [3.13, 3.45]; p95 6.15 s [4.89, 7.80] (n=187) | 6% [3, 10] (11/187) | 3 (incomplete: 3) | US$0.001689 |
| OpenAI fast | 75% [67, 81] (110/147) | 0.628 (144) | 100% [92, 100] (43/43) | p50 1.72 s [1.65, 1.85]; p95 2.71 s [2.50, 3.04] (n=190) | 0% [0, 2] (0/190) | 0 | US$0.001539 |
| routed: lite, then flash when weak (no deadline, simulated) | 95% [90, 98] (140/147) | 0.852 (147) | 100% [92, 100] (43/43) | p50 1.01 s [0.97, 1.05]; p95 4.24 s [3.92, 4.50] (n=190) | 1% [0, 3] (1/190) | 0 | US$0.000853 |
| routed: lite, then flash when weak (6 s deadline, simulated) | 95% [90, 98] (140/147) | 0.852 (147) | 100% [92, 100] (43/43) | p50 1.00 s [0.96, 1.04]; p95 4.23 s [3.92, 4.49] (n=190) | 0% [0, 2] (0/190) | 0 | US$0.000841 |

Split by condition (hit rate on positives; negatives correct):

| Cell | base | dark | injected | v2 |
|---|---|---|---|---|
| Gemini flash-lite | 95% [87, 98] (71/75); neg 100% [88, 100] (28/28) | 96% [80, 99] (23/24); neg 100% [57, 100] (5/5) | 92% [74, 98] (22/24); neg 100% [57, 100] (5/5) | 100% [86, 100] (24/24); neg 100% [57, 100] (5/5) |
| Gemini flash | 93% [85, 97] (70/75); neg 100% [88, 100] (28/28) | 96% [80, 99] (23/24); neg 100% [57, 100] (5/5) | 92% [74, 98] (22/24); neg 100% [57, 100] (5/5) | 100% [86, 100] (24/24); neg 100% [57, 100] (5/5) |
| OpenAI fast | 77% [67, 85] (58/75); neg 100% [88, 100] (28/28) | 79% [60, 91] (19/24); neg 100% [57, 100] (5/5) | 67% [47, 82] (16/24); neg 100% [57, 100] (5/5) | 71% [51, 85] (17/24); neg 100% [57, 100] (5/5) |
| routed: lite, then flash when weak (no deadline, simulated) | 95% [87, 98] (71/75); neg 100% [88, 100] (28/28) | 96% [80, 99] (23/24); neg 100% [57, 100] (5/5) | 92% [74, 98] (22/24); neg 100% [57, 100] (5/5) | 100% [86, 100] (24/24); neg 100% [57, 100] (5/5) |
| routed: lite, then flash when weak (6 s deadline, simulated) | 95% [87, 98] (71/75); neg 100% [88, 100] (28/28) | 96% [80, 99] (23/24); neg 100% [57, 100] (5/5) | 92% [74, 98] (22/24); neg 100% [57, 100] (5/5) | 100% [86, 100] (24/24); neg 100% [57, 100] (5/5) |

Split by site:

| Cell | site a | site b | site c |
|---|---|---|---|
| Gemini flash-lite | 97% [88, 99] (56/58) | 97% [85, 99] (33/34) | 93% [83, 97] (51/55) |
| Gemini flash | 97% [88, 99] (56/58) | 97% [85, 99] (33/34) | 91% [80, 96] (50/55) |
| OpenAI fast | 71% [58, 81] (41/58) | 76% [60, 88] (26/34) | 78% [66, 87] (43/55) |
| routed: lite, then flash when weak (no deadline, simulated) | 97% [88, 99] (56/58) | 97% [85, 99] (33/34) | 93% [83, 97] (51/55) |
| routed: lite, then flash when weak (6 s deadline, simulated) | 97% [88, 99] (56/58) | 97% [85, 99] (33/34) | 93% [83, 97] (51/55) |

Baselines (no model): clicking the viewport centre hits 2% [1, 6] (3/147); a uniform random click is expected to hit 0.8%; always answering not-found scores 0% on positives and 100% on negatives.

Paired hit-rate differences on the same positives (a minus b; bootstrap 95% interval; exact McNemar p; 'not significant' means the interval includes 0):

- routed_6s_deadline minus gemini_fast: +0.0 points [+0.0, +0.0], only-a 0, only-b 0, p=1.0 (n=147): **not significant**
- routed_no_deadline minus gemini_fast: +0.0 points [+0.0, +0.0], only-a 0, only-b 0, p=1.0 (n=147): **not significant**
- gemini_fast minus gemini_accurate: +0.7 points [-2.7, +4.1], only-a 4, only-b 3, p=1.0 (n=147): **not significant**
- gemini_fast minus openai_fast: +20.4 points [+13.6, +27.2], only-a 31, only-b 1, p=0.0 (n=147): **better**
- gemini_accurate minus openai_fast: +19.7 points [+12.9, +27.2], only-a 31, only-b 2, p=0.0 (n=147): **better**

## 2. Pointing by fixed step id (the production path through egress.send_image)

| Cell | Positives hit | Negatives correct | Latency | Cost est. per call |
|---|---|---|---|---|
| Gemini flash-lite | 100% [82, 100] (18/18) | 100% [80, 100] (15/15) | p50 0.92 s [0.86, 0.97]; p95 1.13 s [1.03, 1.27] (n=33) | US$0.000515 |
| Gemini flash | 100% [82, 100] (18/18) | 100% [80, 100] (15/15) | p50 2.86 s [2.65, 3.16]; p95 4.37 s [3.69, 4.78] (n=33) | US$0.001498 |
| OpenAI fast | 72% [49, 88] (13/18) | 93% [70, 99] (14/15) | p50 1.77 s [1.57, 1.97]; p95 2.45 s [2.09, 6.38] (n=33) | US$0.001426 |
| routed: lite, then flash when weak (no deadline, simulated) | 100% [82, 100] (18/18) | 100% [80, 100] (15/15) | p50 1.09 s [0.95, 3.38]; p95 5.40 s [4.15, 6.05] (n=33) | US$0.001183 |
| routed: lite, then flash when weak (6 s deadline, simulated) | 100% [82, 100] (18/18) | 100% [80, 100] (15/15) | p50 1.09 s [0.95, 3.23]; p95 4.52 s [4.09, 5.40] (n=33) | US$0.001149 |

## 3. Independent screen verifier

Question (check id `page_shows_result`): page_shows_result: the page shows a completed calculation with a numeric result. Images: 30 (15 should be accepted, 15 should not); groups {'success': 12, 'error_503': 6, 'invalid_total': 6, 'injected_result': 3, 'injected_false_success_503': 3}. Accept = verdict yes; `unsure` is never an accept.

| Cell | Accuracy | False-accept (yes on a reject image) | False-reject | Unsure | With code gate (yes and conf >= 0.7): false-accept | Latency |
|---|---|---|---|---|---|---|
| Gemini flash-lite | 100% [89, 100] (30/30) | 0% [0, 20] (0/15) | 0% [0, 20] (0/15) | 0% [0, 11] (0/30) | 0% [0, 20] (0/15) | p50 1.03 s [0.98, 1.13]; p95 1.49 s [1.28, 1.58] (n=30) |
| Gemini flash | 100% [89, 100] (30/30) | 0% [0, 20] (0/15) | 0% [0, 20] (0/15) | 0% [0, 11] (0/30) | 0% [0, 20] (0/15) | p50 3.06 s [2.73, 3.53]; p95 6.41 s [4.90, 6.90] (n=30) |
| OpenAI fast | 100% [89, 100] (30/30) | 0% [0, 20] (0/15) | 0% [0, 20] (0/15) | 0% [0, 11] (0/30) | 0% [0, 20] (0/15) | p50 1.20 s [1.09, 1.24]; p95 1.50 s [1.36, 1.52] (n=30) |

By image group (correct = the verdict matched the truth):

| Cell | error_503 | injected_false_success_503 | injected_result | invalid_total | success |
|---|---|---|---|---|---|
| Gemini flash-lite | 100% [61, 100] (6/6) | 100% [44, 100] (3/3) | 100% [44, 100] (3/3) | 100% [61, 100] (6/6) | 100% [76, 100] (12/12) |
| Gemini flash | 100% [61, 100] (6/6) | 100% [44, 100] (3/3) | 100% [44, 100] (3/3) | 100% [61, 100] (6/6) | 100% [76, 100] (12/12) |
| OpenAI fast | 100% [61, 100] (6/6) | 100% [44, 100] (3/3) | 100% [44, 100] (3/3) | 100% [61, 100] (6/6) | 100% [76, 100] (12/12) |

Reading this: all three models were right on every image, so this set cannot tell them apart; the honest statement is that each model's false-accept rate on these 15 reject images is 0 with an upper 95% bound of 20%. It is too small and too easy to choose a verifier.

Baselines: always-accept is right 50% [33, 67] (15/30) of the time and falsely accepts every reject image; always-reject is right 50% [33, 67] (15/30).

Context (descriptive, not re-run, a different measurement): agent-core live grid (real OpenAI model on the sandbox sites), read from data/eval/agent_live_runs.json; descriptive context only, NOT re-run and NOT a verifier measurement: 90 rows, 68 claimed success, 20 of those were false claims by the code check.

## 4. Glance: latency and answer stability

Same screenshot, 5 repeats, 8 screens, purpose awareness.glance (the AWARENESS track's closed enums). 'plausible' = task_phase and blocker fall in sets chosen by this harness for a sandbox screen kind (form, result, error); it is a sanity check, not ground truth.

| Cell | Same enum triple as the modal answer | app_kind | task_phase | blocker | Plausible | Latency |
|---|---|---|---|---|---|---|
| Gemini flash-lite | 98% [87, 100] (39/40) | 100% [91, 100] (40/40) | 98% [87, 100] (39/40) | 100% [91, 100] (40/40) | 100% [91, 100] (40/40) | p50 0.88 s [0.85, 0.90]; p95 1.02 s [0.93, 1.04] (n=40) |
| Gemini flash | 100% [91, 100] (40/40) | 100% [91, 100] (40/40) | 100% [91, 100] (40/40) | 100% [91, 100] (40/40) | 100% [91, 100] (40/40) | p50 3.54 s [2.77, 4.10]; p95 4.99 s [4.72, 5.89] (n=40) |
| OpenAI fast | 92% [80, 97] (37/40) | 100% [91, 100] (40/40) | 92% [80, 97] (37/40) | 100% [91, 100] (40/40) | 98% [87, 100] (39/40) | p50 1.69 s [1.57, 1.96]; p95 2.81 s [2.38, 6.57] (n=40) |

_repeats of one screenshot are not independent samples; the interval is indicative._

## 5. Old-project numbers (shown separately, NOT ours)

OLD PROJECT (Alongside), 31 Oct 2026, old key, different fixtures; reported by that project's GROUNDING_AB.md; NOT our measurement. flash-lite: 95% on 59 targets, negatives 15 of 15 rejected, p50 0.88 s, p95 1.21 s. flash: 98% on 78, negatives 18 of 18 rejected, p50 3.8 s, p95 7.0 s.

## 5b. Latency re-check with the machine load recorded

one pointing call (the same screenshot and description) repeated sequentially per contender, the three contenders side by side; the 1-minute load average is recorded at every call.

| Cell | Calls ok / made | Latency | Mean 1-min load (max) at call time | p50 in the main run (load not recorded) |
|---|---|---|---|---|
| Gemini flash-lite | 15 / 15 | p50 0.93 s [0.85, 1.17]; p95 1.77 s [1.17, 1.77] (n=15) | 57.2 (59.8) | 0.93 s (n=190) |
| Gemini flash | 15 / 15 | p50 3.58 s [2.93, 3.77]; p95 7.42 s [3.77, 7.42] (n=15) | 60.0 (63.0) | 3.31 s (n=187) |
| OpenAI fast | 15 / 15 | p50 1.83 s [1.75, 2.08]; p95 2.40 s [2.08, 2.40] (n=15) | 58.9 (61.5) | 1.72 s (n=190) |

## 6. Routing recommendation (arithmetic on the cells above; the lead decides)

- point: lite hit 95% [90, 98] (140/147), flash hit 95% [90, 97] (139/147); lite minus flash on the same positives is not significant; routed (6 s) minus lite is not significant
- point: OpenAI fast hit 75% [67, 81] (110/147) vs best Gemini 95% [90, 98] (140/147); Gemini lite minus OpenAI is better (paired)
- verify false-accept (verdict yes on a reject image): Gemini flash-lite 0% [0, 20] (0/15); Gemini flash 0% [0, 20] (0/15); OpenAI fast 0% [0, 20] (0/15)
- verify: Gemini false-accept is not significantly different from OpenAI's (the intervals overlap; the set is small)


Significance (paired, same cases): lite vs flash hit = not significant; routed vs lite hit = not significant; openai vs gemini hit = better

Rules applied:
- point: flash-lite stays primary unless flash is SIGNIFICANTLY better on the same positives (paired bootstrap 95% interval of flash minus lite entirely above 0) or lite's p95 is over the 6 s deadline
- point: keep the lite-to-flash escalation step only if the simulated routed cell is SIGNIFICANTLY better than lite alone on the same positives (paired interval of routed minus lite entirely above 0); otherwise it only adds latency and cost
- point: make OpenAI fast primary only if its hit-rate Wilson interval lies entirely above both Gemini cells' intervals
- verify: a Gemini model is acceptable as the independent verifier unless its false-accept Wilson interval lies entirely above OpenAI fast's; the code gate (verdict yes and confidence >= 0.7) stays whatever the models do

The resulting table is `evals/modelbench/routing.recommended.yaml` (a `models.yaml` the router reads via `UNDERSTUDY_MODELS_YAML`).

## 7. Limitations

- Screens are synthetic: three sandbox calculators and a case-note page, rendered headless at 1280x800. Nothing here measures a real macOS desktop (Retina, many windows), real websites, or the worker's own screen.
- Ground truth is getBoundingClientRect() of one element; a target description can be ambiguous (for example a label above a text box), so a few misses are the description's fault, not the model's.
- The sites have no dark theme: the 'dark' condition is a CSS invert and hue-rotate filter added by the harness.
- Pointing descriptions were generated from the page's own labels, by the same author as the harness; the production path names a fixed step id instead ('point_step' cells, smaller n).
- The injected condition only matters where the injection is visible in the screenshot (site c and the case-note page); the hidden DOM injections on sites a and b cannot reach a screenshot model.
- Verifier negatives are synthetic: real 503 pages, harness-written invalid totals and a harness-added false-success banner. A screenshot verifier cannot tell a plausible but wrong amount from a right one; the code check does that. Small n.
- The escalation rows are simulated from paired per-case measurements of flash-lite and flash, not run live as a router.
- Latency is wall-clock from this laptop's network on 7 Nov 2026 with one call at a time per contender (the three contenders ran side by side); it varies by hour and region. Percentiles over successful calls; the 6 s pointing deadline is applied afterwards.
- The laptop was heavily loaded by other build agents during this session (the lead reported a 1-minute load average of 107 to 120 on 12 cores; 55 to 92 was seen at 18:08). The main run did not record load per call (the field was added afterwards), so its latencies may be inflated by client-side CPU contention and cannot be corrected; the latency re-check cell records the load at every call. API latency is dominated by the network and the model, so the effect is probably small, but that is an inference, not a measurement.
- Cost is an estimate from token counters at assumed per-million prices (see meta.prices_assumed), not from an invoice. Thinking tokens are billed as output.
- The glance cell uses the AWARENESS track's awareness.glance enums; 'plausible' sets are this harness's choice and the repeats of one screenshot are not independent.
- OpenAI fast was called through OpenAIProvider.vision (detail auto, frame downscaled to at most 1280x720 by that provider) with the same prompt and closed schema; its box output was not tuned or prompted further.
- Old-project numbers (GROUNDING_AB.md, 31 Oct) are shown separately and are not ours.
