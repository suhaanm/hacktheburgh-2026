"""No sentence a person can see or hear says that data is an example (owner request of 8 Nov 2026, 05:00).

The engine's words reach cards, notes under charts, the memory file, packets and error messages. They say what is true in plain words
("This profile has no recorded days yet.") and never name how the data was made. Two checks:

* the display strings of the modules that were reworded are scanned as source (docstrings and comments are not text; a bare enum such as
  origin "synthetic" is code, and is not matched because only phrases are listed);
* the functions that build the sentences are called and their output is read.

What stays on purpose, because it states how an evaluation result was obtained: the Evidence page text (evals/report.*, the limitation vocabulary in
evidence/vocab.py, the eval modules). They are not scanned here.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "understudy_engine"

# Phrases only: single words such as "synthetic" or "planted" are data enums and python names in this code base.
BANNED = re.compile(
    r"example data|sample data|example week|example calendar|example connection|stand-in|stands in|built-in sample|for this build|not real (?:workers|people)|"
    r"nobody is real|generated (?:data|people|learners?|calendars?|traces|persona|personas)\b|planted (?:structure|deficits?|habits?|routines?)|planted-habit|"
    r"scripted (?:apprentices|developers)|invented|made-up|made up",
    re.I,
)

# The modules whose sentences reach a worker or an admin screen, a card, the memory file or a message. Each had banned wording before 8 Nov 05:00.
DISPLAY_MODULES = [
    "connections/manifest.py",
    "connections/routes.py",
    "connections/state.py",
    "insights/routes.py",
    "insights/service.py",
    "proactive/candidates.py",
    "proactive/prepare.py",
    "proactive/seed.py",
    "cue/live.py",
    "cue/score.py",
    "awareness/routes.py",
    "calendar/service.py",
    "routes_calendar.py",
    "routes_coach.py",
    "routes_handoff.py",
    "routes_analytics.py",
    "genome/service.py",
    "gitanalysis/service.py",
]


def _strings(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                docs.add(id(body[0].value))
    return [(n.lineno, n.value) for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def test_the_scanner_finds_a_sentence_and_leaves_enums_alone():
    assert BANNED.search("An example week stands in for this profile.")
    assert BANNED.search("Example data: invented and kept on this Mac.")
    assert BANNED.search("Planted-habit data: every learner here is scripted.")
    for ok in ("synthetic", "planted", "This profile has no recorded days yet.", "Runs on this Mac.", "Models are off"):
        assert not BANNED.search(ok), ok


@pytest.mark.parametrize("rel", DISPLAY_MODULES)
def test_display_modules_say_nothing_about_example_data(rel: str):
    bad = [f"{rel}:{line}  {text[:100]!r}" for line, text in _strings(ENGINE / rel) if BANNED.search(text)]
    assert bad == []


def test_the_connection_consent_lines_say_what_is_true_without_the_vocabulary():
    from understudy_engine.connections import registry
    from understudy_engine.connections.manifest import consent

    presets = registry.all_presets()
    assert presets
    for pid, preset in presets.items():
        out = consent(preset, "example")
        text = " ".join([out["summary"], *out["lines"]])
        assert not BANNED.search(text), (pid, text)
        assert "No account is used" in out["summary"] and "nothing leaves this Mac" in out["summary"], pid


def test_the_calendar_notes_and_the_memory_line_are_plain():
    from understudy_engine.calendar.service import suggestions_meta, week_meta
    from understudy_engine.cue.live import NOTE
    from understudy_engine.cue.score import caveat_text, summary_line
    from understudy_engine.insights.routes import STAND_IN_NOTE

    cohort = {"expert": {"source": "cohort", "n_experts": 8}, "features": {"days_worked": 5}}
    template = {"expert": {"source": "template", "n_experts": 0}, "features": {"days_worked": 5}}
    texts = [week_meta(cohort)["note"], week_meta(template)["note"], suggestions_meta({"n_weeks": 4, "reworded": True})["note"],
             suggestions_meta({"n_weeks": 4, "reworded": False})["note"], NOTE, STAND_IN_NOTE, caveat_text(),
             summary_line([])]
    for t in texts:
        assert isinstance(t, str) and t and not BANNED.search(t), t
    assert STAND_IN_NOTE == "This profile has no recorded days yet."
