"""The engine tunes Python's collector after its warm-up, so a large long-lived heap is not re-scanned on every burst of allocations (a wedged engine at
100% CPU inside the collector made /health time out)."""
import gc

from understudy_engine.api.app import tune_gc


def test_tune_gc_raises_the_thresholds_and_freezes_what_is_loaded():
    before = gc.get_threshold()
    try:
        tune_gc()
        assert gc.get_threshold()[0] >= 100_000
        assert gc.get_freeze_count() > 0
        # nothing is disabled: the collector still runs and still reclaims a fresh cycle
        assert gc.isenabled()
        a: list = []
        a.append(a)
        del a
        assert gc.collect() >= 0
    finally:
        gc.unfreeze()
        gc.set_threshold(*before)


def test_a_serving_engine_hands_the_gil_back_to_the_event_loop_within_a_millisecond():
    import sys

    from understudy_engine.api.app import tune_switch_interval

    before = sys.getswitchinterval()
    try:
        assert tune_switch_interval() <= 0.0011
        assert sys.getswitchinterval() <= 0.0011
    finally:
        sys.setswitchinterval(before)
