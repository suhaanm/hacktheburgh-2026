"""The fixed rounding table: every accepted spoken form of 65.6 seconds, and the ones that are refused."""
from __future__ import annotations

import pytest

from understudy_engine.evidence import numbers as N
from understudy_engine.evidence.packet import Fact
from understudy_engine.evidence.provenance import _fact_accepts, extract_mentions

F_S = Fact("habit.x.seconds", 65.6, "s")


def _ok(text: str, fact: Fact = F_S) -> bool:
    ms = [m for m in extract_mentions(text) if m.kind == "num"]
    return len(ms) == 1 and _fact_accepts(ms[0], fact)


@pytest.mark.parametrize("text", [
    "65.6 seconds", "66 seconds", "1.1 minutes", "a minute", "1 minute 6 seconds", "1:06", "about 65 seconds", "about 66 seconds",
    "around 70 seconds", "roughly 65.6 seconds", "about a minute", "just over a minute", "over 65 seconds", "over 60 seconds",
    "under 70 seconds", "just under 70 seconds", "nearly a minute and a half", "about 1 minute", "approximately 65 seconds",
])
def test_accepted_forms_of_65_6_seconds(text):
    assert _ok(text), text


@pytest.mark.parametrize("text", [
    "65 seconds", "62 seconds", "about 62 seconds", "about 68 seconds", "over 66 seconds", "under 65 seconds", "about two minutes",
    "2 minutes", "1 minute 5 seconds", "1.2 minutes", "6.56 seconds", "656 seconds", "a minute and a half", "an hour", "half a minute",
    "66.0 seconds"[:0] + "70 seconds",
])
def test_refused_forms_of_65_6_seconds(text):
    assert not _ok(text), text


def test_percent_counts_pounds_rates_and_scores():
    p = Fact("hazard.p_now", 0.103, "frac")
    assert _ok("10%", p) and _ok("10.3%", p) and _ok("10 percent", p) and _ok("about 10%", p) and _ok("0.103", p) and _ok("0.10", p)
    assert not _ok("11%", p) and not _ok("about 15%", p) and not _ok("0.2", p)
    c = Fact("meta.n", 24.0, "count")
    assert _ok("24 people", c) and _ok("24", c) and _ok("about 25", c) and not _ok("23", c) and not _ok("24.5", c)
    g = Fact("consequence.RECONCILE.mean_gbp", 291.9, "gbp")
    assert _ok("£292", g) and _ok("£291.9", g) and _ok("about £300", g) and _ok("about £290", g) and not _ok("£300", g) and not _ok("about £250", g)
    r = Fact("hazard.false_alarms_per_hour", 1.21, "per_hour")
    assert _ok("1.21 per hour", r) and _ok("1.2 per hour", r) and _ok("about 1.2 per hour", r) and not _ok("1.3 per hour", r)
    s = Fact("hazard.model_log_loss", 0.436, "score")
    assert _ok("0.436", s) and _ok("0.44", s) and not _ok("0.45", s)


def test_every_template_rendering_is_accepted_for_many_values():
    import random

    rng = random.Random(1)
    for _ in range(400):
        v = round(rng.uniform(0.1, 4000), 1)
        assert _ok(N.render(v, "s"), Fact("a.b", v, "s")), (v, N.render(v, "s"))
        p = round(rng.uniform(0, 1), 3)
        assert _ok(N.render(p, "frac"), Fact("a.b", p, "frac")), (p, N.render(p, "frac"))
        g = round(rng.uniform(1, 3000), 1)
        assert _ok(N.render(g, "gbp"), Fact("a.b", g, "gbp")), (g, N.render(g, "gbp"))


def test_every_varied_style_form_is_in_the_table_for_many_values():
    import random

    from understudy_engine.evidence.fakes import VariedStyle

    rng = random.Random(2)
    style = VariedStyle(rng)
    for _ in range(600):
        v = round(rng.uniform(0.5, 3000), 1)
        text = style.render(v, "s")
        assert _ok(text, Fact("a.b", v, "s")), (v, text)
        p = round(rng.uniform(0, 1), 3)
        t2 = style.render(p, "frac")
        assert _ok(t2, Fact("a.b", p, "frac")), (p, t2)
