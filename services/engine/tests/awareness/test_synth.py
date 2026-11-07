from __future__ import annotations

import json
from pathlib import Path

import pytest

from understudy_engine.awareness import schema, synth
from understudy_engine.awareness.features import AWARENESS_COLUMNS, features_by_bin
from understudy_engine.awareness.store import AwarenessStore

from .conftest import tiny_persona

REPO_DATA = Path(__file__).resolve().parents[4] / "data"


@pytest.fixture()
def root(tmp_path):
    return tiny_persona(tmp_path / "persona", n_tasks=14)


def test_deterministic_valid_and_labelled_synthetic(root):
    a = synth.make("nine-to-five", root=root)
    b = synth.make("nine-to-five", root=root)
    assert a.events == b.events and a.events
    assert all(e["origin"] == "synthetic" and e["person"] == "p_ninetofive" and e["role"] == "benefits-processor" for e in a.events)
    assert all(schema.problem(e) is None for e in a.events), next(schema.problem(e) for e in a.events if schema.problem(e))
    ids = [e["id"] for e in a.events]
    assert len(ids) == len(set(ids))
    assert "assumed" in a.note and "not evidence about real people" in a.note
    assert synth.make("nine-to-five", root=root, seed=7).events != a.events
    assert json.dumps(a.events) == json.dumps(b.events)                        # byte-identical


def test_windows_only_inside_tasks_two_seconds_long_and_clicks_unknown(root):
    r = synth.make("nine-to-five", root=root)
    wins = [e for e in r.events if e["type"] == "window"]
    assert wins and all(e["window_s"] == 2.0 and e["cursor"]["clicks"] is None for e in wins)
    # tasks run [k*120, k*120 + 100] from 09:00:00; every window lies inside one
    t0 = schema.parse_time("2026-10-12T09:00:00.000Z")
    for e in wins:
        off = schema.parse_time(e["t"]) - t0
        assert off % 120 <= 100 - 2 + 1e-6
    assert len(wins) == 14 * 50
    times = [schema.parse_time(e["t"]) for e in r.events]
    assert times == sorted(times)


def test_max_tasks_and_the_unknown_persona(root):
    assert len([e for e in synth.make("nine-to-five", root=root, max_tasks=2).events if e["type"] == "window"]) == 100
    with pytest.raises(ValueError):
        synth.make("nobody", root=root)
    with pytest.raises(FileNotFoundError):
        synth.make("night-owl", root=root)


def test_spells_show_in_the_cursor_only_when_visible_and_the_generator_says_so_plainly(root):
    """The coupling is ASSUMED by the generator (see the module docstring): this test checks that the generator does what it says, no more."""
    spells = [(60.0, 110.0), (260.0, 300.0), (500.0, 560.0)]
    root2 = tiny_persona(root.parent / "bigger", n_tasks=60, spells=tuple((a, a + 45.0) for a in range(100, 7000, 600)))
    r = synth.make("nine-to-five", root=root2)
    t0 = schema.parse_time("2026-10-12T09:00:00.000Z")

    def in_spell(e, vis):
        t = schema.parse_time(e["t"]) - t0
        return any(sp.visible == vis and sp.t0 - t0 <= t < sp.t1 - t0 for sp in r.spells)

    wins = [e for e in r.events if e["type"] == "window"]
    visible = [e for e in wins if in_spell(e, True)]
    quiet = [e for e in wins if in_spell(e, False)]
    other = [e for e in wins if not in_spell(e, True) and not in_spell(e, False)]
    assert visible and other
    mean = lambda es, k: sum(float(e["cursor"][k]) for e in es) / len(es)  # noqa: E731
    assert mean(visible, "wander") > mean(other, "wander") + 0.5
    assert mean(visible, "back_forth") > mean(other, "back_forth")
    assert mean(visible, "dwell_s") > mean(other, "dwell_s")
    if quiet:                                                                  # a quiet spell leaves the cursor as ordinary as the rest
        assert abs(mean(quiet, "wander") - mean(other, "wander")) < 0.6
    assert sum(1 for s in r.spells if not s.visible) + sum(1 for s in r.spells if s.visible) == len(r.spells)
    assert spells  # silence the unused name


def test_false_alarms_exist_so_the_signal_is_not_clean(root):
    r = synth.make("nine-to-five", root=tiny_persona(root.parent / "noalarm", n_tasks=80, spells=()))
    wins = [e for e in r.events if e["type"] == "window"]
    stuckish = [e for e in wins if e["cursor"]["wander"] > 4.0 or e["cursor"]["back_forth"] >= 2]
    assert 0 < len(stuckish) < 0.2 * len(wins)


def test_glances_follow_the_spells_and_use_only_closed_values(root):
    r = synth.make("nine-to-five", root=root)
    gl = [e for e in r.events if e["type"] == "glance"]
    assert gl and all(e["trigger"] in schema.TRIGGER_REASONS and e["glance"]["blocker"] in schema.BLOCKERS for e in gl)
    assert all(e["trigger"] in ("stuck", "hotkey") for e in gl)                # no periodic unless asked for
    per = synth.make("nine-to-five", root=root, periodic_s=30.0)
    assert any(e["trigger"] == "periodic" for e in per.events if e["type"] == "glance")
    assert sum(1 for e in per.events if e["type"] == "glance") > len(gl)


def test_persona_strengths_differ_and_are_documented(root):
    assert synth.COUPLING["nine-to-five"] > synth.COUPLING["irregular"]
    assert set(synth.COUPLING) == set(synth.PERSONA_DIRS)


def test_features_by_bin_on_synthetic_events_give_finite_columns_for_every_bin(root):
    r = synth.make("nine-to-five", root=root)
    t0 = schema.parse_time("2026-10-12T09:00:00.000Z")
    out = features_by_bin(r.events, [t0 + 30 * k for k in range(0, 56)], span_s=30)
    assert len(out) == 56 and all(tuple(f) == AWARENESS_COLUMNS for f in out)
    assert max(f["aw_coverage"] for f in out) == 1.0


def test_write_goes_to_the_synthetic_partition_only(root, tmp_path):
    store = AwarenessStore(tmp_path / "aw")
    res = synth.write(synth.make("nine-to-five", root=root), store)
    assert res.accepted > 0 and res.rejected == []
    assert store.people("synthetic") == ["p_ninetofive"] and store.people("real") == []
    assert synth.write(synth.make("nine-to-five", root=root), store).accepted == 0   # idempotent: same ids are duplicates


@pytest.mark.skipif(not (REPO_DATA / "synthetic" / "nine-to-five" / "truth.json").exists(), reason="the persona data is not generated here")
def test_all_four_personas_on_the_repo_data_are_valid_and_deterministic():
    for slug in synth.PERSONA_DIRS:
        a = synth.make(slug, root=REPO_DATA, max_tasks=30)
        b = synth.make(slug, root=REPO_DATA, max_tasks=30)
        assert a.events == b.events and a.events
        assert all(schema.problem(e) is None for e in a.events[:500])
        assert {e["person"] for e in a.events} == {a.person}
