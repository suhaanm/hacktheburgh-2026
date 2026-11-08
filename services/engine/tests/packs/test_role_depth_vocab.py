"""RD (7 Nov 2026): the closed vocabularies other layers keep (Cue, Insights, Evidence, the hit list) name everything the deeper role packs added, so
no sentence, chip or table falls back to a clipped label or a made-up phrase. Extend-only: nothing that existed is checked for change here."""
from __future__ import annotations

import pytest
import yaml

from understudy_engine.cue import vocab as CV
from understudy_engine.evidence import vocab as EV
from understudy_engine.hitlist import vocab as HV
from understudy_engine.insights import vocab as IV
from understudy_engine.packs import load_pack
from understudy_engine.packs.loader import packs_dir

ROLES = ("programmer", "data-analyst")


def doc(role: str, name: str) -> dict:
    return yaml.safe_load((packs_dir() / role / name).read_text())


@pytest.mark.parametrize("role", ROLES)
def test_every_new_skill_has_the_same_noun_phrase_in_the_pack_cue_and_insights(role):
    for s in doc(role, "curriculum.yaml")["skills"]:
        if "name" not in s:
            continue
        assert IV.SKILL_PHRASE[s["id"]] == s["name"], s["id"]                        # the insights sentence uses the phrase the curriculum gives
        assert CV.skill_info(role, s["id"])["name"] == s["name"], s["id"]            # and so does Cue
        assert IV.skill_phrase(s["id"]) == s["name"]


@pytest.mark.parametrize("role", ROLES)
def test_every_new_step_has_a_hand_written_short_label_and_its_own_reason(role):
    v = CV.get_vocab(role)
    assert v is not None
    new_steps = [c["id"] for c in doc(role, "expert_steps.yaml")["checks"] if "family" in c]
    assert len(new_steps) >= 11
    reasons_used = set()
    for sid in new_steps:
        label = CV.SHORT_LABELS[role][sid]
        assert label == v.label(sid) and 0 < len(label) <= CV.LABEL_MAX
        rid = CV.STEP_REASON[role][sid]
        assert rid != "why.generic" and len(CV.REASONS[rid].split()) <= CV.REASON_WORDS, sid
        reasons_used.add(rid)
    assert len(reasons_used) == len(new_steps)                                          # one reason per step, none shared with another new step


@pytest.mark.parametrize("role", ROLES)
def test_every_new_routine_template_is_a_known_evidence_kind_with_a_name_and_a_hit_list_style(role):
    for t in doc(role, "routines.yaml")["templates"]:
        assert t["id"] in EV.ROUTINE_KINDS and t["id"] in EV.ROUTINE_NAME, t["id"]
        if "steps" in t:                                                                # a role-depth template
            key, family = HV.TEMPLATE_STYLE[t["id"]]
            assert key.lower() in t["title"].lower() and family in HV.FAMILIES, t["id"]


@pytest.mark.parametrize("role", ROLES)
def test_every_new_cog_is_a_known_evidence_cog_with_a_display_name(role):
    pack = load_pack(role)
    for cog in pack.extra_cogs[10:]:
        assert cog in EV.COG_IDS and cog in EV.COG_NAME, cog


def test_an_evidence_packet_may_name_a_new_cog_and_is_just_as_valid_without_one():
    """No data for a cog means the key is absent from the packet (the screens say "not enough data"), never a zero."""
    from understudy_engine.evidence import packet as P

    meta = {"origin": "synthetic", "n": 1, "n_unit": "people", "split": "none"}
    empty = P.EvidencePacket.model_validate({"meta": meta})
    assert not empty.cogs
    for role in ROLES:
        for cog in load_pack(role).extra_cogs[10:]:
            pk = P.EvidencePacket.model_validate({"meta": meta, "cogs": {cog: {"seconds": 3.0}}})
            assert f"cog.{cog}.seconds" in P.facts(pk).facts


def test_the_hit_lists_risk_words_do_not_misread_a_new_cog_as_irreversible_or_outward():
    """The hit list holds a routine back when its FIRST step looks irreversible or outward (from the cog's own words). A new cog whose name carries
    a risk word would hold back a harmless routine, so the ids were chosen without MESSAGE, DEPLOY, ISSUE, EXPORT and the like."""
    for role in ROLES:
        for cog in load_pack(role).extra_cogs[10:]:
            assert HV.step_risk(cog) is None, (role, cog, HV.step_risk(cog))
