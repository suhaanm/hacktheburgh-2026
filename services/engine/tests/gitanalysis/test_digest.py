from __future__ import annotations

import types

import pytest

from understudy_engine.gitanalysis import digest as dg
from understudy_engine.gitanalysis.vocab import CATEGORIES, MESSAGE_QUALITY, RISKS, SIZE_BUCKETS, size_bucket, valid_digest


def fields(subject="Add retry logic to billing", files=(("src/billing/core.py", 20, 3),), parents=1, body=""):
    return {"sha": "x", "author": "a@example.test", "message": subject + ("\n\n" + body if body else ""), "paths": [p for p, _, _ in files],
            "n_files": len(files), "additions": sum(a for _, a, _ in files), "deletions": sum(d for _, _, d in files),
            "test_files": 0, "is_revert": subject.lower().startswith("revert"), "is_merge": parents > 1, "tz_min": 0}


@pytest.mark.parametrize("lines,bucket", [(0, "tiny"), (10, "tiny"), (11, "small"), (50, "small"), (51, "medium"), (250, "medium"), (251, "large"), (1000, "large"), (1001, "huge")])
def test_size_buckets_match_the_localmodel_track(lines, bucket):
    from understudy_engine.localmodel.schemas import size_bucket as theirs
    assert size_bucket(lines) == bucket == theirs(lines)


def test_vocabularies_match_the_localmodel_track():
    from understudy_engine.localmodel import schemas as s
    assert CATEGORIES == s.COMMIT_CATEGORIES and SIZE_BUCKETS == s.SIZE_BUCKETS and RISKS == s.RISKS and MESSAGE_QUALITY == s.MESSAGE_QUALITIES


# ---- the localmodel track is the digest source
def test_digests_come_from_the_localmodel_track():
    ds, info = dg.commit_digests([fields(), fields("update", files=[("src/a.py", 3, 0)])])
    assert info.impl == "localmodel" and info.source == "rules" and info.label == "rules"       # UNDERSTUDY_MOCK=1: never the model
    assert all(valid_digest(d) for d in ds) and ds[1]["message_quality"] == "vague"


def test_item_handed_over_has_the_expected_shape_and_agrees_with_our_numbers():
    from understudy_engine.localmodel.schemas import normalise_commit
    f = fields("Fix crash on empty file", files=[("src/a.py", 200, 60), ("tests/test_a.py", 30, 0)], body="Because it crashed.")
    item = dg.localmodel_item(f)
    c = normalise_commit(item)
    assert c.additions == 230 + 0 and c.deletions == 60 and c.files_changed == 2 and c.paths == ("src/a.py", "tests/test_a.py")
    d = dg.commit_digests([f])[0][0]
    assert d["size_bucket"] == size_bucket(290) == "large" and d["touches_tests"] is True and d["category"] == "fix"


def test_builtin_fallback_only_when_import_fails(monkeypatch):
    monkeypatch.setattr(dg, "_localmodel", lambda: None)
    ds, info = dg.commit_digests([fields()])
    assert info.impl == "builtin" and info.source == "rules" and valid_digest(ds[0])
    with pytest.raises(RuntimeError):
        dg.commit_digests([fields()], backend="model")


def test_builtin_backend_is_explicit():
    assert dg.commit_digests([fields()], backend="builtin")[1].impl == "builtin"


def fake_lm(digests, sources=None, fallbacks=None, boom=False):
    def commit_digest_ex(items, *, force_rules=False, client=None):
        if boom:
            raise RuntimeError("model said secret-subject-text")
        return types.SimpleNamespace(digests=digests, per_item_source=sources or ["model"] * len(digests), fallbacks=fallbacks or {})
    return types.SimpleNamespace(commit_digest_ex=commit_digest_ex)


OK = {"category": "fix", "size_bucket": "tiny", "touches_tests": False, "risk": "low", "message_quality": "clear", "extra": "dropped"}


