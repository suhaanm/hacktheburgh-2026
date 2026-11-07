"""Fact handles (REQ-7 AGT): the model types a HANDLE, code resolves the VALUE.

The goal given to a computer-use model carries a closed vocabulary of handles such as `{household.savings}` with a
plain-words meaning each. The model emits a `type` action whose text is exactly one handle (that is the `type_fact`
tool: a type action whose argument is a handle). Code checks the handle against the closed vocabulary, lets the
SafetyPipeline gate the action as a type action with a handle, and only then, at actuation time, resolves the handle
to a value and hands the value to the actuator.

What this guarantees, and what it does not
  * prompts, the model's history, step events, the audit log and the approval queue hold handles, never values;
  * a literal value, an unknown handle, or several handles in one action is refused, and so is typing a printable
    character through a key press (that would be a literal typed by another route);
  * the typed value is visible on the screen afterwards, so a screenshot sent to the model after the step can show
    it. That is unavoidable for any agent that watches the screen; it is why screenshots are never stored.

Resolution is per site: money is converted to the period the site's field asks for (site c asks annual and weekly),
and a drop-down gets the option text that site uses, so one handle works on all three calculators.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from ..completion import SITE_LABEL
from ..sandbox_sites.bundles import CANONICAL_PARAMS
from ..sandbox_sites.households import Household, as_household
from ..sandbox_sites.specs import SELECT_LABELS, SITES, bound_value

HANDLE_RE = re.compile(r"^\{([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)\}$")

CALC_VOCAB: dict[str, str] = {
    "household.adults": "how many adults live in the household (the page may ask in words)",
    "household.adult1_age": "the age of the first adult, the claimant",
    "household.adult2_age": "the age of the partner (nothing is typed if there is no partner)",
    "household.children_ages": "the children's ages, separated by commas (nothing is typed if there are none)",
    "household.adult1_earnings": "the first adult's take-home pay, in the period the field asks for",
    "household.adult2_earnings": "the partner's take-home pay, in the period the field asks for",
    "household.limited_capability": "whether a health condition limits ability to work (yes or no)",
    "household.tenure": "whether the household rents or owns its home",
    "household.rent": "the rent, in the period the field asks for",
    "household.bedrooms": "how many bedrooms the household needs",
    "household.savings": "total savings and investments",
    "household.childcare": "childcare costs, in the period the field asks for",
}
NOTE_VOCAB: dict[str, str] = {
    "note.case_ref": "the case reference",
    "note.result_a": "the figure the first calculator showed",
    "note.result_b": "the figure the second calculator showed",
    "note.result_c": "the figure the third calculator showed",
    "note.reconciliation": "whether the calculators agree (agree or discrepancy)",
    "note.text": "the case note text",
}
NOTE_RECONCILIATION = {"agree": "Calculators agree", "discrepancy": "Discrepancy: needs review"}
# handle -> canonical household parameter (money handles are per site, see calculator_values)
_CANON = {"household.adults": "adults", "household.adult1_age": "adult1_age", "household.adult2_age": "adult2_age",
          "household.children_ages": "children_ages", "household.adult1_earnings": "adult1_earnings_monthly",
          "household.adult2_earnings": "adult2_earnings_monthly", "household.limited_capability": "limited_capability",
          "household.tenure": "tenure", "household.rent": "rent_monthly", "household.bedrooms": "bedrooms",
          "household.savings": "savings", "household.childcare": "childcare_monthly"}


class FactRefused(ValueError):
    """The typed text is not exactly one known handle. `code` is audit-safe: no text is ever copied into it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class UnresolvedFact(RuntimeError):
    pass


