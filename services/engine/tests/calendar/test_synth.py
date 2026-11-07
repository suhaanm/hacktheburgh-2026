"""CAL-4: synthetic calendars are deterministic, internally consistent, and the read path recovers what was constructed."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from understudy_engine.calendar import synth
from understudy_engine.calendar.model import week_label
from understudy_engine.plugins.ics import ICSSource

KEYS_EXACT = ("focus_blocks_60", "focus_blocks_90", "longest_focus_min", "back_to_back_runs", "fragmented_days", "external_unbuffered_n",
              "review_slots", "batch_windows", "meetings_n", "days_worked")
KEYS_HOURS = ("meeting_h", "offscreen_h", "recurring_in_peak_h", "outside_hours_h")


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((root / "synthetic" / "calendars").rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_generation_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    synth.generate(a)
    synth.generate(b)
    synth.generate(a, canary=True)
    synth.generate(b, canary=True)
    assert digest(a) == digest(b)


def test_cohort_shape_and_files(store, synth_root):
    assert len(store.people()) == 28
    assert [store.info(p)["group"] for p in store.people()].count("persona") == 4
    assert len(store.people("expert")) == 8 and len(store.people("novice")) == 16
    d = synth_root / "synthetic" / "calendars"
    for p in store.people():
        assert (d / p / "calendar.ics").stat().st_size > 1000 and (d / p / "calendar.json").is_file()
    t = json.loads((d / "truth.json").read_text())
    assert t["meta"]["origin"] == "synthetic" and set(t["problems"]) == set(synth.PROBLEMS)
    assert {w for w in t["people"]["p_exp01"]["weeks"]} == {"2026-W42", "2026-W43", "2026-W44"}
    assert t["people"]["p_ninetofive"]["problems"] == ["fragmented_days"]
    assert all(not t["people"][p]["problems"] for p in store.people("expert"))
    assert any(not t["people"][p]["problems"] for p in store.people("novice"))                  # one clean novice
    counts = {k: sum(k in t["people"][p]["problems"] for p in store.people("novice")) for k in synth.PROBLEMS}
    assert all(3 <= v <= 12 for v in counts.values()), counts                                  # each problem is planted in roughly half


def test_ics_looks_like_a_real_export(synth_root):
    text = (synth_root / "synthetic" / "calendars" / "p_nov05" / "calendar.ics").read_bytes().decode()
    assert text.startswith("BEGIN:VCALENDAR\r\n") and "PRODID:" in text and "BEGIN:VTIMEZONE" in text
    assert "RRULE:FREQ=WEEKLY" in text and "EXDATE" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))                         # folded to 75 octets
    assert "TZID=GMT Standard Time" in text                                                     # odd novices use Outlook's Windows zone name
    even = (synth_root / "synthetic" / "calendars" / "p_nov04" / "calendar.ics").read_bytes().decode()
    assert "TZID=Europe/London" in even
    utc = (synth_root / "synthetic" / "calendars" / "p_ninetofive" / "calendar.ics").read_bytes().decode()
    assert "DTSTART:2026" in utc and "TZID" not in utc.split("BEGIN:VEVENT", 1)[1]


def test_ics_and_json_exports_describe_the_same_events(store):
    for p in store.people():
        a, b = store.get(p, "ics"), store.get(p, "json")
        ka = sorted((x.start, x.end, x.kind, x.tag, x.n_attendees, x.recurring, x.external) for x in a.blocks)
        kb = sorted((x.start, x.end, x.kind, x.tag, x.n_attendees, x.recurring, x.external) for x in b.blocks)
        assert ka == kb, p
        assert a.off_dates == b.off_dates
        assert a.stats.cancelled == b.stats.cancelled and a.stats.declined == b.stats.declined


def test_read_path_recovers_what_was_constructed(store):
    """ICS text -> RRULE expansion, zones, classification, decoys -> features, against the generator's own interval arithmetic."""
    truth = store.truth()["people"]
    n = 0
    for kind in ("ics", "json"):
        for p in store.people():
            pc = store.get(p, kind)
            assert len(pc.weeks) == 3, p
            for m in pc.weeks:
                f = pc.week(m).features
                c = truth[p]["weeks"][week_label(m)]["construction"]
                n += 1
                for k in KEYS_EXACT:
                    assert f[k] == c[k], (kind, p, week_label(m), k, f[k], c[k])
                for k in KEYS_HOURS:
                    assert abs(f[k] - c[k]) <= 0.06, (kind, p, week_label(m), k, f[k], c[k])
                assert abs(f["fragmentation"] - c["fragmentation"]) <= 0.01
    assert n == 168


