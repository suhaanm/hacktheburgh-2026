"""Property tests for the generalisation rules (PRV-3): exhaustive sweeps on the integer grids plus seeded random sampling
on the continuous ones (no hypothesis dependency)."""
from __future__ import annotations

import random
from datetime import datetime, time

import pytest
from pydantic import ValidationError

from understudy_engine.privacy import bucket as B
from understudy_engine.privacy.bucket import (
    Attendees, Count, DurationMin, Hours, Numbers, Ratio, TimeOfDay, register_feature,
)
from understudy_engine.privacy.payload import SafePayload

RNG = random.Random(20261107)


# --------------------------------------------------------------------------- counts
def test_counts_under_five_become_lt5_and_others_are_unchanged_exhaustively():
    for n in range(0, 20001):
        out = B.bucket_count(n)
        assert (out == "lt5") if n < 5 else (out == n)
        assert B.bucket_count(out) == out            # idempotent


def test_count_accepts_integral_floats_but_rejects_fractions_negatives_bools_and_text():
    assert B.bucket_count(7.0) == 7
    for bad in (3.5, -1, True, False, "7", None, float("nan")):
        with pytest.raises(ValueError):
            B.bucket_count(bad)


def test_attendee_buckets_partition_the_counts_and_are_monotone():
    order = {"lt5": 0, "5to9": 1, "10plus": 2}
    prev = 0
    for n in range(0, 500):
        out = B.bucket_attendees(n)
        assert out == ("lt5" if n < 5 else "5to9" if n <= 9 else "10plus")
        assert order[out] >= prev
        prev = order[out]
        assert B.bucket_attendees(out) == out


# --------------------------------------------------------------------------- times of day (15 minutes)
def test_time_rounds_to_15_minutes_within_half_a_step_monotone_and_idempotent():
    prev = -1
    for tenth in range(0, 14401):               # every 0.1 minute from 0 to 1440
        m = tenth / 10
        out = B.round_time_minutes(m)
        assert out % 15 == 0 and 0 <= out <= 1440
        assert abs(out - m) <= 7.5 + 1e-9
        assert out >= prev
        prev = out
        assert B.round_time_minutes(out) == out
    assert B.round_time_minutes(7.5) == 15        # half goes up
    assert B.round_time_minutes(7.4) == 0


def test_time_accepts_datetimes_and_times_and_rejects_out_of_range():
    assert B.round_time_minutes(datetime(2026, 11, 2, 9, 7, 0)) == 540
    assert B.round_time_minutes(datetime(2026, 11, 2, 9, 7, 59)) == 555      # seconds count: 9:07:59 is nearer 9:15
    assert B.round_time_minutes(time(23, 58)) == 1440
    for bad in (-1, 1441, float("inf"), True, "09:00"):
        with pytest.raises(ValueError):
            B.round_time_minutes(bad)


# --------------------------------------------------------------------------- durations (5 minutes)
def test_duration_rounds_to_5_minutes_within_half_a_step_monotone_and_idempotent():
    prev = -1
    for tenth in range(0, 20001):
        m = tenth / 10
        out = B.round_duration_minutes(m)
        assert out % 5 == 0 and out >= 0
        assert abs(out - m) <= 2.5 + 1e-9
        assert out >= prev
        prev = out
        assert B.round_duration_minutes(out) == out
    assert B.round_duration_minutes(2.5) == 5
    assert B.round_duration_seconds(150) == 5      # 2.5 minutes
    assert B.round_duration_seconds(149) == 0


def test_negative_duration_is_rejected():
    with pytest.raises(ValueError):
        B.round_duration_minutes(-0.1)


def test_hours_are_a_multiple_of_five_minutes():
    for _ in range(2000):
        h = RNG.uniform(0, 80)
        out = B.bucket_hours(h)
        minutes = out * 60
        assert abs(minutes - 5 * round(minutes / 5)) < 0.31      # two-decimal hours is within 0.3 min of a 5-minute step
        assert abs(out - h) <= 2.5 / 60 + 0.006
        assert B.bucket_hours(out) == out


# --------------------------------------------------------------------------- ratios (10% steps)
def test_ratio_rounds_to_ten_percent_steps_monotone_idempotent_and_in_range():
    prev = -1.0
    for k in range(0, 100001):
        x = k / 100000
        out = B.bucket_ratio(x)
        assert 0.0 <= out <= 1.0
        assert abs(out * 10 - round(out * 10)) < 1e-9
        assert abs(out - x) <= 0.05 + 1e-9
        assert out >= prev
        prev = out
        assert B.bucket_ratio(out) == out
    assert B.bucket_ratio(0.25) == 0.3 and B.bucket_ratio(0.249999) == 0.2
    assert B.bucket_ratio(0.3) == 0.3 and str(B.bucket_ratio(0.1 + 0.2)) == "0.3"


