from __future__ import annotations

import shutil

import pytest
import yaml

from understudy_engine.cli import main
from understudy_engine.cogs import DEFAULT_MAPPING_PATH, Mapping
from understudy_engine.packs import PackError, list_packs, load_all, load_pack, packs_dir, validate_all, validate_pack

PACK_IDS = {"benefits-processor", "data-analyst", "programmer"}


def test_three_packs_listed_with_depth():
    rows = {r["id"]: r for r in list_packs()}
    assert set(rows) >= PACK_IDS
    assert rows["benefits-processor"]["depth"] == "deep"
    assert rows["data-analyst"]["depth"] == rows["programmer"]["depth"] == "thin"
    for r in rows.values():
        assert set(r) == {"id", "name", "summary", "depth"} and r["name"] and r["summary"]


def test_all_real_packs_validate():
    results = validate_all()
    assert set(results) >= PACK_IDS
    assert {k: v for k, v in results.items() if v} == {}


def test_loader_reads_pack_pieces():
    p = load_pack("benefits-processor")
    assert p.depth == "deep" and "CHECK_CLIFF" in p.extra_cogs
    assert [q["id"] for q in p.questions()] == ["tools", "risky", "tone", "pace", "hours"]
    assert "submit" in p.risk_classes()["irreversible"]
    assert p.tone_defaults()["length"] == "short"
    assert p.plugin_refs == []
    assert isinstance(p.cog_mapping(), Mapping)
    assert p.sensitive_fields()["patterns"]
    assert p.file("routines") and p.file("curriculum")
    # packs differ visibly (the whole point of the thin ones)
    a, b = load_pack("data-analyst"), load_pack("programmer")
    assert a.extra_cogs != b.extra_cogs != p.extra_cogs
    assert [q["prompt"] for q in a.questions()] != [q["prompt"] for q in b.questions()]
    assert len(load_all()) >= 3


def test_unknown_pack_error_is_specific():
    with pytest.raises(PackError) as e:
        load_pack("sales")
    assert e.value.code == "unknown_pack" and "benefits-processor" in e.value.message and e.value.status == 404


@pytest.fixture()
def copy_pack(tmp_path):
    n = [0]

    def make(src="data-analyst", name="data-analyst"):
        n[0] += 1
        dst = tmp_path / f"copy{n[0]}" / name
        shutil.copytree(packs_dir() / src, dst)
        return dst
    return make


def test_broken_packs_give_plain_errors(copy_pack):
    d = copy_pack()
    assert validate_pack(d) == []
    # 1. id must equal the directory
    d2 = copy_pack(name="renamed")
    errs = validate_pack(d2)
    assert any("must equal the directory name" in e for e in errs)
    # 2. a referenced file is missing
    d3 = copy_pack()
    (d3 / "routines.yaml").unlink()
    assert any("routines.yaml" in e and "missing" in e for e in validate_pack(d3))
    # 3. a schema violation in pack.yaml (only four onboarding questions)
    d4 = copy_pack()
    doc = yaml.safe_load((d4 / "pack.yaml").read_text())
    doc["onboarding"]["questions"] = doc["onboarding"]["questions"][:4]
    (d4 / "pack.yaml").write_text(yaml.safe_dump(doc))
    errs = validate_pack(d4)
    assert errs and all(e.startswith("data-analyst/pack.yaml") for e in errs)
    # 4. a sub-file that does not parse
    d5 = copy_pack()
    (d5 / "curriculum.yaml").write_text("a: [unclosed\n")
    assert any("does not parse" in e for e in validate_pack(d5))
    # 5. no pack.yaml at all
    empty = d.parent.parent / "empty"
    empty.mkdir()
    assert validate_pack(empty) == ["empty: pack.yaml is missing"]


def test_plugin_refs_are_accepted_but_inert(copy_pack):
    d = copy_pack()
    doc = yaml.safe_load((d / "pack.yaml").read_text())
    ref = {"id": "anthropics/knowledge-work-plugins:sql-queries", "kind": "skill", "as": "procedure", "license": "Apache-2.0", "enabled": False}
    doc["plugin_refs"] = [ref]
    (d / "pack.yaml").write_text(yaml.safe_dump(doc))
    assert validate_pack(d, extended=False) == []   # the schema accepts a sample reference
    from understudy_engine.packs.loader import Pack

    assert Pack(d, doc).plugin_refs == [ref]


def test_mapping_in_engine_format_is_used_and_other_formats_fall_back(copy_pack):
    d = copy_pack()
    shutil.copy(DEFAULT_MAPPING_PATH, d / "mapping.yaml")
    from understudy_engine.packs.loader import Pack

    p = Pack(d, yaml.safe_load((d / "pack.yaml").read_text()))
    m = p.cog_mapping()
    assert isinstance(m, Mapping) and not p.warnings
    (d / "mapping.yaml").write_text("version: 1\nrole_rules: []\nbase_rules: []\n")
    p2 = Pack(d, yaml.safe_load((d / "pack.yaml").read_text()))
    assert isinstance(p2.cog_mapping(), Mapping) and p2.warnings and "default mapping" in p2.warnings[0]


def test_cli_pack_validate_exit_codes(copy_pack, capsys):
    good = copy_pack()
    assert main(["pack", "validate", str(good)]) == 0
    assert "ok    pack data-analyst" in capsys.readouterr().out
    (good / "persona.yaml").unlink()
    assert main(["pack", "validate", str(good)]) == 1
    out = capsys.readouterr().out
    assert "FAIL  pack data-analyst" in out and "persona.yaml" in out
    assert main(["pack", "validate"]) == 0          # every real pack