def calculator_values(site: str, household: Household | Mapping[str, Any]) -> dict[str, str]:
    """handle -> the text to type on this site. Computed here, in code, at actuation time; never put in a prompt.
    Accepts a Household, its dict form, or the canonical parameter strings (`Household.params()`)."""
    if isinstance(household, Mapping) and "adult1_age" in household and "adults" in household:
        p = dict(household)           # already the canonical parameter strings
    else:
        p = as_household(household).params()
    spec = SITES[site]
    labels = SELECT_LABELS[site]
    out: dict[str, str] = {}
    for handle, canon in _CANON.items():
        if canon in labels:
            out[handle] = labels[canon][p[canon]]
        else:
            out[handle] = bound_value(spec, canon, p)
    if p["adults"] == "1":
        out["household.adult2_age"] = ""
        out["household.adult2_earnings"] = ""
    return out


class FactStore:
    """A closed vocabulary of handles and, privately, how to resolve each one."""

    def __init__(self, vocabulary: Mapping[str, str], resolvers: Mapping[str, Callable[[], str]]) -> None:
        if set(vocabulary) != set(resolvers):
            raise ValueError("every handle needs a description and a resolver")
        self._vocab = dict(vocabulary)
        self._resolvers = dict(resolvers)
        self.resolved: list[str] = []     # handles resolved so far (names only)

    # ---- building
    @classmethod
    def for_calculator(cls, site: str, household: Household | Mapping[str, Any]) -> "FactStore":
        """`household`: a Household, its dict form, or its canonical parameter strings."""
        vals = calculator_values(site, household)
        return cls(CALC_VOCAB, {h: (lambda v=v: v) for h, v in vals.items()})

    @classmethod
    def for_casenote(cls, params: Mapping[str, str]) -> "FactStore":
        keys = {"note.case_ref": "case_ref", "note.result_a": "result_a", "note.result_b": "result_b",
                "note.result_c": "result_c", "note.reconciliation": "reconciliation", "note.text": "note_text"}
        res = {h: (lambda k=k: str(params.get(k, ""))) for h, k in keys.items()}
        # the drop-down shows words, not the stored value: type-ahead needs the option text
        res["note.reconciliation"] = lambda: NOTE_RECONCILIATION.get(str(params.get("reconciliation", "")), "")
        return cls(NOTE_VOCAB, res)

    # ---- what the model may see
    @property
    def handles(self) -> tuple[str, ...]:
        return tuple(self._vocab)

    def goal_block(self) -> str:
        """Trusted wording for the goal: handles and what they mean. No values."""
        lines = [f"{{{h}}}: {d}" for h, d in self._vocab.items()]
        if not lines:
            return "You have nothing to type on this task. Do not type anything and do not press letter or digit keys."
        return ("FACTS you may type. You cannot see their values. To enter one, click the field, then type exactly the "
                "handle, braces included, as the whole text of one type action (for example {household.savings}). Never "
                "type a number or a word yourself, and never press a letter or digit key to enter data. The code puts "
                "the real value in. If a fact has no value for this household nothing is typed; carry on.\n" + "\n".join(lines))

    # ---- checking and resolving
    def check(self, text: Any) -> str:
        """Return the handle if `text` is exactly one known handle, else raise FactRefused."""
        if not isinstance(text, str):
            raise FactRefused("literal_text", "typed text must be a handle")
        m = HANDLE_RE.match(text.strip())
        if not m:
            raise FactRefused("literal_text", "typed text is not a fact handle; type a handle from the list, nothing else")
        handle = m.group(1)
        if handle not in self._vocab:
            raise FactRefused("unknown_handle", "that handle is not in the vocabulary for this task")
        return handle

    def resolve(self, handle: str) -> str:
        if handle not in self._resolvers:
            raise UnresolvedFact(f"unknown handle {handle!r}")
        self.resolved.append(handle)
        return self._resolvers[handle]()


_PRINTABLE_SINGLE = re.compile(r"^[^\s]$")


def key_would_type_text(keys: list[str]) -> bool:
    """A bare printable key (or shift plus one) types a literal. Shortcuts with ctrl, alt or cmd, and named keys
    (Enter, Tab, Escape, arrows) do not."""
    low = [k.lower() for k in keys]
    if any(k in ("ctrl", "control", "alt", "option", "cmd", "command", "meta", "super") for k in low):
        return False
    return any(_PRINTABLE_SINGLE.match(k) for k in keys)