def test_ratio_tolerates_float_dust_but_rejects_real_out_of_range():
    assert B.bucket_ratio(1.0000000001) == 1.0
    assert B.bucket_ratio(-1e-12) == 0.0
    for bad in (1.2, -0.2, float("nan"), True, "0.5"):
        with pytest.raises(ValueError):
            B.bucket_ratio(bad)


# --------------------------------------------------------------------------- the annotated types inside a SafePayload
class Buckets(SafePayload):
    count: Count
    people: Attendees
    at: TimeOfDay
    length: DurationMin
    hours: Hours
    share: Ratio
    lengths: list[DurationMin] = []


def test_the_types_apply_the_rules_when_the_payload_is_built():
    p = Buckets(count=3, people=12, at=datetime(2026, 11, 2, 9, 7), length=47, hours=1.83, share=0.34, lengths=[7, 8, 11])
    w = p.to_wire()
    assert w["count"] == "lt5" and w["people"] == "10plus" and w["at"] == 540 and w["length"] == 45
    assert w["hours"] == 1.83 and w["share"] == 0.3 and w["lengths"] == [5, 10, 10]
    assert Buckets.model_validate_json(p.model_dump_json()).to_wire() == w         # idempotent through the wire


def test_a_payload_with_raw_unbucketed_numbers_cannot_be_built_from_a_string_or_a_bool():
    with pytest.raises(ValidationError):
        Buckets(count="3", people=3, at=0, length=0, hours=0.0, share=0.0)
    with pytest.raises(ValidationError):
        Buckets(count=True, people=3, at=0, length=0, hours=0.0, share=0.0)


def test_random_payloads_are_always_on_the_grids():
    for _ in range(500):
        p = Buckets(count=RNG.randint(0, 40), people=RNG.randint(0, 40), at=RNG.uniform(0, 1440), length=RNG.uniform(0, 600),
                    hours=RNG.uniform(0, 50), share=RNG.random(), lengths=[RNG.uniform(0, 100) for _ in range(5)])
        w = p.to_wire()
        assert w["count"] == "lt5" or (isinstance(w["count"], int) and w["count"] >= 5)
        assert w["at"] % 15 == 0 and w["length"] % 5 == 0 and all(x % 5 == 0 for x in w["lengths"])
        assert abs(w["share"] * 10 - round(w["share"] * 10)) < 1e-9


# --------------------------------------------------------------------------- feature maps
def test_numbers_generalise_each_value_by_its_feature_and_reject_unknown_features():
    register_feature("t_meet_h", "hours")
    register_feature("t_blocks", "count")
    register_feature("t_longest", "duration_min")
    register_feature("t_frag", "ratio")

    class M(SafePayload):
        nums: Numbers

    w = M(nums={"t_meet_h": 14.1, "t_blocks": 2, "t_longest": 47, "t_frag": 0.36}).to_wire()["nums"]
    assert w == {"t_meet_h": 14.08, "t_blocks": "lt5", "t_longest": 45, "t_frag": 0.4}
    with pytest.raises(ValidationError):
        M(nums={"Ada Lovelace's review": 3})
    with pytest.raises(ValidationError):
        M(nums={"t_blocks": True})
    with pytest.raises(ValueError):
        register_feature("t_blocks", "ratio")
    with pytest.raises(ValueError):
        register_feature("t_x", "no_such_kind")


# --------------------------------------------------------------------------- numpy and pandas scalars from the analytics code
def test_numpy_scalars_are_accepted_and_come_out_as_plain_python_numbers():
    np = pytest.importorskip("numpy")
    assert B.bucket_count(np.int64(3)) == "lt5" and B.bucket_count(np.int64(12)) == 12 and type(B.bucket_count(np.int64(12))) is int
    assert B.bucket_count(np.float64(7.0)) == 7
    assert B.round_time_minutes(np.float64(547.9)) == 555 and type(B.round_time_minutes(np.float64(547.9))) is int
    assert B.round_duration_minutes(np.int32(47)) == 45 and B.bucket_ratio(np.float32(0.34)) == 0.3
    assert type(B.bucket_ratio(np.float64(0.34))) is float
    for bad in (np.bool_(True), np.float64("nan")):
        with pytest.raises(ValueError):
            B.bucket_count(bad)

    register_feature("t_np_raw", "raw")

    class M(SafePayload):
        nums: Numbers
        c: Count
        r: Ratio

    w = M(nums={"t_np_raw": np.int64(9)}, c=np.int64(2), r=np.float64(0.51)).to_wire()
    assert w == {"nums": {"t_np_raw": 9}, "c": "lt5", "r": 0.5}



def test_the_calendar_layer_uses_these_exact_functions():
    from understudy_engine.calendar import bucket as cb

    assert cb.FROM_PRIVACY is True
    assert cb.bucket_count is B.bucket_count and cb.round_minutes is B.round_duration_minutes
    assert cb.round_ratio is B.bucket_ratio and cb.round_hours is B.bucket_hours and cb.round_time_of_day is B.round_time_minutes