def test_planted_structure_is_visible_in_the_features(store):
    truth = store.truth()["people"]

    def feats(p):
        pc = store.get(p)
        return [pc.week(m).features for m in pc.weeks]

    for f in feats("p_ninetofive"):
        assert f["fragmented_days"] >= 3                       # planted on three days a week
    for f in feats("p_nightowl"):
        assert f["focus_blocks_90"] == 0 and f["meeting_h"] > 20 and f["offscreen_h"] == 0
    for f in feats("p_shiftwkr"):
        assert f["back_to_back_runs"] >= 3 and f["external_unbuffered_n"] >= 1
    for f in feats("p_irregular"):
        assert f["recurring_in_peak_h"] >= 2.0 and f["review_slots"] == 0
    for p in store.people("expert"):
        for f in feats(p):
            assert f["fragmented_days"] == 0 and f["focus_blocks_90"] >= 6 and f["review_slots"] >= 2 and f["recurring_in_peak_h"] == 0
            assert f["meeting_h"] <= 7.5 and f["back_to_back_runs"] <= 1 and f["outside_hours_h"] == 0
    # every planted label has a matching construction on at least one person-week (nothing is planted only on paper)
    seen = {k: 0 for k in synth.PROBLEMS}
    for p, rec in truth.items():
        for w, t in rec["weeks"].items():
            seen["fragmented_days"] += bool(t["fragmented_days"])
            seen["back_to_back_runs"] += bool(t["back_to_back_days"])
            seen["unbuffered_external"] += bool(t["unbuffered_external_days"])
            seen["late_meetings"] += bool(t["late_days"])
            seen["no_focus_blocks"] += bool(t["no_focus_blocks"])
            seen["no_review_slot"] += bool(t["no_review_slot"])
            seen["no_breaks"] += bool(t["no_breaks"])
            seen["recurring_in_peak"] += t["recurring_in_peak_h_planted"] > 0
    assert all(v > 0 for v in seen.values()), seen


def test_decoys_are_present_and_ignored(store):
    pc = store.get("p_exp02")
    st = pc.stats
    assert st.cancelled + st.declined + st.free_skipped >= 1
    total = sum(store.get(p).stats.cancelled for p in store.people())
    assert total > 10 and sum(store.get(p).stats.days_off for p in store.people()) >= 2         # an all-day out-of-office exists in the cohort


def test_clock_change_is_in_the_london_calendars(store):
    pc = store.get("p_exp01")
    hours = {(b.start.date() >= date(2026, 10, 25), b.start.hour) for b in pc.blocks if b.kind == "offscreen"}
    # lunch is 12:30 local: 11:30 UTC in BST, 12:30 UTC in GMT
    assert (False, 11) in hours and (True, 12) in hours


def test_persona_calendars_follow_their_schedules(store):
    pc = store.get("p_shiftwkr")
    wk0 = pc.week(pc.weeks[0])
    worked = [d.dow for d in wk0.days if d.working]
    assert worked == [0, 1, 3, 4, 6]                                    # Sunday, Monday, Tuesday, Thursday, Friday... see profile
    assert pc.work.by_date[date(2026, 10, 12)] == (360, 855)            # early shift 06:00-14:15 before the swap
    assert pc.work.by_date[date(2026, 10, 26)] == (840, 1335)           # after day 15 the shifts swap
