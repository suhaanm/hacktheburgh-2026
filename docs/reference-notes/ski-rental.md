# Ski rental with predictions (Kumar, Purohit, Svitkina)

**Source.** "Improving Online Algorithms via ML Predictions", NeurIPS 2018. Not a repo; a paper.

**What I verified (web search, 7 Nov 2026).** The search results confirm the paper, the problem (ski rental, plus non-clairvoyant scheduling) and a deterministic algorithm that is (1 + 1/lambda)-robust and (1 + lambda)-consistent. A full-text copy of the paper (found via the search results, read with a page fetch) gives the rule: with prediction `y` of the number of days, buy cost `b` and `lambda` in (0, 1), if `y >= b` buy at the start of day `lambda * b`, otherwise at the start of day `b / lambda`. Theorem 2.2 gives the constants above. The randomised variant is `1 / (1 - e^(-(lambda - 1/b)))`-robust and `lambda / (1 - e^(-lambda))`-consistent (not used here).

**What I did not see.** The copy I read showed no ceiling brackets, so rounding to whole days (`ceil`) is the spec's and my choice. "Buy at the start of day t" means t - 1 rented days first. I therefore **tested the constants numerically** with ceilings over a grid of `b`, `lambda`, `y` and every true length `x`: cost over `min(x, b)` stays within 1 + lambda when `y = x` and within 1 + 1/lambda always (`tests/handoff/test_skirental.py`).

**Where it lands.** ANA-11, `routines/skirental.py`. `b` is the build cost in units of one manual run; `x` the number of future runs, predicted by the recurrence forecast. Regret is measured against the hindsight best `min(x, b)` and against the break-even rule (buy at day `b`, 2-competitive) on simulated workdays.

**Our additions.** `lambda` is chosen from past forecast error (accurate forecasts, small `lambda`; noisy ones, large), a heuristic and labelled as one.
