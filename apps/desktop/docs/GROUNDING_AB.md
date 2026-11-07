# Grounding A/B, latency tuning and service benchmarks

Owner: SERVICES. Run on 31 Oct 2026 against the live API. Harness in `spikes/grounding/` (own `package.json`), live tests in `src/main/gemini/*.live.test.ts`. Everything below is reproducible; raw results are in `spikes/grounding/results/*.jsonl|json` and `fixtures/scam/results-*.json`.

## TL;DR

| Decision | Choice |
|---|---|
| Grounding method | **Structured `box_2d` from a Gemini vision model** (not `computer_use`, not Argon) |
| Default preset (`ALONGSIDE_GROUNDING_PRESET=fast`) | `gemini-3.5-flash-lite` (thinking `low`, image `high`) first, **escalate to `gemini-3.8-flash`** when it says not-found, confidence < 0.7 or errors. p50 1.2 s, p95 1.7 s |
| `accurate` preset | `gemini-3.8-flash` only (thinking `low`, image `high`). p50 3.4 s, p95 6.8 s |
| Always `accurate` (the `precise` flag) | any step with `safetyCritical=true`, and scam-phrase highlighting |
| Fallback when box calls fail or return an implausible box | `computer_use` dry-run, click point only (nothing is ever executed), confidence 0.5 |
| Hard limits | 6 s per `ground()` (returns `found:false`, reason `timeout`, the call keeps running and warms a 30 s cache); box covering over 50% of the screen is rejected |
| Verifier | lite first (about 1 s), flash on dispute, Argon last; an unsure answer is never a tick |
| Scam Shield | 3 flash specialists in parallel, then Argon (thinking medium) as orchestrator; deterministic conservative merge if Argon fails. p50 9.4 s, p95 10.4 s single call |
| Lesson architect | Argon, thinking `low`, at most 4 steps, hedged request, step 1 grounded on the real screenshot. p50 8.9 s, p95 12.5 s including the grounding check |

If QA's harness shows `fast` under about 92% on the demo targets, flip the default with `ALONGSIDE_GROUNDING_PRESET=accurate` (one env var, read in `src/main/gemini/grounder.ts`). The grounder logs the preset at start-up and, per call, the mode, model and latency; `GroundResult.model` shows which model answered (lite = fast path, flash = escalation or precise path).

## 1. A/B: how to localise a UI element

Targets are natural-language descriptions ("the green Start call button"). Hit = predicted centre inside the ground-truth box. Ground truth is automatic: `getBoundingClientRect()` of a `data-ground-id` element (synthetic fixtures), CSS selector (4 real sites), or STAGE's `__stage.rects()`. Negatives are targets that are NOT on screen: the correct answer is `found:false`.

Fixtures: 8 synthetic UIs (video call, messages with scam text, settings, webmail, login, files, editor with 28 px icon toolbar, cookie banner with a decoy and an 18 px close button) at 1440x900 and 1920x1080, plus gov.uk, Wikipedia, Hacker News and BBC at 1440x900. Prompts carry a prompt-injection guard; all calls are `store:false`.

| Method | n | Hit-rate | Mean IoU | Negatives correct | p50 | p95 |
|---|---|---|---|---|---|---|
| `gemini-3.8-flash` box_2d (thinking low, image high) | 78 | **98%** | 0.83 | 18/18 | 3.8 s | 7.0 s |
| `computer_use` dry-run on 3.8-flash (image ultra_high) | 78 | 98% | n/a (point only) | 18/18 | 5.6 s | 7.3 s |
| `gemini-4-argon` box_2d (thinking low) | 44 | 97% | 0.80 | 11/11 | 4.3 s | 14.5 s |

Conclusions: accuracy is a three-way tie on these fixtures, so choose on latency and output type. box_2d gives a real box (needed for rings and `highlightText`), computer_use gives a point only and is slower, Argon has a bad tail. Not one hallucinated positive on any negative target for any method.

Ground-truth artifact worth knowing: Wikipedia's "Random article" element exists in the DOM but its menu is collapsed. All three methods correctly said "not visible", so the one "miss" in every row above is my ground truth being wrong, not the models. On the 4 real sites the genuine misses were zero for flash.

## 2. Latency tuning (the 3.8 s p50 felt too slow)

Findings:
- **`thinking_level: "minimal"` returns HTTP 400 on `gemini-3.8-flash`** (`THINKING_LEVEL_MINIMAL is not supported for this model`). The thinking table in the docs is right; the skill's migration checklist is wrong. `low` is the floor for flash. `gemini-3.5-flash-lite` does accept `minimal`.
- Flash `low` still spends 300 to 500 thought tokens per call, and that dominates latency. Image width (1024/1280/1920) and `media_resolution` (medium/high) made no meaningful latency difference; a slimmer output schema did not help either.
- Flash-lite is 4-5x faster.

