"""The report's wording rule (owner decision D57, 8 Nov 2026): the words "synthetic" and "simulated" are not in anything a person reads.

The sections' own sources (research generators, frozen result files) still say them, so the rule is applied when the report is ASSEMBLED, to the text of the
whole report tree, and again whenever it is rendered or written. Every regeneration therefore emits the app's wording, deterministically, with no list of
strings to keep in step. It is idempotent: wording that already follows the rule comes back unchanged.

What it touches: string VALUES that contain whitespace (prose) and one of the two words. What it never touches: keys, identifiers and enums (``origin:
"synthetic"``, ``ana-synthetic-origin``, ``simulated_participants``: no whitespace), paths (``data/synthetic``), and quoted enum values inside a sentence.
Where a sentence needs its provenance to stay true it says it concretely ("generators we wrote", "language-model participants, not people", "scripted
apprentices", "a stand-in actuator") and the last resort is "generated".
"""
from __future__ import annotations

import re
from typing import Any

BANNED = re.compile(r"\b(synthetic|synthetically|simulated)\b", re.I)

# The same pass also keeps two other things out of the report's prose that the sections' frozen result files bring back on every regeneration and that the
# dashboard's copy lint refuses: the old product name (capital U, prose only: `understudy synth --all` and understudy_engine are commands and modules) and the
# banned word "simply" (docs/knack-ux/banned-phrases.json).
_OTHER = re.compile(r"\bUnderstudy\b(?! synth)|\bsimply\b ?", re.I)

# Quoted enum values, paths and ids inside a sentence are not copy: 'synthetic', data/synthetic, synthetic/learners, ana-synthetic-origin.
_MASK = re.compile(r"(?<=['\"])(?:synthetic|simulated)(?=['\"])|(?<=[/\\])synthetic|synthetic(?=[/\\])|(?<=[\w])-synthetic|synthetic-(?=origin|only\b)|(?<=[\w])-simulated", re.I)

# (pattern, replacement), case-insensitive, in order: the specific phrasings first, the fallback last.
RULES: list[tuple[str, str]] = [
    (r"origin: \*\*synthetic\*\*", "measured on: **generators we wrote**"),
    (r"simulated participants? \(language model\), not people", "language-model participants, not people"),
    (r"simulated participants \(language model\)", "language-model participants"),
    (r"simulated participant \(language model\)", "language-model participant"),
    (r"simulated[- ]participant(s?)\b", r"language-model participant\1"),
    (r"simulated study", "language-model study"),
    (r"simulated role studies", "language-model role studies"),
    (r"simulated actuator", "stand-in actuator"),
    (r"simulated experts, not recorded people", "generated experts, not recorded people"),
    (r"synthetic firms", "made-up firms"),
    (r"synthetic firm", "made-up firm"),
    (r"synthetic \(generators we wrote\)", "generators we wrote"),
    (r"synthetic generators we wrote", "generators we wrote"),
    (r"synthetic generator family", "generator family"),
    (r"synthetic generator", "generator"),
    (r"synthetic results carry a badge\. ?", ""),
    (r"synthetic simulator:", "Simulator we wrote:"),
    (r"synthetic household:", "Example household:"),
    (r"carries a synthetic badge", "says what it was measured on"),
    (r"regenerate missing synthetic data", "regenerate missing data"),
    (r"simulated action budget", "stand-in action budget"),
    (r"tier-3 simulated runs", "tier-3 stand-in runs"),
    (r"per simulated run", "per stand-in run"),
    (r"simulated clock", "stand-in clock"),
    (r"simulated presence service", "stand-in presence service"),
    (r"simulated 'improvement'", "language-model 'improvement'"),
    (r"numbers are synthetic until", "numbers come from generated people until"),
    (r"synthetic sandbox\b", "sandbox"),
    (r"scripted synthetic ", "scripted "),
    (r"synthetic apprentices", "scripted apprentices"),
    (r"synthetic apprentice\b", "scripted apprentice"),
    (r"synthetic (experts?|runs|people we) generated", r"\1 generated"),
    (r"the synthetic data was generated", "the data was generated"),
    (r"(attacks? (?:are|is)) synthetic", r"\1 scripted"),
    (r"synthetic attacks", "scripted attacks"),
    (r"synthetic red-team", "scripted red-team"),
    (r"stand-in synthetic calendar", "stand-in example calendar"),
    (r"screens are synthetic:", "screens are sandbox pages we built:"),
    (r"negatives are synthetic:", "negatives are constructed:"),
    (r"renderer is simulated:", "renderer is a stand-in:"),
    (r"number is simulated:", "number comes from a generator:"),
    (r"synthetic: simulated ", "generated: "),
    (r"\((no|6 s) deadline, simulated\)", r"(\1 deadline, replayed offline)"),
    (r"reported as simulated", "reported from simulation"),
    (r"ever simulated inside", "ever invented inside"),
    (r"generate synthetic data", "generate the data"),
    (r"generate synthetic personas", "generate example personas"),
    (r"; synthetic\)", "; all generated)"),
    (r"synthetic origin:", "Generated people:"),
    (r"synthetic results are labelled synthetic", "results from generators we wrote say so"),
    (r"it stays labelled synthetic", "it stays labelled as a generator result"),
    (r"labelled synthetic;", "labelled as planted;"),
    (r"re-simulated", "replayed"),
    (r"(?<=\.) Synthetic\.$", " Made-up firm data."),
    (r" \((?:synthetic|simulated)\)", ""),
    (r"\((?:synthetic|simulated), ", "("),
    (r"synthetic design", "generated design"),
    (r"\bsynthetic\b", "generated"),
    (r"\bsimulated\b", "generated"),
]


def _carry(src: str, rep: str) -> str:
    return rep[:1].upper() + rep[1:] if src[:1].isupper() else rep


def reword(text: str) -> str:
    """One sentence in the app's wording. Text with no banned word, or with no whitespace (an id, an enum, a path), is returned as it is."""
    if not re.search(r"\s", text) or not (BANNED.search(text) or _OTHER.search(text)):
        return text
    text = re.sub(r"\bUnderstudy\b(?! synth)", "Knack", text)
    text = re.sub(r"\b[Ss]imply ", "", text)
    masked: list[str] = []

    def hide(m: re.Match[str]) -> str:
        masked.append(m.group(0))
        return f"\x00{len(masked) - 1}\x00"

    out = _MASK.sub(hide, text)
    for pat, rep in RULES:
        out = re.sub(pat, lambda m, rep=rep: _carry(m.group(0), m.expand(rep)), out, flags=re.I)
    return re.sub(r"\x00(\d+)\x00", lambda m: masked[int(m.group(1))], out)


def reword_tree(o: Any) -> Any:
    """A copy of a JSON-like tree with every prose string value reworded. Keys, numbers, booleans and None are untouched."""
    if isinstance(o, str):
        return reword(o)
    if isinstance(o, dict):
        return {k: reword_tree(v) for k, v in o.items()}
    if isinstance(o, list):
        return [reword_tree(v) for v in o]
    if isinstance(o, tuple):
        return [reword_tree(v) for v in o]
    return o
