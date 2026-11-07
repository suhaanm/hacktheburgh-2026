"""Spoken forms of a number: what the templates say, and the FIXED ROUNDING TABLE the provenance check accepts.

The rule (REQ-6): the model never computes a number. A figure in a reply is accepted only if it is a field of the packet
the sentence cites, written in one of the forms below. Nothing here is fuzzy: every accepted form is a member of a finite
set computed from the packet value, so "is 62 seconds a fair way to say 65.6?" has the same answer every time (no).

Units. A packet value has one of these units: ``s`` seconds, ``min`` minutes, ``h`` hours, ``frac`` a share or probability
(spoken as a percentage), ``count`` a whole number, ``gbp`` pounds, ``per_hour`` a rate, ``score`` a small unitless score
(log loss, calibration error, a coefficient of variation).

How a mention is judged, with F the packet value in the mention's own unit and D what the sentence says:

* no qualifier ("66 seconds", "62%", "1.1 minutes"): D must equal F rounded to the number of decimals written, half up,
  with the written unit as the step: ``|D - F| <= half of the last written digit`` (65.6 s may be 65.6 or 66 seconds, or
  1.1 minutes, or "a minute" because a bare "a minute" is written to the nearest minute; it may not be 65 or 62).
* "about", "around", "roughly", "approximately", "close to": D must be in the APPROX TABLE of F.
* "over", "more than", "just over", "at least", "above": D must be in the FLOOR TABLE of F (D <= F).
* "under", "less than", "just under", "almost", "nearly", "below": D must be in the CEIL TABLE of F (D >= F).

The tables (all computed on the magnitude; the sign of a difference is checked separately, from the words around it):

* APPROX(F) = {F to one decimal, F rounded, floor(F), ceil(F)} plus F rounded to the nearest 5 and 10 when F >= 10 and 20,
  plus, for seconds, the nearest 30 and 60 when F >= 45, and, for pounds, the nearest 50 and 100 when F >= 100.
* FLOOR(F)  = {floor(F), F rounded down to a multiple of 5 (F >= 5), 10 (F >= 10), and for seconds 30 (F >= 30), 60 (F >= 60)}.
* CEIL(F)   = the same with ceiling.

So 65.6 seconds may be "about 65", "about 66", "about 70", "about a minute", "just over a minute" (floor 60), "over 65",
"under 70", "nearly a minute and a half" (ceil 90), and may not be "about 62", "about 68", "over 66" or "about two minutes".
"""
from __future__ import annotations

import math

EPS = 1e-9
UNIT_SCALE_S = {"s": 1.0, "min": 60.0, "h": 3600.0}
TIME_UNITS = ("s", "min", "h")


def half_up(x: float) -> int:
    """Round half up (65.5 -> 66, and so is -65.5 -> -65): stable and monotone, the same rule the privacy layer uses."""
    return int(math.floor(x + 0.5 + EPS))


def _nearest(x: float, step: float) -> float:
    return half_up(x / step) * step


def _floor_to(x: float, step: float) -> float:
    return math.floor(x / step + EPS) * step


def _ceil_to(x: float, step: float) -> float:
    return math.ceil(x / step - EPS) * step


def approx_table(f: float, kind: str) -> set[float]:
    """The numbers a sentence may say after "about" for magnitude ``f`` (``kind`` is ``s``, ``gbp`` or anything else)."""
    f = abs(f)
    out = {round(f, 1), float(half_up(f)), float(math.floor(f + EPS)), float(math.ceil(f - EPS))}
    if f >= 10:
        out.add(_nearest(f, 5))
    if f >= 20:
        out.add(_nearest(f, 10))
    if kind == "s" and f >= 45:
        out.add(_nearest(f, 30))
        out.add(_nearest(f, 60))
    if kind == "s" and f >= 3000:
        out.add(_nearest(f, 1800))
        out.add(_nearest(f, 3600))
    if kind == "gbp" and f >= 100:
        out.add(_nearest(f, 50))
        out.add(_nearest(f, 100))
    return out


def floor_table(f: float, kind: str) -> set[float]:
    f = abs(f)
    out = {float(math.floor(f + EPS))}
    if f >= 5:
        out.add(_floor_to(f, 5))
    if f >= 10:
        out.add(_floor_to(f, 10))
    if kind == "s" and f >= 30:
        out.add(_floor_to(f, 30))
    if kind == "s" and f >= 60:
        out.add(_floor_to(f, 60))
    if kind == "s" and f >= 3600:
        out.add(_floor_to(f, 3600))
    if kind == "gbp" and f >= 100:
        out.add(_floor_to(f, 50))
        out.add(_floor_to(f, 100))
    return out


