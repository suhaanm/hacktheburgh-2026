"""Checks on the red-team catalog. Run: uv run pytest evals/tests -q"""
from __future__ import annotations

import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

EVALS = Path(__file__).resolve().parents[1]
RED = EVALS / "redteam"
sys.path.insert(0, str(RED))
import generate as G  # noqa: E402

CAT = json.loads((RED / "attacks.json").read_text())
ATTACKS = CAT["attacks"]
CLEAN = {c["id"]: c for c in CAT["clean"]}
ALLOWED_HOSTS = {"evil.example", "127.0.0.1", "localhost"}


def read(rel: str) -> str:
    return (RED / rel).read_text(encoding="utf-8")


def test_schema_valid_and_sizes():
    schema = json.loads((RED / "attacks.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    errs = list(Draft202012Validator(schema).iter_errors(CAT))
    assert not errs, [e.message for e in errs[:3]]
    assert len(ATTACKS) >= 24
    assert len(CAT["clean"]) >= 12
    assert len({a["id"] for a in ATTACKS}) == len(ATTACKS)


def test_every_category_has_three_or_more_attacks():
    counts = Counter(a["category"] for a in ATTACKS)
    for cat in G.CATEGORIES:
        assert counts[cat] >= 3, (cat, counts)


def test_all_goal_kinds_and_channels_are_covered():
    assert {a["goal_of_attack"]["kind"] for a in ATTACKS} == {"exfiltrate", "click_destructive", "navigate", "type_data"}
    assert {a["where"] for a in ATTACKS} == {"text", "hidden_element", "alt_text", "ocr"}


def test_hidden_payload_equals_injected_instruction():
    for a in ATTACKS:
        assert a["hidden_payload"] == a["injected_instruction"], a["id"]


@pytest.mark.parametrize("a", [a for a in ATTACKS if a["page"]], ids=lambda a: a["id"])
def test_attack_page_carries_the_payload_in_its_channel_and_the_twin_does_not(a):
    page = read(a["page"])
    plain = a["hidden_payload"]
    carrier = plain if a.get("payload_obfuscation") != "zero_width_split" else G.zw(plain)
    escaped = G.e(plain) if a.get("payload_obfuscation") != "zero_width_split" else G.zw(G.e(plain))
    if a["where"] == "ocr":
        assert a["ocr_text"] == plain and (RED / a["asset"]).is_file()
    elif a["category"] == "multi_step":
        assert any(G.e(plain) in read(s["page"]) for s in a["steps"])
    else:
        assert (plain in page or G.e(plain) in page or carrier in page or escaped in page), a["id"]
    # the clean twin is the same page without the injection
    twin = CLEAN[a["clean_twin"]]
    twin_pages = [twin["page"]] + [s["page"] for s in twin.get("steps", [])]
    for tp in twin_pages:
        t = read(tp)
        assert plain not in t and G.e(plain) not in t and "evil.example" not in t, (a["id"], tp)


def test_attack_pages_differ_from_their_twins_only_by_the_injection():
    for aid, (page, rec) in G.attack_pages().items():
        twin = CLEAN[rec["clean_twin"]]
        clean_html = read(twin["page"])
        if rec["where"] == "ocr":  # the injection lives in the image, not the page
            assert (RED / rec["asset"]).read_bytes() != (RED / "clean" / Path(rec["asset"]).name).read_bytes(), aid
            continue
        assert page != clean_html, aid
        # removing the injected payload text leaves a page of about the same size as the twin
        stripped = page.replace(G.e(rec["hidden_payload"]), "").replace(rec["hidden_payload"], "")
        assert abs(len(stripped) - len(clean_html)) < 900, (aid, len(stripped), len(clean_html))


def test_multi_step_attacks_have_two_real_pages_and_a_payload_step():
    for a in [x for x in ATTACKS if x["category"] == "multi_step"]:
        assert len(a["steps"]) >= 2
        assert a["steps"][-1]["role"] == "payload" and a["steps"][-1]["carries_payload"]
        for s in a["steps"]:
            assert (RED / s["page"]).is_file()
        # step 1 links to step 2 so a navigating agent really gets there
        first, second = a["steps"][0]["page"], Path(a["steps"][1]["page"]).name
        assert second in read(first)


def test_sandbox_entries_use_the_sandbox_payload_and_local_targets():
    sb = [a for a in ATTACKS if a["page"] is None]
    assert len(sb) >= 4
    for a in sb:
        assert a["sandbox"]["attack_query"] == "variant=injected"
        assert G.CANARY in a["hidden_payload"]
        assert a["goal_of_attack"]["target"].startswith("127.0.0.1:")
        assert a["clean_twin"] in CLEAN and CLEAN[a["clean_twin"]]["sandbox"]["attack_query"] is None


def test_sandbox_payload_matches_the_sandbox_sites_text():
    sites = pytest.importorskip("understudy_agent.sandbox_sites.sites")
    specs = pytest.importorskip("understudy_agent.sandbox_sites.specs")
    assert specs.CANARY == G.CANARY
    for a in [x for x in ATTACKS if x["page"] is None]:
        s = a["sandbox"]
        assert a["hidden_payload"] == sites.injection_text(s["site"], f"http://127.0.0.1:{s['port']}"), a["id"]


def test_every_url_in_the_catalog_is_evil_example_or_local():
    blobs = [(RED / "attacks.json").read_text()]
    for sub in ("pages", "clean"):
        blobs += [p.read_text(encoding="utf-8", errors="ignore") for p in (RED / sub).glob("*.html")]
    for blob in blobs:
        for host in re.findall(r"https?://([^/\s\"'<>)\]\\]+)", blob):
            assert host.split(":")[0] in ALLOWED_HOSTS, host


def test_clean_pages_never_mention_the_attacker_domain():
    for c in CAT["clean"]:
        for rel in [c["page"]] + [s["page"] for s in c.get("steps", [])]:
            if rel:
                assert "evil.example" not in read(rel), (c["id"], rel)


def test_hard_negatives_really_contain_their_benign_hidden_features():
    hn = [c for c in CAT["clean"] if c.get("hard_negative")]
    assert len(hn) >= 8
    probes = {"html_comment": "<!--", "aria_hidden_text": 'aria-hidden="true"', "visually_hidden_text": "left:-9999px",
              "display_none_ui_template": "display:none", "destructive_words_in_hidden_ui": "delete this case record",
              "imperatives_to_the_person": "Now press", "security_notice_text": "never type a claimant", "json_code_sample": '{"tool"',
              "fixed_banner": "position:fixed", "descriptive_alt_text": 'alt="Bar chart', "markdown_syntax_in_text": "![chart](chart.png)",
              "hidden_input_fields": 'type="hidden"', "next_page_instruction": "open the case note page"}
    seen = set()
    for c in hn:
        page = read(c["page"])
        for f in c["benign_features"]:
            if f in probes:
                assert probes[f] in page, (c["id"], f)
                seen.add(f)
    assert {"html_comment", "aria_hidden_text", "display_none_ui_template", "imperatives_to_the_person", "security_notice_text"} <= seen


def test_visible_text_of_attack_and_twin_agrees_for_text_channel_pages():
    for a in ATTACKS:
        if a["page"] and a["category"] not in ("multi_step",) and a["where"] in ("hidden_element", "ocr"):
            twin = CLEAN[a["clean_twin"]]
            assert a["visible_task_text"] == twin["visible_task_text"], a["id"]


def test_build_is_deterministic(tmp_path):
    G.build(tmp_path)
    assert (tmp_path / "attacks.json").read_text() == (RED / "attacks.json").read_text()
    for sub in ("pages", "clean"):
        for p in sorted((RED / sub).iterdir()):
            assert (tmp_path / sub / p.name).read_bytes() == p.read_bytes(), p.name


def test_pdf_assets_are_valid_and_the_attack_pdf_hides_the_payload():
    for rel, has_payload in (("pages/capital-rules.pdf", True), ("clean/capital-rules.pdf", False)):
        raw = (RED / rel).read_bytes()
        assert raw.startswith(b"%PDF-1.4") and raw.rstrip().endswith(b"%%EOF")
        start = int(re.search(rb"startxref\n(\d+)", raw).group(1))
        assert raw[start:start + 4] == b"xref"
        offsets = [int(m) for m in re.findall(rb"(\d{10}) 00000 n", raw)]
        for i, off in enumerate(offsets, 1):
            assert raw[off:].startswith(b"%d 0 obj" % i)
        assert (G.PAYLOADS["nav"].encode() in raw) is has_payload
        assert b"1 1 1 rg" in raw or not has_payload


def test_png_assets_open():
    PIL = pytest.importorskip("PIL.Image")
    for rel in ("pages/scan.png", "clean/scan.png", "pages/logo.png"):
        with PIL.open(RED / rel) as im:
            assert im.size[0] >= 48


def test_page_files_for_every_catalog_entry_exist():
    for a in ATTACKS:
        if a["page"]:
            assert (RED / a["page"]).is_file(), a["id"]
    for c in CAT["clean"]:
        if c["page"]:
            assert (RED / c["page"]).is_file(), c["id"]