def test_model_digests_are_used_cleaned_and_counted(monkeypatch):
    monkeypatch.setattr(dg, "_localmodel", lambda: fake_lm([OK, OK], ["model", "rules"], {"guard:x": 1}))
    ds, info = dg.commit_digests([fields(), fields()])
    assert info.source == "mixed" and info.label == "model" and info.model_share == 0.5 and info.fallbacks == 1
    assert "extra" not in ds[0] and ds[0]["category"] == "fix"
    monkeypatch.setattr(dg, "_localmodel", lambda: fake_lm([OK]))
    assert dg.commit_digests([fields()])[1].source == "model"


def test_invalid_model_digests_are_replaced_by_builtin(monkeypatch):
    bad = dict(OK, category="banana")
    monkeypatch.setattr(dg, "_localmodel", lambda: fake_lm([bad, OK]))
    ds, info = dg.commit_digests([fields(), fields("Fix crash on empty file")])
    assert info.fallbacks == 1 and ds[0]["category"] == "feature" and ds[1]["category"] == "fix" and all(valid_digest(d) for d in ds)


def test_exception_or_wrong_length_falls_back_without_logging_text(monkeypatch, caplog):
    monkeypatch.setattr(dg, "_localmodel", lambda: fake_lm([], boom=True))
    ds, info = dg.commit_digests([fields()])
    assert info.impl == "builtin" and "secret-subject-text" not in caplog.text
    monkeypatch.setattr(dg, "_localmodel", lambda: fake_lm([]))
    assert dg.commit_digests([fields()])[1].impl == "builtin"


def test_backend_model_requires_the_model(monkeypatch):
    with pytest.raises(RuntimeError):
        dg.commit_digests([fields()], backend="model")             # rules path: the model produced none
    monkeypatch.setattr(dg, "_localmodel", lambda: fake_lm([OK]))
    assert dg.commit_digests([fields()], backend="model")[1].source == "model"


# ---- the built-in fallback keeps its own tests
@pytest.mark.parametrize("subject,quality", [
    ("", "vague"), ("update", "vague"), ("wip", "vague"), ("fix stuff", "vague"), (".", "vague"), ("asdf", "vague"), ("ok now", "vague"),
    ("Fix off-by-one in pagination", "ok"), ("Add retry logic to billing", "clear"), ("Bump pytest to 8.3", "ok"),
    ("Fix the crash on empty input in the importer", "clear"),
])
def test_builtin_message_quality(subject, quality):
    assert dg.message_quality(subject) == quality


@pytest.mark.parametrize("subject,paths,cat", [
    ('Revert "Add thing"', ["src/a.py"], "revert"), ("anything", ["tests/test_a.py", "tests/b/test_c.py"], "test"),
    ("anything", ["README.md", "docs/x.md"], "docs"), ("anything", ["pyproject.toml", ".github/workflows/ci.yml"], "chore"),
    ("Fix crash on empty file", ["src/a.py"], "fix"), ("Refactor billing core", ["src/a.py", "src/b.py"], "refactor"),
    ("Add pagination to search", ["src/a.py"], "feature"), ("Make it nicer", ["src/a.py"], "other"),
])
def test_builtin_categories(subject, paths, cat):
    assert dg.rules_commit_digest(fields(subject, files=[(p, 5, 1) for p in paths]))["category"] == cat


@pytest.mark.parametrize("path,is_test", [
    ("tests/test_a.py", True), ("src/pkg/tests/x.py", True), ("src/a_test.go", True), ("web/app.test.ts", True), ("web/app.spec.js", True),
    ("src/Foo.java", False), ("src/FooTest.java", True), ("src/contest.py", False), ("src/latest.py", False)])
def test_builtin_test_paths(path, is_test):
    assert dg.is_test_path(path) is is_test


def test_digests_contain_no_text():
    secret = "AcmeCorpZQ91 invoice for jane.doe@example.org"
    f = fields(subject=f"Fix {secret}", body=secret, files=[(f"src/{secret}.py", 5, 5)])
    for ds in (dg.commit_digests([f])[0], dg.commit_digests([f], backend="builtin")[0]):
        assert secret.lower() not in repr(ds).lower()
        assert all(isinstance(v, bool) or v in CATEGORIES + SIZE_BUCKETS + RISKS + MESSAGE_QUALITY for v in ds[0].values())
