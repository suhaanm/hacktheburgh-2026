"""Canary flows for the privacy track's measurement (PRV-1, PRV-4): the REAL evidence flow, run with canaries planted.

``FLOWS`` is read by ``understudy_engine.privacy.evaluate`` (``understudy_engine/<layer>/canary_flows.py``; the layer name ``evidence``
needs adding to its ``LAYERS`` tuple). Each fixture is the data the builders read (the ``/genome`` payload, the ``/hazard`` payload,
the coach decision and the ``/routines`` rows) with planted names, emails, meeting titles, paths, commit messages and customer names
in every place a string can sit: the person fields, the notes and messages, the routine titles and touched sites, the coach's message
and target hint, the consequence rows' sources and notes. The real flow then builds the packet, builds the request and asks the
CLOUD route for an explanation through ``egress.send(..., port=port)``; only the model port is faked. What is checked by the kit:
zero planted tokens in the captured request, in the ledger and other artifacts and in the logs, and one ledger line per request.

The local-model route is covered by the evidence test-suite (its fake client records the messages and they are scanned the same way).
"""
from __future__ import annotations

from typing import Any

from ..privacy.testing import CanaryFlow, CapturingPort
from . import explain as E
from . import packet as P


def make_fixtures() -> dict[str, Any]:
    seg_n = [{"cog": "SEARCH", "t0": 0.0, "t1": 60.0}, {"cog": "READ_RESULT", "t0": 60.0, "t1": 130.0}]
    seg_e = [{"cog": "SEARCH", "t0": 0.0, "t1": 20.0}, {"cog": "READ_RESULT", "t0": 20.0, "t1": 60.0}]
    return {
        "genome": {
            "data": {
                "person": "Ada Lovelace", "episode": "t_nov01a", "expert_person": "Charles Babbage", "owner": "Grace Hopper",
                "novice": {"segments": seg_n}, "expert": {"segments": seg_e}, "person_gap_s": 70.0,
                "person_waterfall": [{"label": "Search loops", "seconds": 40.0, "title": "Quarterly planning review"},
                                     {"label": "Long pauses", "seconds": 20.0, "notes": "weekly sync with the finance team"},
                                     {"label": "Repeated reads", "seconds": 10.0, "description": "reads the payroll sheet again"}],
                "waterfall": [{"label": "Search loops", "seconds": 40.3, "ci": [21.7, 58.6], "name": "Dev Person"},
                              {"label": "Long pauses", "seconds": 38.5, "ci": [14.7, 64.2]},
                              {"label": "Rework", "seconds": 5.0, "ci": [1.0, 9.0]}],
                "total_gap_s": 229.6, "total_gap_ci": [193.1, 269.9],
                "controls": {"placebo": {"gap_s": 7.1, "ci": [-3.1, 18.4]}, "null": {"gap_s": 43.6, "ci": [-45.1, 109.1]}},
                "people": {"novices": ["Ada Lovelace", "Alan Turing", "Edsger Dijkstra"], "experts": ["Charles Babbage"]},
                "decomposition": {"components": [{"cog": "READ_RESULT", "seconds": 88.6, "ci": [41.4, 152.4], "path": "/Users/someone/notes/ledger.py"},
                                                 {"cog": "SEARCH", "seconds": 25.0, "ci": [-28.3, 69.2]}]},
                "consequences": [{"step": "RECONCILE", "p_error": 0.103, "p_error_ci95": [0.078, 0.13], "mean_error_gbp": 291.89, "n": 200,
                                  "customer": "Acme Holdings Ltd", "message": "fix rounding bug for Acme", "source": "evals/cases/skip_consequences.json#x",
                                  "note": "gives a wrong answer on about 20.7 of 200 households"}],
            },
            "meta": {"origin": "synthetic", "n": 24, "n_unit": "people", "author": "Linus Torvalds"},
        },
        "hazard": {
            "series": [{"t": "2026-11-02T09:00:31Z", "p": 0.62}, {"t": "2026-11-02T09:01:01Z", "p": 0.41}],
            "model": {"log_loss": 0.436, "brier": 0.14, "ece": 0.015}, "baselines": {"time_since_progress": {"log_loss": 0.509}},
            "false_alarms_per_hour": 1.21,
            "person": {"id": "Ada Lovelace", "alarm_rule": {"threshold": 0.579}, "email": "ada.lovelace@example.test"},
        },
        "coach": {"action": "nudge", "level": "L2", "trigger": "stuck", "reason_codes": ["stuck_signal", "gate_act"], "gate": {"consecutive": 2},
                  "missed": ["Open the payroll workbook"], "p_stuck": 0.62, "p_source": "hazard", "message": "Try opening the Acme invoice",
                  "why": "The expert opens the contract first", "target": {"label_hint": "Submit to claimant record", "site": "internal.example.test"}},
        "routines": [{"id": "calc-entry-3x", "title": "Enter the household for the Smith family", "episodes": 14, "minutes_per_week": 96.0, "cv": 0.18,
                      "judgement_share": 0.07, "value": {"hours_saved": [3.1, 5.2], "horizon_weeks": 4}, "status": "shadow", "rung": "A1",
                      "shadow": {"runs": 12, "matches": 12, "wilson_lower": 0.757}, "touches": ["GovCalc", "case note"],
                      "customer": "Acme & Sons", "path": "/Users/someone/Projects/ledger/steps.json"}],
    }


def run(fixtures: dict[str, Any], port: CapturingPort) -> dict[str, Any]:
    """The real flow: builders, request, and the cloud route through the egress guard. Only the port is a fake."""
    g = fixtures["genome"]
    pk = P.from_genome(g["data"], g["meta"])
    hz = P.from_hazard(fixtures["hazard"])
    coach, _ = P.from_coach(fixtures["coach"])
    pk = P.combine(pk, hazard=hz, coach=coach, routines=P.from_routines(fixtures["routines"]))
    out = E.explain(pk, "why did this case take 14 minutes?", backends=E.Backends(cloud=E.CloudBackend(port=port)))
    return out


FLOWS = [CanaryFlow(name="evidence.explain_cloud", make_fixtures=make_fixtures, run=run, layer="evidence", kind="integration",
                    min_requests=1, mode="replace")]