def ceil_table(f: float, kind: str) -> set[float]:
    f = abs(f)
    out = {float(math.ceil(f - EPS))}
    if f >= 5:
        out.add(_ceil_to(f, 5))
    if f >= 10:
        out.add(_ceil_to(f, 10))
    if kind == "s" and f >= 30:
        out.add(_ceil_to(f, 30))
    if kind == "s" and f >= 60:
        out.add(_ceil_to(f, 60))
    if kind == "s" and f >= 3600:
        out.add(_ceil_to(f, 3600))
    if kind == "gbp" and f >= 100:
        out.add(_ceil_to(f, 50))
        out.add(_ceil_to(f, 100))
    return out


def _in(d: float, table: set[float]) -> bool:
    return any(abs(d - t) <= 1e-6 for t in table)


def accepts(d: float, qualifier: str, decimals: int, step: float, f: float, kind: str) -> bool:
    """Is the sentence's value ``d`` (a magnitude, in the fact's own base: seconds, percent points, pounds, plain) an accepted
    way to say the fact's magnitude ``f``?

    ``qualifier``: ``none`` | ``approx`` | ``over`` | ``under``. ``decimals``: decimals written (0 for "66"). ``step``: how many
    base units one written unit is (1 for seconds written in seconds, 60 for minutes, 1 for percent points).
    ``kind``: ``s`` | ``gbp`` | ``other`` (selects the extra rows of the tables)."""
    f = abs(f)
    d = abs(d)
    exact = abs(d - f) <= 0.5 * (10 ** -decimals) * step + EPS
    if qualifier == "none":
        return exact
    if qualifier == "approx":
        return exact or _in(d, approx_table(f, kind))
    if qualifier == "over":
        return (d <= f + EPS) and (_in(d, floor_table(f, kind)) or exact)
    if qualifier == "under":
        return (d >= f - EPS) and (_in(d, ceil_table(f, kind)) or exact)
    raise ValueError(qualifier)


def near(d: float, f: float, floor: float = 0.5) -> bool:
    """A mention that is 'close' to a fact without being accepted: reported as a rounding error, not an invented number.
    ``floor`` is the smallest difference that still counts as close, in the same base as ``d`` and ``f``."""
    f = abs(f)
    d = abs(d)
    return abs(d - f) <= max(0.25 * f, floor)


# ------------------------------------------------------------------------------------------------ rendering (templates)
def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def render_seconds(v: float) -> str:
    """Magnitude of a duration in seconds, as a template says it. Every output is accepted by ``accepts`` for ``v``."""
    v = abs(v)
    if v < 10:
        return f"{v:.1f} seconds"
    r = half_up(v)
    if r < 100:
        return f"{r} seconds"
    m, s = divmod(r, 60)
    if s == 0:
        return f"{m} {_plural(m, 'minute', 'minutes')}"
    return f"{m} {_plural(m, 'minute', 'minutes')} {s} {_plural(s, 'second', 'seconds')}"


def render_percent(frac: float) -> str:
    return f"{half_up(abs(frac) * 100)}%"


def render_count(n: float) -> str:
    return str(int(round(n)))


def render_gbp(v: float) -> str:
    return f"£{half_up(abs(v)):,}"


def render_score(v: float) -> str:
    return f"{v:.3f}" if abs(v) < 0.1 else f"{v:.2f}"


def render_per_hour(v: float) -> str:
    return f"{v:.2f} per hour"


def render(value: float, unit: str) -> str:
    if unit == "s":
        return render_seconds(value)
    if unit == "min":
        return render_seconds(value * 60)
    if unit == "h":
        return f"{abs(value):.1f} hours"
    if unit == "frac":
        return render_percent(value)
    if unit == "count":
        return render_count(value)
    if unit == "weeks":
        n = int(round(value))
        return f"{n} week" if n == 1 else f"{n} weeks"
    if unit == "gbp":
        return render_gbp(value)
    if unit == "per_hour":
        return render_per_hour(value)
    if unit == "score":
        return render_score(value)
    raise ValueError(unit)


def _signed(text: str, v: float) -> str:
    return ("-" + text) if (v < 0 and not text.startswith("0")) else text


def render_range(lo: float, hi: float, unit: str) -> str:
    """An interval as a template says it: both ends signed, same unit, lo then hi ("between 55 and 72 seconds",
    "between -3.1 seconds and 18 seconds"). The provenance check reads it back as one interval of one item."""
    if unit == "s":
        a, b = _signed(render_seconds(lo), lo), _signed(render_seconds(hi), hi)
        if a.endswith(" seconds") and b.endswith(" seconds") and "minute" not in a and "minute" not in b:
            return f"between {a[:-8]} and {b}"
        return f"between {a} and {b}"
    if unit == "frac":
        return f"between {half_up(abs(lo) * 100)} and {render_percent(hi)}"
    return f"between {_signed(render(lo, unit), lo)} and {_signed(render(hi, unit), hi)}"
