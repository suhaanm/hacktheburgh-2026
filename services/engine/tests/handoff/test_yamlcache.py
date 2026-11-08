"""YAML files are parsed once per version of the file, and every caller gets its own copy; a cached read equals an uncached one.

Also pins the other caches added for the page-load cost (genome: no cohort is remembered per file version; the ledger's hour parse; the presence interval).
"""
from __future__ import annotations

import os

import pytest
import yaml

from understudy_engine import yamlcache
from understudy_engine.yamlcache import load_yaml_file


def test_cached_read_equals_a_plain_parse_and_parses_once(tmp_path):
    p = tmp_path / "pack.yaml"
    p.write_text("id: x\nlist: [1, 2, {a: b}]\nwhen: 2026-11-08\nnested:\n  k: [a, b]\n", encoding="utf-8")
    plain = yaml.safe_load(p.read_text(encoding="utf-8"))
    yamlcache.clear()
    before = dict(yamlcache.stats)
    first, second = load_yaml_file(p), load_yaml_file(p)
    assert first == plain == second
    assert yamlcache.stats["parses"] - before["parses"] == 1 and yamlcache.stats["hits"] - before["hits"] == 1


def test_each_caller_gets_its_own_copy(tmp_path):
    p = tmp_path / "a.yaml"
    p.write_text("items: [1, 2]\nm: {k: v}\n", encoding="utf-8")
    a = load_yaml_file(p)
    a["items"].append(99)
    a["m"]["k"] = "changed"
    b = load_yaml_file(p)
    assert b == {"items": [1, 2], "m": {"k": "v"}}


def test_the_cache_refreshes_when_the_file_changes(tmp_path):
    p = tmp_path / "b.yaml"
    p.write_text("v: 1\n", encoding="utf-8")
    assert load_yaml_file(p) == {"v": 1}
    p.write_text("v: 22\n", encoding="utf-8")                  # another size
    assert load_yaml_file(p) == {"v": 22}
    p.write_text("v: 33\n", encoding="utf-8")                  # the same size, another mtime
    os.utime(p, ns=(1, p.stat().st_mtime_ns + 5_000_000))
    assert load_yaml_file(p) == {"v": 33}


def test_errors_are_what_the_plain_call_raises_and_a_bad_file_is_not_remembered(tmp_path):
    with pytest.raises(OSError):
        load_yaml_file(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [1, 2\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_yaml_file(bad)
    with pytest.raises(yaml.YAMLError):
        load_yaml_file(bad)
    bad.write_text("a: [1, 2]\n", encoding="utf-8")
    assert load_yaml_file(bad) == {"a": [1, 2]}


def test_role_packs_load_the_same_with_and_without_the_cache():
    from understudy_engine.memory import list_pack_ids, load_pack
    from understudy_engine.packs.loader import load_pack as load_full_pack

    for rid in list_pack_ids():
        yamlcache.clear()
        cold = load_pack(rid)
        warm = load_pack(rid)
        assert cold == warm
        full_cold = load_full_pack(rid)
        assert full_cold.id == load_full_pack(rid).id == rid


def test_the_connection_registry_reads_the_same_with_the_cache():
    from understudy_engine.connections import registry

    yamlcache.clear()
    cold = registry.role_lists()
    assert registry.role_lists() == cold and cold


def test_hour_to_epoch_is_remembered_and_exact():
    from datetime import datetime, timezone

    from understudy_engine.cue.ledger import hour_to_epoch

    h = "2026-11-08T05"
    assert hour_to_epoch(h) == datetime(2026, 11, 8, 5, tzinfo=timezone.utc).timestamp()
    before = hour_to_epoch.cache_info().hits
    hour_to_epoch(h)
    assert hour_to_epoch.cache_info().hits == before + 1


def test_genome_remembers_that_a_file_version_had_no_cohort(tmp_path):
    from understudy_engine.genome import GenomeError, GenomeService
    from understudy_engine.store import EventStore

    svc = GenomeService(EventStore(tmp_path))
    loads: list[str] = []
    real_load = svc._load

    def counting(part):
        loads.append(part)
        return real_load(part)

    svc._load = counting                                          # type: ignore[method-assign]
    for _ in range(3):
        with pytest.raises(GenomeError):
            svc.bundle("t_entitlement_check")
    assert loads == ["real", "synthetic"]                          # asked once per partition, not on every request
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "roster.json").write_text("{}")           # the files changed: look again
    with pytest.raises(GenomeError):
        svc.bundle("t_entitlement_check")
    assert loads.count("real") == 2
