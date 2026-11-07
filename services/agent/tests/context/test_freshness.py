"""The shared freshness table: the limits, the three states, and agreement with the keys Cue already reads."""
from __future__ import annotations

import pytest

from understudy_agent.context import MAX_AGE_S, Status, age_s, is_fresh, status_of


def test_the_three_states():
    assert status_of("glance", 100.0, 150.0) is Status.FRESH
    assert status_of("glance", 100.0, 161.0) is Status.STALE
    assert status_of("glance", None, 161.0) is Status.MISSING
    assert status_of("progress", 0.0, 10**9) is Status.FRESH           # no limit: it only has to exist
    assert status_of("progress", None, 10.0) is Status.MISSING


def test_a_reading_from_the_future_is_age_zero_never_negative():
    assert age_s(200.0, 100.0) == 0.0 and is_fresh("p_stuck", 200.0, 100.0)


def test_an_unknown_kind_is_an_error_not_no_limit():
    with pytest.raises(KeyError):
        status_of("gance", 1.0, 2.0)


def test_the_limits_requested_by_the_other_tracks_are_in_the_table():
    for kind, limit in {"p_stuck": 6.0, "snapshot": 60.0, "grounding": 20.0, "glance": 60.0, "input_rhythm": 10.0, "progress": None,
                        "worker_state": 10.0, "meeting_state": 120.0}.items():
        assert MAX_AGE_S[kind] == limit


def test_it_agrees_with_the_cue_engines_own_table_for_every_key_cue_reads():
    from understudy_engine.cue import freshness as cue

    for k, v in cue.MAX_AGE_S.items():
        assert MAX_AGE_S[k] == v, k
