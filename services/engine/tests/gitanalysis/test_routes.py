from __future__ import annotations

import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from understudy_engine import routes_git
from understudy_engine.gitanalysis import service, synth
from understudy_engine.gitanalysis.features import HABIT_IDS


@pytest.fixture
def client(service_env):
    app = FastAPI()
    app.include_router(routes_git.router)
    return TestClient(app)


def test_flag_off_refuses(client, monkeypatch):
    monkeypatch.delenv("UNDERSTUDY_X_GIT")
    r = client.get("/git/habits")
    assert r.status_code == 404 and r.json()["error"]["code"] == "extension_off"
    assert client.get("/git/people").status_code == 404
    monkeypatch.setenv("UNDERSTUDY_X", "1")
    assert client.get("/git/people").status_code == 200


def test_habits_contract_shape(client):
    r = client.get("/git/habits", params={"person": "p_git_learner_1", "repo": "r_git_learner_1"})
    assert r.status_code == 200
    j = r.json()
    meta, data = j["meta"], j["data"]
    assert meta["origin"] == "synthetic" and meta["n_unit"] == "commits" and meta["n"] == data["n_commits"] > 50
    assert meta["interval_level"] == 0.95 and meta["split"] and meta["note"] and meta["generated_at"]
    assert data["digest_source"] in ("model", "rules") and data["digest_source"] == "rules"
    assert [h["id"] for h in data["habits"]] == list(HABIT_IDS)
    for h in data["habits"]:
        assert {"id", "label", "learner", "expert", "delta", "ci"} <= set(h)
        assert len(h["ci"]) == 2 and h["ci"][0] <= h["delta"] <= h["ci"][1]
    flagged = {h["id"] for h in data["habits"] if h["flagged"]}
    assert {"big_commits", "tests_with_changes"} <= flagged                       # planted for learner 1
    assert all("suggestion" in h for h in data["habits"] if h["flagged"])
    assert data["reference"]["n_experts"] == 8 and data["features"]["n_commits"] == data["n_commits"]
    assert 1 <= len(data["suggestions"]) <= 5 and all(s["risk"] == "low" for s in data["suggestions"])


def test_default_person_and_people(client):
    assert client.get("/git/habits").json()["data"]["person"] == "p_git_learner_1"
    p = client.get("/git/people").json()
    assert len(p["learners"]) == 4 and len(p["experts"]) == 8


def test_planted_habits_per_learner_through_the_api(client):
    got = {}
    for person in ("p_git_learner_2", "p_git_learner_3"):
        d = client.get("/git/habits", params={"person": person}).json()["data"]
        got[person] = {h["id"] for h in d["habits"] if h["flagged"]}
    assert "fix_after_fix" in got["p_git_learner_2"] and "late_night" in got["p_git_learner_3"] and "vague_messages" in got["p_git_learner_3"]
    assert "big_commits" not in got["p_git_learner_3"]                              # a negative stays a negative


def test_errors_are_plain(client):
    r = client.get("/git/habits", params={"person": "p_nobody"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_person" and "p_git_learner_1" in r.json()["error"]["message"]
    r = client.get("/git/habits", params={"person": "p_git_learner_1", "repo": "r_git_learner_2"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_repo"
    assert client.get("/git/habits", params={"repo": "../../etc"}).status_code == 422          # ids only, never paths
    assert client.get("/git/habits", params={"repo": "/etc/passwd"}).status_code == 422
    assert client.get("/git/habits", params={"digest": "model"}).status_code == 422


def test_a_path_can_never_be_requested(client, tmp_path):
    other = synth.make_repo(synth.RepoSpec(person="p_sneak", days=5, seed=4), tmp_path / "sneak")
    r = client.get("/git/habits", params={"repo": str(other)})
    assert r.status_code == 422
    r = client.get("/git/habits", params={"repo": "sneak"})
    assert r.status_code == 404                                                       # not registered


def test_registered_repo_is_mixed_origin(client, monkeypatch, tmp_path):
    mine = synth.make_repo(synth.learner_specs(210)[2], tmp_path / "mine")
    monkeypatch.setenv("UNDERSTUDY_GIT_REPOS", f"mine={mine}")
    j = client.get("/git/habits", params={"repo": "mine"}).json()
    assert j["meta"]["origin"] == "mixed" and "synthetic" in j["meta"]["note"] and j["data"]["repo"] == "mine"
    assert client.get("/git/people").json()["registered"] == ["mine"]


def test_unreadable_registered_repo_is_a_plain_422(client, monkeypatch, tmp_path):
    bad = tmp_path / "bad"
    (bad / ".git").mkdir(parents=True)
    monkeypatch.setenv("UNDERSTUDY_GIT_REPOS", f"bad={bad}")
    r = client.get("/git/habits", params={"repo": "bad"})
    assert r.status_code == 422 and str(bad) not in r.text


def test_placebo_option(client):
    d = client.get("/git/habits", params={"placebo": 1}).json()["data"]
    assert d["placebo"]["status"] == "ok" and d["placebo"]["false_flags"]["n"] >= 40


def test_responses_carry_numbers_and_enums_only(client, cohort_template):
    j = client.get("/git/habits", params={"person": "p_git_learner_4"}).json()
    text = json.dumps(j)
    truth = synth.load_truth(cohort_template / "p_git_learner_4" / "repo")
    assert truth["person"] in text                                                    # the learner id is an id, not content
    assert not re.search(r"\b[0-9a-f]{40}\b", text)                                   # no commit ids
    assert "@" not in text and "src/" not in text and "tests/" not in text and ".py" not in text
    import subprocess
    subjects = subprocess.run(["git", "-C", str(cohort_template / "p_git_learner_4" / "repo"), "log", "--format=%s"], capture_output=True, text=True,
                              check=True).stdout.splitlines()
    assert len(subjects) > 100 and not [s for s in set(subjects) if len(s) > 12 and s in text]


def test_second_call_is_served_from_the_cache(client):
    a = client.get("/git/habits").json()
    b = client.get("/git/habits").json()
    assert a == b


def test_service_clear_caches_and_defaults(service_env):
    assert service.resolve(None, None).person == service.DEFAULT_PERSON
