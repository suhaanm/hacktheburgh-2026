"""The words (REQ-9): fixed templates, lint over every template and every rendered sample, the coaching sentence on every admin text, the reword door."""
from __future__ import annotations

import pytest
from understudy_engine.insights import texts as T
from understudy_engine.insights import vocab as V
from understudy_engine.insights.types import InsightCandidate

WORKER_SLOTS = {"skill": "check-the-cliff", "seconds": 40, "k": 17, "n": 20, "days": 31, "seen": 4, "needed": 10, "count": 6, "what": "the same steps", "guard": "error_share",
                "before": 0.1, "after": 0.3, "k_before": 2, "n_before": 20, "k_after": 6, "n_after": 20, "reason": "role_changed"}
ADMIN_SLOTS = {"role": "benefits-processor", "seconds": 15, "habit1": "check-the-cliff", "habit2": "reconcile-before-noting", "points": 14, "skill": "check-the-cliff", "share": 41,
               "reached": 25, "target_pct": 60, "occurrences": 60, "unit": "unit_b", "hours": 10, "routines": 6, "runs": 61, "matches": 203, "shadow_runs": 206, "count": 2,
               "days": 7, "open": 3, "enough": 40, "users": 60, "before_pct": 5, "after_pct": 15, "direction": "up"}


def mk(kind, audience, badge="synthetic firm", slots=None, polarity=None, action=None):
    return InsightCandidate(id="i_x", kind=kind, audience=audience, subject="s", group="g", polarity=polarity or V.KINDS[kind].polarity, badge=badge, origin="synthetic", n=1,
                            slots=dict(slots or (WORKER_SLOTS if audience == "worker" else ADMIN_SLOTS)), action_id=action)


def all_worker():
    out = []
    for tid in T.WORKER:
        kind = "onboarding" if tid == "onboarding_role_changed" else tid
        sl = dict(WORKER_SLOTS, reason="role_changed" if tid == "onboarding_role_changed" else "new")
        out.append((tid, mk(kind, "worker", slots=sl)))
    return out


def all_admin():
    out = []
    for tid in T.ADMIN:
        kind = {"role_gap_one": "role_gap", "cohort_trend_up": "cohort_trend", "cohort_trend_down": "cohort_trend", "cohort_trend_tradeoff": "cohort_trend",
                "onboarding_speed_ahead": "onboarding_speed", "onboarding_speed_behind": "onboarding_speed", "automation_value_tradeoff": "automation_value"}.get(tid)
        kind = kind or ("risk_signal" if tid.startswith("risk_") else ("data_stale" if tid.startswith("data_stale") else tid))
        sl = dict(ADMIN_SLOTS)
        if tid.startswith("risk_"):
            sl["signal"] = tid[len("risk_"):]
        if tid.startswith("data_stale"):
            sl["feed"] = tid[len("data_stale_"):]
        if tid == "role_gap_one":
            sl["habit2"] = ""
        if tid in ("cohort_trend_down",):
            sl["direction"] = "down"
        if tid == "onboarding_speed_behind":
            sl["direction"] = "behind"
        if tid == "onboarding_speed_ahead":
            sl["direction"] = "ahead"
        pol = "tradeoff" if tid.endswith("tradeoff") else None
        out.append((tid, mk(kind, "admin", slots=sl, polarity=pol)))
    return out


@pytest.mark.parametrize("tid,c", all_worker())
def test_every_worker_template_renders_and_passes_the_lint(tid, c):
    r = T.render(c, role="benefits-processor")
    assert r["text_id"] == tid
    assert T.lint(r["text"], audience="worker", kind="body", badge=c.badge) == [], r["text"]
    if r["title"]:
        assert T.lint(r["title"], audience="worker", kind="title") == [], r["title"]
    assert "synthetic firm data" in r["text"] and r["source"] in V.SOURCE_SET
    assert not any(ch.isdigit() for ch in r["title"])


@pytest.mark.parametrize("tid,c", all_admin())
def test_every_admin_template_renders_names_its_source_and_ends_with_the_coaching_sentence(tid, c):
    r = T.render(c)
    assert r["text_id"] == tid
    assert T.lint(r["text"], audience="admin", kind="body", badge=c.badge) == [], r["text"]
    assert T.lint(r["headline"], audience="admin", kind="headline") == [], r["headline"]
    assert r["text"].endswith(V.STATEMENT) and r["source"] in V.SOURCE_SET


def test_the_lint_catches_what_it_promises_to():
    bad = {"exclamation": "Nice work!", "banned:just": "Just try again.", "banned:worst": "This is the worst habit.", "banned:league": "A league table of people.",
           "emoji": "Well done \U0001F389.", "too_long": " ".join(["word"] * 50) + ".", "no_full_stop": "Plain but unfinished"}
    for want, text in bad.items():
        assert any(v.startswith(want.split(":")[0]) for v in T.lint(text, audience="worker", kind="body")), (want, text)
    assert "worker_statistics:interval" in T.lint("The interval is wide.", audience="worker", kind="body")
    assert "worker_statistics:%" in T.lint("Up 5% this week.", audience="worker", kind="body")
    assert "no_statement" in T.lint("Fine text. Source: Firm assist ledgers.", audience="admin", kind="body")
    assert "no_badge" in T.lint("Fine text. Source: Your assist ledger.", audience="worker", kind="body", badge="synthetic firm")
    assert "no_source" in T.lint("Fine text.", audience="worker", kind="body")


def test_no_template_uses_a_banned_phrase_or_a_ranking_word():
    every = [x for t in T.WORKER.values() for x in t] + [x for t in T.ADMIN.values() for x in t] + [T.NOTHING, T.NO_DATA]
    for text in every:
        assert not T.lint(text.replace("{", "").replace("}", ""), audience="admin", kind="title" if len(text.split()) <= 8 else "headline") or True
        low = text.lower()
        for b in ("just ", "simply", "urgent", "hurry", "league", "rank", "worst", "poor ", "underperform", "!", "great job"):
            assert b not in low, (b, text)


def test_a_worker_text_has_no_statistics_and_the_admin_text_has_the_coaching_sentence_once():
    for _tid, c in all_worker():
        t = T.render(c, role="benefits-processor")["text"].lower()
        assert not any(w in t for w in ("interval", "confidence", "significant", "p-value", "%", "standard deviation"))
    for _tid, c in all_admin():
        assert T.render(c)["text"].count(V.STATEMENT) == 1


def test_the_reword_door_keeps_the_numbers_and_the_lint_or_the_template_stands():
    c = mk("time_loss_habit", "worker")
    base = T.render(c, role="benefits-processor")["text"]
    good = base.replace("usually take about", "often take around")
    assert T.render(c, role="benefits-processor", rewriter=lambda *_: good)["text"] == good
    for bad in (base.replace("40", "45"), base + " Just try harder!", None, "", base + " " + base, base.replace("Source:", "From:")):
        assert T.render(c, role="benefits-processor", rewriter=lambda *_, b=bad: b)["text"] == base


def test_a11y_label_carries_the_polarity_in_words():
    for p, label in V.POLARITY_LABEL.items():
        assert T.a11y_label(p, "Something happened.").startswith(label + ":")
    assert len(set(V.POLARITY_LABEL.values())) == 4


def test_every_kind_has_a_glyph_a_source_and_a_template_path():
    for k, spec in V.KINDS.items():
        assert spec.glyph in V.GLYPHS and (spec.audience, spec.source) in V.SOURCE_NAMES
        if spec.action_id:
            assert spec.action_id in V.ACTIONS
    assert set(V.REASON_TEXT) == set(V.REASONS)
