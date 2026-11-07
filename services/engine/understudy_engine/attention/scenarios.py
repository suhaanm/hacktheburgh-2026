"""The five scripted scenario days of ``evals/attention/PLAN.md`` section 4 (S1 to S5), each with explicit assertions and the numbers behind them.

Scripted means the schedule, the meeting, the call, the share and the key events are fixed here, so an assertion is a statement about the
router, not about luck. SIMULATED like everything in this layer: nobody is real. The assertions are written to fail loudly if the router
stops doing what ``docs/ATTENTION_DESIGN.md`` says; they are also unit tests (``tests/attention/test_scenarios.py``).

Hours are absolute from midnight of the first simulated day (so 11.75 is 11:45).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from . import texts
from . import vocab as V
from .events import Event, Item
from .simulate import BASE_T, DaySched, Raw, WorkerSpec, build_world, population, run_condition
from .state import DEFAULT, Params, Settings

H = 3600.0


def _t(hour: float) -> float:
    return BASE_T + hour * H


def _spec(seed: int, persona: str = "nine-to-five", **kw: Any) -> WorkerSpec:
    return WorkerSpec(f"s{seed}_{persona[:3]}", persona, seed, **kw)


def _days(*windows: tuple[float, float], n: int = 2) -> list[DaySched]:
    out = [DaySched("normal", (w,)) for w in windows]
    while len(out) < n:
        out.append(DaySched("normal", ((9.0, 17.25),)))
    return out


def _displays(trace: list[dict], **kw: Any) -> list[dict]:
    return [e for e in trace if e["e"] == "display" and all(e.get(k) == v for k, v in kw.items())]


def _polls(trace: list[dict]) -> list[dict]:
    return [e for e in trace if e["e"] == "poll"]


def _cls(type_id: str) -> str:
    return V.TYPES[type_id].cls


def _contrast(world, params: Params, settings: Settings | None) -> dict[str, Any]:
    out = {}
    for c in ("B1", "B2"):
        r = run_condition(world, c, params=params, settings=settings)
        out[c] = {"displays": r.displays, "hard_quiet_breaches": r.hq_breaches, "flow_displays": r.flow_displays, "important_seen": r.important_seen,
                  "important_n": r.important_n, "safety_missed": r.safety_missed, "cost_s": round(r.cost_s, 1)}
    return out


def _run(world, params: Params, settings: Settings | None):
    from .simulate import Runner

    r = Runner(world, "R", params=params, settings=settings, trace=True)
    res = r.run()
    return r, res


def _result(name: str, title: str, checks: dict[str, bool], numbers: dict[str, Any], contrast: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": name, "title": title, "assertions": checks, "passed": all(checks.values()), "numbers": numbers, "contrast": contrast or {}}


# ------------------------------------------------------------------------------------------------ S1
def s1_overnight_approval(seed: int = 0, *, params: Params = DEFAULT, settings: Settings | None = None, background: bool = False) -> dict[str, Any]:
    spec = _spec(seed)
    ret = 8.0 + 50.0 / 60.0
    extra = [Raw(_t(2.0 + k), "run_finished", f"s1n{k}", {"outcome": "done", "run_mode": "overnight"}, "agent") for k in range(3)]
    extra += [Raw(_t(4.5), "approval_blocking", "qs1", {"blocks_run": True}, "queue", reraise=True),
              Raw(_t(6.5), "morning_report", "s1rep", {"count": 1}, "agent"),
              Raw(_t(ret + 0.02), "briefing_ready", "s1gen", {"count": 2}, "proactive")]
    world = build_world(spec, 2, days=_days((ret, 17.25)), extra=extra, background=background)
    r, res = _run(world, params, settings)
    tr = r.trace or []
    disp = sorted(_displays(tr), key=lambda e: e["t"])
    after = [d for d in disp if d["t"] >= _t(ret)]
    appr = _displays(tr, type="approval_blocking", reminder=False)
    polls_night = [p for p in _polls(tr) if _t(4.5) <= p["t"] < _t(ret)]
    arr = r.arr.get(("approval_blocking", "qs1"))
    digest = r.svc.digest(r.pid, "morning") if r.svc else {}
    digest_toasts = [d for d in disp if d["type"] == "attention_digest"]
    checks = {
        "approval_is_the_first_thing_shown_on_return": bool(after) and after[0]["type"] == "approval_blocking" and after[0]["t"] - _t(ret) <= 30.0,
        "approval_is_shown_exactly_once": len(appr) == 1,
        "a_badge_exists_from_the_moment_it_arrived": bool(polls_night) and all(p["badges"]["needs_you"] >= 1 for p in polls_night),
        "at_most_one_reminder": res.reminder_displays <= 1,
        "the_summary_does_not_announce_it_a_second_time": not digest_toasts,
        "it_was_seen_in_its_window": arr is not None and arr.seen is not None and arr.start is not None and arr.seen - arr.start <= 900.0,
    }
    nums = {"seconds_from_return_to_first_display": round(after[0]["t"] - _t(ret), 1) if after else None, "displays": res.displays,
            "reminders": res.reminder_displays, "badge_polls_overnight": len(polls_night), "summary_lines": digest.get("lines", []),
            "summary_counts": digest.get("counts", {})}
    return _result("S1", "Overnight approval", checks, nums, _contrast(world, params, settings))


# ------------------------------------------------------------------------------------------------ S2
def s2_meeting_and_share(seed: int = 0, *, params: Params = DEFAULT, settings: Settings | None = None, background: bool = False) -> dict[str, Any]:
    spec = _spec(seed)
    extra = [Raw(_t(11.0 + 10 / 60), "cue_cue", "e_s2a", {"expires_in_s": 12.0}, "cue"), Raw(_t(11.0 + 35 / 60), "cue_cue", "e_s2b", {"expires_in_s": 12.0}, "cue"),
             Raw(_t(11.0 + 50 / 60), "cue_cue", "e_s2c", {"expires_in_s": 12.0}, "cue"),
             Raw(_t(11.0 + 40 / 60), "approval_blocking", "qs2", {"blocks_run": True}, "queue", reraise=True),
             Raw(_t(11.75), "injection_pause", "ij2", {"run_mode": "foreground"}, "agent", reraise=True)]
    world = build_world(spec, 2, days=_days((9.0, 17.25)), scripted={"meeting": [(11.0, 13.0)], "share": [(11.0 + 20 / 60, 12.0)]}, extra=extra, background=background)
    world.glances, world.dashes = np.array([]), np.array([])      # the worst case for a held item: this worker never looks at the tray today
    r, res = _run(world, params, settings)
    tr = r.trace or []
    inside = [d for d in _displays(tr) if _t(11.0) <= d["t"] < _t(13.0) and _cls(d["type"]) != V.SAFETY]
    inj = [d for d in _displays(tr, type="injection_pause") if _t(11.75) <= d["t"] <= _t(11.75) + 60.0]
    rendered = texts.render_item(Item.from_event(Event(type="injection_pause", person="p_x", subject="ij2"), "i_x", _t(11.75)))
    appr = [d for d in _displays(tr, type="approval_blocking", reminder=False) if d["t"] >= _t(11.0)]
    arr = r.arr.get(("approval_blocking", "qs2"))
    dropped_cues = sum(n for k, n in res.dropped.items() if k.startswith("dropped_"))
    # An item held for over `max_hold_soft_s` (here: about 80 minutes) is shown at the first moment the worker is present, not typing and has been
    # quiet for 2 s: waiting for a full natural break on top of that would only add delay.
    def _pause(x: float) -> bool:
        w_ = world.tl.ws(float(x))
        return bool(world.tl.present[world.tl.idx(float(x))]) and w_.hard_quiet() is None and not w_.typing_burst and w_.quiet_s >= params.flow_quiet_s

    t_break = next((x for x in np.arange(_t(13.0), _t(17.0), 5.0) if _pause(float(x))), None)
    checks = {
        "no_non_safety_interruption_in_the_meeting": not inside,
        "all_three_cues_were_dropped_not_shown": dropped_cues == 3 and not _displays(tr, type="cue_cue"),
        "the_injection_pause_was_shown_within_10_s_during_the_share": bool(inj) and inj[0]["t"] - _t(11.75) <= 10.0 and inj[0]["ctx"] == "hard_quiet",
        "its_wording_is_content_free": "ij2" not in f"{rendered['title']} {rendered['body']}" and not texts.lint(rendered["title"], rendered["body"]),
        "the_held_approval_is_shown_at_the_first_pause_after_the_meeting": bool(appr) and t_break is not None and 0.0 <= appr[0]["t"] - float(t_break) <= 15.0,
        "the_held_approval_is_not_lost": arr is not None and arr.seen is not None,
    }
    nums = {"meeting_interruptions_non_safety": len(inside), "cues_dropped": dropped_cues, "dropped_by_reason": dict(res.dropped),
            "injection_seconds_to_display": round(inj[0]["t"] - _t(11.75), 1) if inj else None,
            "approval_displayed_minutes_after_meeting": round((appr[0]["t"] - _t(13.0)) / 60.0, 1) if appr else None,
            "first_pause_after_meeting_minutes": round((float(t_break) - _t(13.0)) / 60.0, 1) if t_break is not None else None}
    return _result("S2", "Meeting and screen share", checks, nums, _contrast(world, params, settings))


# ------------------------------------------------------------------------------------------------ S3
def s3_injection_in_long_run(seed: int = 0, *, params: Params = DEFAULT, settings: Settings | None = None, background: bool = False) -> dict[str, Any]:
    spec = _spec(seed)
    t0 = 11.0
    extra = [Raw(_t(t0), "injection_pause", "ij3", {"run_mode": "foreground"}, "agent", reraise=True),
             Raw(_t(t0) + 20.0, "cue_cue", "e_s3", {"expires_in_s": 12.0}, "cue"), Raw(_t(t0) + 30.0, "run_finished", "s3rf", {"outcome": "done", "run_mode": "background"}, "agent"),
             Raw(_t(t0) + 40.0, "help_level_changed", "lv_s3", {"expires_in_s": 60.0}, "coach")]
    world = build_world(spec, 2, days=_days((9.0, 17.25)), scripted={"typing": [(9.5, 12.5)]}, extra=extra, background=background)
    r, res = _run(world, params, settings)
    tr = r.trace or []
    inj = _displays(tr, type="injection_pause", reminder=False)
    others = [d for d in _displays(tr) if _t(t0) <= d["t"] < _t(t0) + 60.0 and d["type"] != "injection_pause"]
    arr = r.arr.get(("injection_pause", "ij3"))
    window = [p for p in _polls(tr) if arr is not None and _t(t0) <= p["t"] <= (arr.resolved or _t(t0))]
    ws = world.tl.ws(_t(t0))
    checks = {
        "the_worker_was_typing_in_a_long_run": ws.typing_burst or ws.deep_work,
        "shown_within_5_s_despite_typing": bool(inj) and inj[0]["t"] - _t(t0) <= 5.0,
        "exactly_one_toast": len(inj) == 1,
        "the_marker_persists_until_resolved": bool(window) and all(p["badges"]["needs_you"] >= 1 for p in window),
        "no_reminder": res.reminder_displays == 0,
        "nothing_else_interrupts_in_that_minute": not others,
    }
    nums = {"seconds_to_display": round(inj[0]["t"] - _t(t0), 1) if inj else None, "typing": bool(ws.typing_burst), "deep_work": bool(ws.deep_work),
            "seconds_marker_persisted": round((arr.resolved - _t(t0)), 1) if arr is not None and arr.resolved else None}
    return _result("S3", "Injection pause in a long run", checks, nums, _contrast(world, params, settings))


# ------------------------------------------------------------------------------------------------ S5
def s5_kill_state(seed: int = 0, *, params: Params = DEFAULT, settings: Settings | None = None, background: bool = False) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    specs = {"call": ({"call": [(10.0, 11.0)]}, 10.0 + 20 / 60, (9.0, 17.25), 300.0),
             "away": ({}, 7.0, (9.0, 17.25), 2.0 * H + 600.0),          # still stopped when the worker is back; they resume ten minutes after
             "typing": ({"typing": [(13.0, 15.0)]}, 14.0, (9.0, 17.25), 300.0)}
    for name, (scripted, at, win, clear_after) in specs.items():
        extra = [Raw(_t(at), "kill_engaged", f"k_{name}", {}, "kill"), Raw(_t(at) + clear_after, "kill_cleared", f"k_{name}", {}, "kill")]
        world = build_world(_spec(seed, "nine-to-five"), 2, days=_days(win), scripted=scripted, extra=extra, background=background)
        r, res = _run(world, params, settings)
        tr = r.trace or []
        polls_after = [p for p in _polls(tr) if p["t"] >= _t(at)]
        first_poll = polls_after[0] if polls_after else None
        kd = [d for d in _displays(tr, type="kill_engaged")]
        lat = (kd[0]["t"] - _t(at)) if kd else None
        away = name == "away"
        stopped_polls = [p for p in polls_after if p["t"] < _t(at) + clear_after]
        checks[f"{name}: the stopped marker is present at the first poll"] = bool(first_poll) and first_poll["badges"]["stopped"] is True and first_poll["badges"]["marker"] == "stopped"
        checks[f"{name}: the marker stays until it is cleared"] = bool(stopped_polls) and all(p["badges"]["stopped"] for p in stopped_polls)
        if away:
            checks["away: the notice is first on return"] = bool(kd) and 0.0 <= kd[0]["t"] - _t(win[0]) <= 30.0
        else:
            checks[f"{name}: the notice is shown at once"] = bool(kd) and lat is not None and lat <= 5.0
        after = [p for p in _polls(tr) if _t(at) + clear_after + 30.0 <= p["t"] < _t(at) + clear_after + 900.0]
        checks[f"{name}: the marker clears when it is cleared"] = bool(after) and all(not p["badges"]["stopped"] for p in after)
        cases[name] = {"first_poll_stopped": bool(first_poll and first_poll["badges"]["stopped"]), "seconds_to_notice": None if lat is None else round(lat, 1),
                       "notice_ctx": kd[0]["ctx"] if kd else None}
    return _result("S5", "Kill state", checks, cases)


# ------------------------------------------------------------------------------------------------ S4
def s4_dismisses_everything(seed: int = 0, *, per_archetype: int = 2, n_work_days: int = 14, params: Params = DEFAULT, settings: Settings | None = None,
                            n_boot: int = 400, root=None) -> dict[str, Any]:
    from .evaluate import boot_diff

    specs = population(seed, per_archetype, dismiss_all=True)
    helpful_e, helpful_l, wait_e, wait_l, nl_late = [], [], [], [], []
    approvals_seen = approvals_n = safety_missed = safety_n = 0
    appr_shown = appr_total = 0
    for sp in specs:
        w = build_world(sp, n_work_days, root=root)
        wd = [i for i, d in enumerate(w.days) if d.windows]
        r = run_condition(w, "R", params=params, settings=settings)
        nl = run_condition(w, "R-nolearn", params=params, settings=settings)

        def mean_days(res, key: str, idxs: list[int]) -> float:
            return float(np.mean([res.per_day[i].get(key, 0) for i in idxs])) if idxs else 0.0

        early, late = wd[:3], wd[-3:]
        helpful_e.append(mean_days(r, "cls_now", early))
        helpful_l.append(mean_days(r, "cls_now", late))
        wait_e.append(mean_days(r, "wait_toasts", early))
        wait_l.append(mean_days(r, "wait_toasts", late))
        nl_late.append(mean_days(nl, "cls_now", late))
        approvals_n += r.time_n
        approvals_seen += r.time_n - r.time_missed
        safety_missed += r.safety_missed
        safety_n += r.safety_n
        appr_total += sum(d.get("type_approval_blocking", 0) for d in r.per_day)
    he, hl, we, wl, nl_l = map(np.array, (helpful_e, helpful_l, wait_e, wait_l, nl_late))
    d_help = boot_diff(hl, he, n_boot, seed)
    d_wait = boot_diff(wl, we, n_boot, seed + 1)
    d_nolearn = boot_diff(hl, nl_l, n_boot, seed + 2)
    checks = {
        "helpful_now_interruptions_fall_from_the_first_days_to_the_last_days": d_help["hi"] < 0.0,
        "learning_is_what_made_the_difference_vs_the_same_worker_without_it": d_nolearn["hi"] < 0.0,
        "time_sensitive_items_are_still_seen_in_their_window": approvals_n > 0 and approvals_seen / approvals_n >= 0.95,
        "no_safety_item_missed": safety_missed == 0,
        "approval_toasts_were_still_shown": appr_total > 0,
    }
    nums = {"workers": len(specs), "working_days": n_work_days, "helpful_per_day_first3": round(float(he.mean()), 2), "helpful_per_day_last3": round(float(hl.mean()), 2),
            "helpful_late_minus_early": d_help, "wait_toasts_per_day_first3": round(float(we.mean()), 3), "wait_toasts_per_day_last3": round(float(wl.mean()), 3),
            "wait_late_minus_early": d_wait, "helpful_late_router_minus_nolearn": d_nolearn,
            "time_sensitive_seen_share": round(approvals_seen / approvals_n, 3) if approvals_n else None, "safety_missed": safety_missed, "safety_n": safety_n,
            "approval_toasts_shown": appr_total}
    return _result("S4", "A worker who dismisses everything", checks, nums)


def run_all(seed: int = 0, *, params: Params = DEFAULT, settings: Settings | None = None, fast: bool = False, root=None) -> dict[str, Any]:
    out = {"S1": s1_overnight_approval(seed, params=params, settings=settings), "S2": s2_meeting_and_share(seed, params=params, settings=settings),
           "S3": s3_injection_in_long_run(seed, params=params, settings=settings), "S5": s5_kill_state(seed, params=params, settings=settings),
           "S4": s4_dismisses_everything(seed, per_archetype=1 if fast else 2, n_work_days=10 if fast else 14, params=params, settings=settings,
                                         n_boot=150 if fast else 400, root=root)}
    return dict(sorted(out.items()))