| Config (JPEG q70 inputs) | n | Hit | Neg ok | p50 | p95 |
|---|---|---|---|---|---|
| flash low, 1920 wide, high | 8 | 6/6 | 2/2 | 5.2 s | 6.6 s |
| flash low, 1280 wide, high | 8 | 6/6 | 2/2 | 5.0 s | 8.0 s |
| flash low, 1280 wide, medium | 8 | 5/6 | 2/2 | 4.8 s | 17.2 s |
| flash low, 1024 wide, medium | 8 | 5/6 | 2/2 | 5.7 s | 11.3 s |
| flash low, 1280 wide, medium, slim schema | 8 | 5/6 | 2/2 | 4.8 s | 11.4 s |
| lite minimal, 1280, high | 8 | 6/6 | **1/2** (hallucinated a negative) | 0.9 s | 1.2 s |
| lite minimal, 1280, medium | 8 | 5/6 | 2/2 | 0.9 s | 1.1 s |

Full benchmark (59 targets, 1280-wide JPEG, evidence-first prompt):

| Lite config | Hit | Negatives | p50 | p95 |
|---|---|---|---|---|
| minimal | 91% | 15/15 | 1.07 s | 1.35 s |
| **low** (chosen) | **95%** | 15/15 | **0.88 s** | 1.21 s |
| medium (real + hard subset only) | 88% | 8/8 | 1.23 s | 1.68 s |

Lite is weaker than flash on dense real UIs: on Hacker News it picked the adjacent link ("past" instead of "new"), and it read gov.uk's search box as not-found in one config. That is why the default escalates and why safety-critical paths are `precise`.

## 3. STAGE demo targets: fast vs accurate (the numbers that matter)

`apps/demo-stage` fixtures captured at 1440x900 (all) and 1920x1080 (call screen, scam, display settings), JPEG q80, through the **real** `createGrounder`. 100 targets: 65 UI controls, 20 verbatim text phrases from the scam/genuine messages (ground truth from DOM Range rects), 15 negatives.

| Preset | UI controls (65) | Phrases (20) | All positives (85) | Negatives | p50 | p95 | Over 6 s |
|---|---|---|---|---|---|---|---|
| **fast** | 95% (62/65) | 65% | 88% | 15/15 | **1.16 s** | **1.68 s** | 1 |
| **accurate** | **98%** (64/65) | **90%** | **96%** | 15/15 | 3.4 s | 6.8 s | 6 |

Reading this honestly:
- Production routing sends phrases to `precise` (accurate), so the effective hit-rate with the `fast` default is (62 + 18) / 85 = **94%**, above the 92% bar. UI controls alone: 95% fast vs 98% accurate (3 vs 1 misses, within noise at this n).
- Fast misses: one genuinely wrong button ("Voice call only" pointed at "Start call"), and two cases where it pointed at the label row instead of the toggle ("Camera control under the preview"), which is partly an ambiguous target description. A label-vs-target text-overlap check does not catch these (tested offline: it fires on correct answers too), so it is not implemented.
- Accurate "misses" are mostly my targets: "New message button" is a "+" icon (the model correctly said there is no button with that label), and two phrases appear twice on screen (message bubble and the conversation-list preview).
- 7% of accurate calls exceed the 6 s cap, which is why that preset is only used where correctness beats speed. The capped call is not wasted: it keeps running and fills the cache for the retry.
- `label` was present on 100% of found results.

## 4. Verifier, router, lesson architect, scam analyst: live latencies

| Service | Config | Result | p50 | p95 / max |
|---|---|---|---|---|
| Verifier | lite low, flash, Argon low only on dispute | 6/6 STAGE screens judged correctly, 0 false ticks (all answered at about 1 s, i.e. the lite tier) | 1.0 s | 1.2 s |
| Router | `gemini-3.5-flash-lite` minimal; regex fast path for "stop" | 8/8 intents (after a prompt fix: it first called "make the writing bigger" a settings request) | 0.8 s | 0.9 s |
| LessonArchitect | Argon thinking low, hedged at 7 s, 4 steps, medium image, no Search, step 1 grounded | 10/10 plans valid, step 1 found on screen 10/10, 0 re-plans | plan() 8.9 s (Argon call alone 6.9 s) | 12.5 s |
| ScamAnalyst | 3 flash specialists (cap 5 s) then Argon medium (cap 9 s), hard cap 20 s | 20/20 fixtures correct (below) | 9.4 s | 10.4 s |

