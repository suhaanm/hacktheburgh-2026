"""A deterministic token estimator. No tokenizer, no model, no network.

Why an estimator: the context library must give the same answer on every machine, offline, and be cheap enough to call on every
step. The provider's own usage fields stay the truth for cost; the meter keeps both numbers so the error of this estimate can be
reported (`estimate_error`). Two things are assumed and labelled as assumptions:

* text: about 3.6 characters per token for English and JSON together (prose is nearer 4, JSON and ids nearer 3), and one token per
  non-ASCII character (CJK and emoji are one or more tokens each). The runtime's own `policy.estimate_tokens` uses 4.0; this one
  is deliberately a little conservative so a budget enforced with it is not exceeded by the provider's count.
* images: the DEFAULT profile is 1150 input tokens for a 1280 x 720 screenshot. That figure comes from our own bake-off usage fields
  (`evals/modelbench/cache/results.jsonl`, 7 Nov 2026): one image plus a short prompt was 1238 to 1373 input tokens on
  gpt-5.4-mini and 1311 to 1517 on the Gemini flash models, and the short prompts are 150 to 250 tokens. Other sizes scale with
  pixel area (a floor of 85, a cap of 1600).
  The `openai_cu` profile is calibrated on ONE live run of the shipped tier-3 loop (`evals/agentic/ITERATIONS.md`, diag_smoke_2:
  74,548 input tokens over 27 steps, a 1152 x 720 frame sent at `detail: original`, 2.4k to 2.7k characters of text, 191 tokens of
  instructions), which leaves about 1860 tokens per frame: the default profile under-counts that path by about 27 percent. It is a
  calibration from n = 1, not a validation; the models meter records `ctx_estimate_error` for every later call.
"""
from __future__ import annotations

import math

CHARS_PER_TOKEN = 3.6
IMAGE_TOKENS_1280x720 = 1150
IMAGE_MIN_TOKENS = 85
IMAGE_MAX_TOKENS = 1600
_REF_PIXELS = 1280 * 720
# profile -> (reference pixels, tokens at that size, cap)
IMAGE_PROFILES: dict[str, tuple[int, int, int]] = {
    "default": (1280 * 720, 1150, 1600),
    "openai_cu": (1152 * 720, 1860, 2400),
}


def estimate_tokens(text: str) -> int:
    """Estimated tokens of `text` (0 for empty)."""
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other = len(text) - ascii_chars
    return int(math.ceil(ascii_chars / CHARS_PER_TOKEN)) + other


def estimate_image_tokens(width: int, height: int, profile: str = "default") -> int:
    """Estimated input tokens for one image of this pixel size (scaled by area, floor 85, a cap per profile)."""
    if width <= 0 or height <= 0:
        return 0
    ref_px, ref_tokens, cap = IMAGE_PROFILES[profile]
    t = ref_tokens * (width * height) / ref_px
    return int(max(IMAGE_MIN_TOKENS, min(cap, round(t))))


def estimate_error(estimated: int, actual: int) -> float | None:
    """Signed relative error of an estimate against a provider's count: (estimate - actual) / actual. None when actual is 0."""
    if not actual:
        return None
    return (estimated - actual) / actual
