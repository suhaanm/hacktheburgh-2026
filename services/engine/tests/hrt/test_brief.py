"""The HRT brief is rendered from the reports: no number typed by hand, every "beats" and "loses" backed by an inequality, and the committed text current."""
from __future__ import annotations

import importlib.util
import re

import pytest

from understudy_engine.store.paths import repo_root

ROOT = repo_root()
SCRIPT = ROOT / "scripts" / "hrt_brief.py"


@pytest.fixture(scope="module")
def hb():
    spec = importlib.util.spec_from_file_location("hrt_brief", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_placeholder_and_assertion_resolves_against_the_reports(hb):
    text, bad = hb.build()
    assert not bad, "unresolved or false assertions in docs/hrt/HRT_BRIEF.tmpl.md:\n  " + "\n  ".join(bad)
    assert "[[UNRESOLVED" not in text and "{{" not in text


def test_the_committed_brief_equals_a_fresh_render(hb):
    text, bad = hb.build()
    assert not bad
    have = hb.OUT.read_text(encoding="utf-8") if hb.OUT.exists() else ""
    assert have == text, "docs/HRT_BRIEF.md is out of date: a report under evals/ changed. Run `python3 scripts/hrt_brief.py` and commit the result."


def test_the_brief_says_what_it_must_and_avoids_what_it_must_not(hb):
    text, _ = hb.build()
    assert "synthetic" in text.lower() and "live study" in text and "n = 4" in text
    assert not re.search(r"\bdemo\b", text, re.I), "the word 'demo' is not used in anything an owner might paste"
    for section in ("## 1. In thirty seconds", "## 2. What a prediction-and-decision judge asks", "## 2b. The registered claims, as run", "## 3. What a quant judge will attack",
                    "## 4. Decisions", "## 5. The dumbest competent baseline", "## 6. Gap analysis", "## 7. Reproduce"):
        assert section in text, section
    for attack in ("Leakage.", "Generator dependence.", "Small n.", "Multiple comparisons.", "Simulated data.", "Calibration under shift.", "Decision value against prediction accuracy."):
        assert attack in text, attack


def test_the_number_of_generated_values_is_large_and_the_prose_has_no_loose_decimals(hb):
    """Every decimal result in the prose comes from a placeholder. Constants of the design (0.05, 0.02, 0.01, the 30% budget, L/G = 9, b = 8) are allowed;
    anything else that looks like a measured result is a hand-typed number and fails."""
    tmpl = hb.TEMPLATE.read_text(encoding="utf-8")
    assert len(hb.PLACEHOLDER.findall(tmpl)) > 200
    stripped = hb.PLACEHOLDER.sub("", tmpl)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.S)
    stripped = re.sub(r"`[^`]*`", "", stripped)
    stripped = re.sub(r"## 6\. Gap analysis.*?## 7\. Reproduce", "", stripped, flags=re.S)       # impact and hours there are our estimates, labelled as such
    allowed = {"0.05", "0.02", "0.01", "0.95", "0.0", "1.0", "0.3", "0.2", "0.1", "0.5", "0.8", "0.4", "0.7", "0.6", "0.9", "98.75"}
    loose = [m.group(0) for m in re.finditer(r"(?<![\w.])\d+\.\d+(?![\w.])", stripped) if m.group(0) not in allowed]
    assert not loose, f"hand-typed decimals in the brief's template: {sorted(set(loose))}"