Architect detail: with thinking low the Argon call is p50 5.5 s but 2 of 10 first-run calls stalled past the 15 s cap (Argon has a long tail). A hedged second request fired at 7 s removed the timeouts (10/10 afterwards, p95 12.5 s). Cost: an extra Argon call only in slow cases. Without a screenshot (or without the grounding check) plan() is about 7 s; the check adds about 1 s. The model invented UI ("three dots top right, Zoom") when it could not see the screen, so give it a screenshot whenever possible.

### Scam Shield: 10 scam + 10 genuine UK-flavoured fixtures (`fixtures/scam/`)

Generic brands (Brightway Bank, Northfield Energy, Parcel Courier, Revenue Office), `.example` domains, Ofcom drama phone numbers. Written by the same author as the pipeline, so treat as a smoke test, not a benchmark: the hardest items are the genuine bank card alert and the courier "no action needed" note.

| | predicted scam/suspicious | predicted genuine | cannot_tell |
|---|---|---|---|
| truth scam (10) | **10** | 0 | 0 |
| truth genuine (10) | 0 | **10** | 0 |

Before (Flash fast pass + Argon `high`, in parallel): 20/20, p50 14.2 s, p95 21.1 s (4 concurrent).
After medium synthesis (three specialists + Argon medium): 20/20, p50 8.9 s, p95 12.5 s (4 concurrent); sequential single-call subset (n=6): p50 9.4 s, p95 10.4 s.
Accuracy delta of the new pipeline on this set: none. Every red-flag phrase was a verbatim substring of its message (20/20 messages), no advice contained "safe", every report carried the bank-card human check. Argon thinking `low` was not needed because medium met the latency target.

Caveats: the link specialist (flash + `url_context` + `google_search`) takes about 5.8 s with tools and hit its 5 s cap in about half the runs; its findings are then dropped and the other two specialists plus Argon still see the link text. No fixture used a real, resolvable domain, so tool value on live sites is unmeasured.

## 5. API quirks found (all verified against the live API)

1. `thinking_level: "minimal"` is a 400 on `gemini-3.8-flash`; fine on `gemini-3.5-flash-lite`.
2. `computer_use` function calls carry a `safety_decision` (`require_confirmation` for a "Start call" click) inside `arguments`. Irrelevant for a dry run, but a real executor must honour it.
3. `tools: [url_context, google_search]` together with `response_format` JSON schema works on `gemini-3.8-flash`.
4. Per-image `resolution` (`medium|high|ultra_high`) works inside the `input` array; `response_format` is a top-level parameter.
5. The SDK's abort signal is not enough to enforce a deadline; `callModel` races a hard timer against the request.
6. Argon latency has a tail (calls stalling beyond 15 s at thinking low). Hedge or cap it; do not trust a single call.
7. Usage reports `total_thought_tokens: 0` for Argon calls that clearly thought, so token accounting for Argon is understated.
8. Flash thinking `low` with an image still means about 300 to 500 thought tokens; lite is the practical way to get sub-2 s vision answers.

## 6. Unverified / open risks

- Real macOS desktop screenshots (Retina, 2x, many windows) were not benchmarked; all accuracy numbers are on clean synthetic UIs, STAGE, and four public web pages (4 valid real targets). The demo-day accuracy on the user's real screen is unproven.
- Capture JPEG quality and width in production may differ from the q80 / native width I used.
- Scam fixtures are author-written; real-world scams are more varied.
- Roughly 750 live API calls were made in total (estimated, not counted exactly) (benchmarks, tuning, STAGE re-runs, scam before/after, service checks), above the original 200 guideline; the coordinator approved the extra budget for the benchmark, tuning, STAGE and scam work.

## 7. Reproduce

```
python3 -m http.server 5180 --directory apps/demo-stage        # STAGE
cd spikes/grounding && node capture.mjs && node capture.mjs --only-hard && node capture-stage.mjs
node run-bench.mjs flash_box p1440 50                          # also cu_flash, argon_box; then: node score.mjs
node tune.mjs && node score-tune.mjs
RUN_LIVE=1 STAGE_BENCH=1 npx vitest run src/main/gemini/stage-bench.live.test.ts   # then: node spikes/grounding/score-stage.mjs --misses
RUN_LIVE=1 SCAM_FIXTURES=1 SCAM_TAG=run npx vitest run src/main/gemini/scam-fixtures.live.test.ts
RUN_LIVE=1 ARCH_BENCH=1 npx vitest run src/main/gemini/architect-bench.live.test.ts
RUN_LIVE=1 npx vitest run src/main/gemini/live.test.ts          # router, verifier, architect checks
```
