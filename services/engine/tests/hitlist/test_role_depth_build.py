"""RD (7 Nov 2026): the hit list's rules read the new routine templates the way their authors meant. Planted repeats of each new template go through
``build_hitlist`` with the programmer and data-analyst packs: the harmless ones are listed under the pack's own words and stop before the right
thing, the ones that need judgement or cannot be undone are counted as held back and never listed. (Before the templates were given the four steps
the routine finder needs, most of them could never have been found: the finder never reports a routine shorter than four steps.)"""
from __future__ import annotations

import pytest

from understudy_engine.hitlist import vocab as V
from understudy_engine.hitlist.build import build_hitlist
from understudy_engine.memory import load_pack

from .conftest import NOW, P, many


def run(eps, pack):
    return build_hitlist(eps, pack, person=P, now=NOW)


def held(r) -> dict[str, int]:
    return {h["reason"]: h["count"] for h in r["held_back"]}


def plant(pack, template_id, n=12):
    return many(list(pack.template(template_id)["cogs"]), n, prefix=template_id[:6])


# template id -> (label, key, what it stops before). The stop is the most serious class in the template's own `never` list.
LISTED_PROGRAMMER = {
    "open-pr-from-branch": ("Open a pull request from the branch", "pull request", "release"),
    "ci-status-sweep": ("Check CI on my open pull requests", "CI", "release"),
    "post-release-watch": ("Watch the logs for ten minutes after a release", "logs", "release"),
    "profile-and-note-hot-path": ("Profile the slow endpoint and note the top frames", "slow endpoint", "release"),
    "bisect-regression-range": ("Bisect the range between a good and a bad commit", "good and a bad commit", "delete"),
    "migration-dry-run": ("Draft the migration and dry-run it on a copy", "migration", "delete"),
    "add-failure-log-line": ("Add a log line at the failing branch", "log line", "release"),
    "dependency-bump-pr": ("Bump a dependency and open a pull request", "dependency", "release"),
    "docs-lookup-and-apply": ("Look up the same API again and apply the example", "same API", "release"),
}
LISTED_ANALYST = {
    "reload-and-reprofile": ("Reload the dataset and re-run the profile", "dataset", "delete"),
    "parameterised-weekly-query": ("Run the saved query for a new week", "saved query", "delete"),
    "reconcile-and-note-gap": ("Compare the total with the control and note the gap", "control", "message"),
    "join-check-and-count": ("Join the two tables and check the row counts", "two tables", "delete"),
    "segment-breakdown-chart": ("Break the metric down by segment and chart it", "segment", "share"),
    "interval-for-a-rate": ("Add an interval to a rate before charting it", "interval", "share"),
    "notebook-restart-and-run": ("Restart the notebook and run it top to bottom", "notebook", "delete"),
    "draft-metric-definition": ("Draft the metric definition from the saved query", "metric definition", "delete"),
    "send-weekly-extract": ("Export the weekly extract for a stakeholder", "weekly extract", "message"),
}
HELD = {
    "programmer": ["review-queue-triage", "rollback-after-alert", "reply-to-review-comments"],
    "data-analyst": ["magnitude-and-units-check", "send-peer-check", "schedule-refresh-with-alert"],
}


@pytest.mark.parametrize("role,table", [("programmer", LISTED_PROGRAMMER), ("data-analyst", LISTED_ANALYST)])
def test_the_automatable_templates_are_listed_in_the_packs_words_and_stop_before_the_right_thing(role, table):
    pack = load_pack(role)
    new_automatable = {t["id"] for t in pack.templates if "steps" in t and t["automatable"]}
    assert set(table) == new_automatable                                   # the table is complete: no new template escapes the check
    for tid, (label, key, stops) in table.items():
        r = run(plant(pack, tid), pack)
        assert [x["id"] for x in r["rows"]] == [tid], (tid, r["state"], held(r))
        row = r["rows"][0]
        assert (row["label"], row["key"], row["stops_before"]) == (label, key, stops), tid
        assert row["stops_before"] == V.stops_for_never(pack.template(tid)["never"])
        assert row["judgement_share"] == pytest.approx(pack.template(tid)["judgement_share"], abs=0.011), tid
        assert row["family"] in V.FAMILIES


@pytest.mark.parametrize("role", ["programmer", "data-analyst"])
def test_the_templates_that_need_judgement_or_cannot_be_undone_are_held_back_and_never_listed(role):
    pack = load_pack(role)
    assert set(HELD[role]) == {t["id"] for t in pack.templates if "steps" in t and not t["automatable"]}
    for tid in HELD[role]:
        r = run(plant(pack, tid), pack)
        assert r["rows"] == [] and held(r).get("judgement") == 1, (tid, r["state"], held(r))


def test_a_routine_that_begins_with_a_rollback_is_held_back_for_its_first_step():
    """The hit list reads the first step of a sequence from the cog's own words. ROLL_BACK is a release-class action, so a routine that starts by
    rolling back is never listed, whatever its template says."""
    pack = load_pack("programmer")
    assert V.step_risk("ROLL_BACK") == "release"
    r = run(many(["ROLL_BACK", "WATCH_PROD", "NAVIGATE", "READ_TRACE"], 12, prefix="rb"), pack)
    assert r["rows"] == [] and held(r).get("irreversible_first_step") == 1


def test_no_new_cog_but_the_rollback_is_misread_as_irreversible_or_outward():
    """A new cog whose name carries a risk word would hold back a harmless routine, so the ids avoid MESSAGE, DEPLOY, ISSUE, EXPORT and the like."""
    for role in ("programmer", "data-analyst"):
        for cog in load_pack(role).extra_cogs[10:]:
            assert V.step_risk(cog) == ("release" if cog == "ROLL_BACK" else None), (role, cog, V.step_risk(cog))
