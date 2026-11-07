"""Code-checked completion (AGT-4). Code, not a model, decides success.

For the benefits task the final observation must contain, for EACH calculator, its result fields
(amount, status, quote reference) and the case note id. A model "done" that fails this check is
recorded as a FALSE CLAIM. See docs/reference-notes/rouge.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

SITE_LABEL = {"a": "GovCalc", "b": "Quick Estimator", "c": "EntitledTo"}
REF_RE = re.compile(r"\b(?:GOV|T2U|ET)-[A-Z0-9]{6}\b")
NOTE_ID_RE = re.compile(r"\bCN-\d{4}\b")
MONEY_RE = re.compile(r"(?<![\w.])(?:£\s*)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?!\d)")
STATUS_POS = ("likely to be eligible", "likely to qualify", "eligible")
STATUS_NEG = ("unlikely", "not eligible", "not qualify")


def parse_money(text: str) -> float | None:
    """First pound figure in `text` ('£1,234', '955.00 per month', '313.14 GBP / month')."""
    m = MONEY_RE.search(text or "")
    if not m:
        return None
    whole = m.group(1).replace(",", "")
    return float(f"{whole}.{m.group(2) or '0'}")


def parse_status(text: str) -> bool | None:
    t = (text or "").lower()
    if any(n in t for n in STATUS_NEG):
        return False
    if any(p in t for p in STATUS_POS):
        return True
    return None


@dataclass(frozen=True)
class ResultFields:
    site: str
    amount_text: str
    amount: float
    status_text: str
    eligible: bool
    ref: str

    def as_dict(self) -> dict[str, Any]:
        return {"site": self.site, "amount_text": self.amount_text, "amount": self.amount,
                "status_text": self.status_text, "eligible": self.eligible, "ref": self.ref}


def validate_result_fields(site: str, raw: Mapping[str, Any]) -> tuple[ResultFields | None, list[str]]:
    """Check what a tier (or the reader) says a calculator displayed. Returns (fields, problems)."""
    problems: list[str] = []
    amount_text = str(raw.get("amount_text") or raw.get("amount") or "").strip()
    status_text = str(raw.get("status_text") or raw.get("status") or "").strip()
    ref = str(raw.get("ref") or "").strip()
    amount = parse_money(amount_text)
    if amount is None:
        problems.append("amount is not a money figure")
    eligible = parse_status(status_text)
    if eligible is None:
        problems.append("status is not recognised")
    if not REF_RE.fullmatch(ref):
        problems.append("reference is not a quote reference")
    if problems:
        return None, problems
    assert amount is not None and eligible is not None
    return ResultFields(site, amount_text, amount, status_text, eligible, ref), []


@dataclass(frozen=True)
class CompletionResult:
    ok: bool
    missing: tuple[str, ...] = ()
    checked: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "missing": list(self.missing)}


def _norm(s: str) -> str:
    return " ".join((s or "").replace(",", "").split()).lower()


def check_completion(final_text: str, results: Mapping[str, ResultFields], note_id: str | None,
                     expected_sites: tuple[str, ...] = ("a", "b", "c")) -> CompletionResult:
    """The final observation (the saved case note page) must contain every calculator's amount, status
    and reference, and the note id. Anything missing is named, so a human can see why."""
    text = _norm(final_text)
    missing: list[str] = []
    checked: list[str] = []
    for s in expected_sites:
        r = results.get(s)
        if r is None:
            missing.append(f"calculator {s}: no result")
            continue
        # Amount is compared by its digits so '£955.00 per month' and '955.00' both count.
        digits = _norm(r.amount_text)
        figure = re.search(r"\d[\d.]*", digits)
        if not figure or figure.group(0).rstrip(".") not in text:
            missing.append(f"calculator {s}: amount {r.amount_text!r}")
        if _norm(r.ref) not in text:
            missing.append(f"calculator {s}: reference")
        if _norm(r.status_text) not in text:
            missing.append(f"calculator {s}: status")
        checked.append(s)
    if not note_id or not NOTE_ID_RE.fullmatch(note_id):
        missing.append("case note id")
    elif _norm(note_id) not in text:
        missing.append("case note id not on page")
    return CompletionResult(ok=not missing, missing=tuple(missing), checked=tuple(checked))


@dataclass
class ClaimLedger:
    """Counts claims of success against what code verified. `false_claims` goes to the Agent API."""

    claims: list[dict[str, Any]] = field(default_factory=list)

    def record(self, source: str, claimed_success: bool, verified: bool, note: str = "") -> bool:
        """Returns True if this was a FALSE claim (claimed success, code says no)."""
        false = bool(claimed_success and not verified)
        self.claims.append({"source": source, "claimed": claimed_success, "verified": verified,
                            "false_claim": false, "note": note[:120]})
        return false

    @property
    def false_claims(self) -> int:
        return sum(1 for c in self.claims if c["false_claim"])
