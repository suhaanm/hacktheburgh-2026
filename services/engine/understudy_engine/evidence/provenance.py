"""The number-provenance check (REQ-6): THE MODEL NEVER COMPUTES A NUMBER, and this is the code that holds it to that.

A reply is a strict JSON object: sections, each a list of sentences ``{text, uses}``, and up to two coach-menu ids. For every
sentence the check proves, with no model in the loop:

* **Every number traces.** Each number in the text (digits, number words, percentages, durations written as "1 minute 6
  seconds", "1:06", "a minute", "about a minute", "just over a minute", pounds, rates) must equal a field of the packet that the
  sentence cites in ``uses``, in one of the forms of the fixed rounding table in ``numbers.py``. A number that matches nothing is
  ``invented_number``; one that matches a field the sentence did not cite is ``uncited_number``; one that is near a cited field but
  not in its table is ``wrong_rounding``. Multipliers and shares that the model would have computed ("twice as long", "half",
  "three times", "a third") are ``derived_ratio``; vague counts next to a unit ("several minutes") are ``vague_quantity``.
* **Intervals stay whole.** "between 55 and 72 seconds" must be the lo and hi of ONE interval, in order (``swapped_interval``), and
  next to a point value it must belong to the same item (``interval_other_item``). A number that fits a different habit than the
  one the sentence names is ``swapped_attribution``. A time difference that the packet says is negative cannot be called slower
  (``wrong_direction``).
* **Names trace.** A habit, cog or routine the sentence names must be in the packet and cited (``name_not_in_packet``,
  ``name_not_cited``). An id-shaped token that is in no vocabulary is ``unknown_id``. A cause attributed to something that is
  not in the vocabulary ("because of tab switching") is ``unknown_habit``. "largest", "smallest", "most of" are checked against
  the packet's own ordering and shares (``rank_claim_false``, ``share_claim_false``).
* **Nothing else rides along.** A URL, a path, an email or any other shape the privacy backstop refuses (``pii:<rule>``, ``link``),
  a quoted string that is not an allowed name (``quoted_string``), an instruction-like sentence (``injection``,
  ``instruction_like``), advice outside the vetted menu (``unvetted_advice``), a causal claim (``causal_claim``), a promise that
  a novice becomes an expert or will improve (``expert_claim``).

What this does not do, stated plainly: it proves **traceability**, not **truth**. A sentence whose numbers all trace can still be
a misleading reading of them, and a packet built from a wrong analysis yields a faithful explanation of a wrong number. The
unknown-habit rule is a set of cue patterns, not a language model: a novel phrasing with no cue can pass. A rejected reply costs
nothing (the deterministic template is used), so the rules lean toward rejecting.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

import jsonschema

from ..privacy import patterns as privacy_patterns
from . import vocab as V
from .numbers import UNIT_SCALE_S, accepts, near
from .numbers import render
from .packet import AMBIENT, ExplainRequest, EvidencePacket, Fact, FactTable, facts

MAX_TEXT = 320            # what a model may write
MAX_EXPANDED = 520        # after the code has filled in placeholders

REPLY_SCHEMA: dict[str, Any] = {
    "title": "EvidenceReply",
    "type": "object",
    "properties": {
        "sections": {
            "type": "array", "minItems": 1, "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["explanation", "answer"]},
                    "sentences": {
                        "type": "array", "minItems": 1, "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
                                "uses": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 64}},
                            },
                            "required": ["text", "uses"], "additionalProperties": False,
                        },
                    },
                },
                "required": ["kind", "sentences"], "additionalProperties": False,
            },
        },
        "coach_actions": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": list(V.MENU_IDS)}},
    },
    "required": ["sections", "coach_actions"],
    "additionalProperties": False,
}


# ------------------------------------------------------------------------------------------------ verdict
@dataclass
class SentenceResult:
    section: str
    index: int
    codes: list[str]


@dataclass
class Verdict:
    ok: bool
    expanded: Any = None
    rejected: list[SentenceResult] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=lambda: {"sentences": 0, "numbers": 0, "names": 0, "intervals": 0})
    schema_ok: bool = True
    dropped_actions: list[str] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        return sorted({c for r in self.rejected for c in r.codes})

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "schema_ok": self.schema_ok, "checked": dict(self.checked),
                "rejected": [{"section": r.section, "index": r.index, "codes": r.codes} for r in self.rejected],
                "dropped_actions": list(self.dropped_actions)}


# ------------------------------------------------------------------------------------------------ placeholders
# The agent service's model port neutralises markup in every prompt it sends (``{`` becomes the ornate brace U+2774, ``}`` U+2775), and a model
# then writes its placeholders with those glyphs; both forms are accepted. A model may also name a collection by the packet's plural
# (``habits.pace.seconds``): the aliases below map it to the path the facts use (``habit.pace.seconds``).
_PLACEHOLDER = re.compile(r"[{\u2774]([A-Za-z0-9_.\-]{1,64})[}\u2775]")
PATH_ALIASES = {"habits": "habit", "cohort_habits": "cohort_habit", "cogs": "cog", "consequences": "consequence", "routines": "routine",
                "blocks": "block", "question": "question"}


def canon_path(p: str) -> str:
    head, sep, rest = p.partition(".")
    return PATH_ALIASES.get(head, head) + sep + rest


def render_fact(f: Fact) -> str:
    """How code writes a field the model referred to by ``{path}``: the canonical form of ``numbers.render``, as a magnitude for a point
    (the sentence says longer, shorter or saved) and signed for the ends of an interval."""
    text = render(abs(f.value), f.unit)
    return ("-" + text) if (f.role in ("lo", "hi") and f.value < 0 and not text.startswith("0")) else text


def expand_placeholders(reply: dict[str, Any], tab: FactTable) -> dict[str, Any]:
    """A copy of a (schema-valid) reply with every ``{field.path}`` in the text replaced by the field's canonical spoken form, and the
    path added to the sentence's ``uses``. This lets a model that is poor at copying numbers still write fluent text around them: the
    model never types a figure, code does, and the expanded text then goes through the same check as any other. A placeholder that
    names no numeric field is left in place and refused (``bad_placeholder``)."""
    out = copy.deepcopy(reply)
    for sec in out["sections"]:
        for s in sec["sentences"]:
            used = list(s["uses"])

            def sub(m: re.Match[str]) -> str:
                f = tab.facts.get(canon_path(m.group(1)))
                if f is None:
                    return m.group(0)
                if f.path not in used:
                    used.append(f.path)
                return render_fact(f)

            s["text"] = _PLACEHOLDER.sub(sub, s["text"])
            s["uses"] = [canon_path(u) if canon_path(u) in tab.facts or canon_path(u) in tab.containers or canon_path(u) in tab.labels else u
                         for u in used]
    return out


# ------------------------------------------------------------------------------------------------ number mentions
_W1 = "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_ONES = "one|two|three|four|five|six|seven|eight|nine"
_NUMWORD = rf"(?:(?:{_TENS})(?:[- ](?:{_ONES}))?|{_W1})"
_WORD_VAL = {w: i for i, w in enumerate(_W1.split("|"))}
_TENS_VAL = {w: 20 + 10 * i for i, w in enumerate(_TENS.split("|"))}

_MAIN = re.compile(re.sub(r"\n\s*", "",
    rf"""
 (?P<clock>(?<![\w:.])\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?![\w:]))
|(?P<phr>\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten) and a half (?:minutes?|hours?)\b|\bhalf an? (?:minute|hour)\b|\ban? (?:minute|hour) and a half\b|\b(?:a|an|one) (?:minute|hour)\b|\ba second\b(?!\s*[a-z]))
|(?P<vague>\b(?:a few|several|a handful of|dozens of|hundreds of|a number of|many)\s+(?:seconds?|minutes?|hours?|times|cases?|steps?|runs?|episodes?|routines?)\b)
|(?P<couple>\ba couple of\b)
|(?P<derived>\b(?:twice|thrice|double[ds]?|triple[ds]?|halved|halves|half|(?:a|one|two|three|four|five)[- ](?:third|quarter|fifth|half|tenth)s?|[a-z]+-fold|a (?:third|quarter|fifth|tenth)|thirds|quarters|fifths)\b)
|(?P<num>(?P<cur>[£$€])?(?<![\w.])(?P<sign>-)?(?P<dig>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?))
|(?P<word>\b(?:(?:a|one|two|three|four|five|six|seven|eight|nine)\s+hundred(?:\s+and\s+{_NUMWORD})?|{_NUMWORD}|hundred|thousand)\b)
"""), re.I,
)
_TAIL = re.compile(
    r"""\s*(?:
 (?P<pct>%|percent\b|per\s?cent\b|pc\b|percentage\s+points?\b)
|(?P<ph>(?:times\s+|alarms\s+|nudges\s+)?(?:an|per|each|every|a)\s+hour\b)
|(?P<h>hours?\b|hrs?\b|h\b)
|(?P<min>minutes?\b|mins?\b|m\b)
|(?P<s>seconds?\b|secs?\b|s\b)
|(?P<gbp>pounds?\b|gbp\b|quid\b)
|(?P<ord>st\b|nd\b|rd\b|th\b)
|(?P<mult>x\b|×)
|(?P<times>times\b)
|(?P<noun>cases?\b|routines?\b|runs?\b|steps?\b|episodes?\b|people\b|persons?\b|households?\b|habits?\b|bins?\b|calculators?\b|checks?\b|trials?\b|readings?\b|alarms?\b)
|(?P<weeks>weeks?\b)
|(?P<oth>days?\b|months?\b|years?\b)
)""",
    re.X | re.I,
)
_UNDER = re.compile(r"(?:just |slightly |a little |a bit |well )?(?:under|below|less than|fewer than|at most|up to|almost|nearly|within|shy of)\s*(?:about |around |roughly )?$")
_OVER = re.compile(r"(?:just |slightly |a little |a bit |well )?(?:over|above|more than|exceeds?|exceeding|beyond|at least|upwards of|in excess of)\s*(?:about |around |roughly )?$")
_APPROX = re.compile(r"(?:about|around|roughly|approximately|approx\.?|circa|some|~|c\.|close to|in the region of|of order)\s*$")
_CONNECT = re.compile(r"^\s*(?:to|and|-|,|or|through)\s*$")
_BEFORE_INT = re.compile(r"(?:between|from)\s*$")
_BEFORE_BRACKET = re.compile(r"[\[(]\s*$")
_MINUS_WORD = re.compile(r"(?:minus|negative)\s*$")
_COMPARATIVE = re.compile(r"^\s*(?:as\b|longer|slower|faster|more|greater|bigger|higher|lower|less|the\b|that|over\b)")

TIME_BASE = {"s": 1.0, "min": 60.0, "h": 3600.0}


@dataclass
class Mention:
    kind: str                  # num | derived | vague
    start: int
    end: int
    raw: float = 0.0           # the number as written (signed)
    unit: str | None = None    # s | min | h | pct | gbp | ph | count | ord | oth | None
    decimals: int = 0
    qualifier: str = "none"    # none | approx | over | under
    step: float | None = None  # overrides the unit step (word forms such as "half a minute")
    sign_word: bool = False
    noun: str | None = None    # the word that follows a count ("24 people", "16 instances"), if it looks like a noun

    @property
    def is_time(self) -> bool:
        return self.unit in TIME_BASE

    def denoted(self) -> float:
        """The value in the base the facts are compared in: seconds, percent points, or the plain number."""
        if self.unit in TIME_BASE:
            return abs(self.raw) * TIME_BASE[self.unit]
        return abs(self.raw)

    def step_units(self) -> float:
        if self.step is not None:
            return self.step
        return TIME_BASE.get(self.unit or "", 1.0)


def _word_number(s: str) -> float | None:
    s = s.lower().strip()
    m = re.fullmatch(rf"(a|one|two|three|four|five|six|seven|eight|nine)\s+hundred(?:\s+and\s+({_NUMWORD}))?", s)
    if m:
        base = {"a": 1}.get(m.group(1)) or _WORD_VAL[m.group(1)]
        return base * 100 + (_word_number(m.group(2)) or 0)
    if s == "hundred":
        return 100.0
    if s == "thousand":
        return 1000.0
    parts = re.split(r"[- ]", s)
    if parts[0] in _TENS_VAL:
        return float(_TENS_VAL[parts[0]] + (_WORD_VAL[parts[1]] if len(parts) > 1 else 0))
    return float(_WORD_VAL[parts[0]]) if parts[0] in _WORD_VAL else None


_COUNT_SKIP = r"(?:shadow|clean|more|consecutive|further|other|additional|extra|matching|stuck|false|such|different|separate)"
_NEXT_WORD = re.compile(rf"\s+(?:{_COUNT_SKIP}\s+)*([a-z][a-z\-]*)")
_FUNCTION_WORDS = frozenset((
    "and or of the a an to in on for with by at from as per is are was were be been than that this these those it its which who but so if "
    "then when while about over under between against after before out off up down into onto also too only just more less longer shorter "
    "faster slower each all both every not no has have had can will would could should may might seconds second minutes minute hours hour "
    "percent into around roughly approximately across during since until within without upon using than whereas whereby however although "
    "though because there here we you they he she our your their my his her").split())


def _noun_after(t: str, end: int) -> str | None:
    m = _NEXT_WORD.match(t, end)
    if not m:
        return None
    w = m.group(1)
    return None if w in _FUNCTION_WORDS else w


def _qualifier(before: str) -> str:
    b = before[-32:]
    if _UNDER.search(b):
        return "under"
    if _OVER.search(b):
        return "over"
    if _APPROX.search(b):
        return "approx"
    return "none"


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    return t.replace("−", "-").replace("–", "-").replace("—", "-").replace(" ", " ").replace(" ", " ")


def _neutralise_ids(t: str) -> str:
    """Blank out id-shaped tokens (routine ids with digits, rungs and levels) so their digits are not read as numbers."""
    t = re.sub(r"\b(?:calc-entry-3x|case-note-copy|cliff-recheck|queue-sweep|weekly-report|weekly-metric-refresh|rerun-failed-ci)\b",
               lambda m: "ROUTINE" + " " * (len(m.group(0)) - 7) if len(m.group(0)) >= 7 else m.group(0), t)
    t = re.sub(r"\b[AL][0-4]\b", "Zz", t)             # a rung or a level id: same length, so spans stay aligned
    return t


def extract_mentions(text: str) -> list[Mention]:
    """Every number-like mention in ``text``, in order, with its unit, qualifier and written precision."""
    t = _neutralise_ids(normalise(text))
    low = t.lower()
    out: list[Mention] = []
    pos = 0
    for m in _MAIN.finditer(t):
        if m.start() < pos:
            continue
        before = low[: m.start()]
        qual = _qualifier(before)
        kind = None
        for g in ("clock", "phr", "vague", "couple", "derived", "num", "word"):
            if m.group(g) is not None:
                kind = g
                break
        if kind == "clock":
            parts = [int(x) for x in m.group("clock").split(":")]
            secs = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
            out.append(Mention("num", m.start(), m.end(), float(secs), "s", 0, qual))
            pos = m.end()
        elif kind == "phr":
            ph = m.group("phr").lower()
            nh = re.match(r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten) and a half (minute|hour)", ph)
            if nh:
                base = float(nh.group(1)) if nh.group(1).isdigit() else float(_WORD_VAL[nh.group(1)])
                unit_s = 3600.0 if nh.group(2) == "hour" else 60.0
                out.append(Mention("num", m.start(), m.end(), (base + 0.5) * unit_s, "s", 0, qual, unit_s / 2))
                pos = m.end()
                continue
            if ph.startswith("half a minute") or ph.startswith("half an minute"):
                val, step = 30.0, 30.0
            elif ph.startswith("half an hour") or ph.startswith("half a hour"):
                val, step = 1800.0, 1800.0
            elif ph.endswith("minute and a half"):
                val, step = 90.0, 30.0
            elif ph.endswith("hour and a half"):
                val, step = 5400.0, 1800.0
            elif "hour" in ph:
                val, step = 3600.0, 3600.0
            elif "second" in ph:
                val, step = 1.0, 1.0
            else:
                val, step = 60.0, 60.0
            out.append(Mention("num", m.start(), m.end(), val, "s", 0, qual, step))
            pos = m.end()
        elif kind == "vague":
            out.append(Mention("vague", m.start(), m.end()))
            pos = m.end()
        elif kind == "derived":
            out.append(Mention("derived", m.start(), m.end()))
            pos = m.end()
        elif kind in ("num", "couple", "word"):
            if kind == "couple":
                val, dec, end, qual2 = 2.0, 0, m.end(), "approx"
            elif kind == "word":
                val = _word_number(m.group("word"))
                if val is None:
                    continue
                dec, end, qual2 = 0, m.end(), qual
            else:
                digs = m.group("dig").replace(",", "")
                val = float(digs)
                dec = len(digs.split(".")[1]) if "." in digs else 0
                end, qual2 = m.end(), qual
            tail = _TAIL.match(t, end)
            unit = None
            tail_noun = None
            if m.group("cur") if kind == "num" else False:
                unit = "gbp"
            if tail is not None:
                tg = tail.lastgroup
                if tg in ("noun", "times"):
                    tail_noun = tail.group(0).strip().lower()
                unit = {"pct": "pct", "ph": "ph", "h": "h", "min": "min", "s": "s", "gbp": "gbp", "ord": "ord", "mult": "mult",
                        "times": "times", "noun": "count", "weeks": "weeks", "oth": "oth"}.get(tg, unit)
                end = tail.end()
            sign = (kind == "num" and m.group("sign") is not None) or bool(_MINUS_WORD.search(before))
            if kind == "word" and unit is None and (val < 2 or val > 99) and m.group("word").lower() in ("one", "zero", "hundred", "thousand"):
                continue                       # "one of the", "no one": only a number when it carries a unit or noun
            if kind == "word" and unit is None and m.group("word").lower() in ("one",):
                continue
            if unit == "mult":
                out.append(Mention("derived", m.start(), end))
                pos = end
                continue
            if unit == "times":
                rest = t[end: end + 24].lower()
                if _COMPARATIVE.match(rest):
                    out.append(Mention("derived", m.start(), end))
                    pos = end
                    continue
                unit = "count"
            noun = tail_noun
            if noun is None and unit is None and dec == 0:
                noun = _noun_after(t.lower(), end)
            out.append(Mention("num", m.start(), end, -val if sign else val, unit, dec, qual2, None, bool(sign), noun))
            pos = end
    return _merge_compound(out, t)


def _merge_compound(ms: list[Mention], t: str) -> list[Mention]:
    """"1 minute 6 seconds" and "2 hours and 5 minutes" become one duration written to the smaller unit."""
    order = {"h": 3, "min": 2, "s": 1}
    out: list[Mention] = []
    i = 0
    while i < len(ms):
        a = ms[i]
        if (a.kind == "num" and a.unit in order and i + 1 < len(ms) and ms[i + 1].kind == "num" and ms[i + 1].unit in order
                and order[ms[i + 1].unit] < order[a.unit] and a.decimals == 0 and ms[i + 1].decimals == 0
                and re.fullmatch(r"\s*(?:and\s+|,\s*)?", t[a.end: ms[i + 1].start])):
            b = ms[i + 1]
            total = abs(a.raw) * TIME_BASE[a.unit] + abs(b.raw) * TIME_BASE[b.unit]
            out.append(Mention("num", a.start, b.end, total, "s", 0, a.qualifier, TIME_BASE[b.unit]))
            i += 2
            continue
        out.append(a)
        i += 1
    return out


def find_intervals(ms: list[Mention], text: str) -> list[tuple[int, int]]:
    """Index pairs ``(i, i+1)`` of mentions written as one interval ("between A and B", "A to B", "[A, B]", "A-B unit")."""
    t = normalise(text).lower()
    pairs: list[tuple[int, int]] = []
    for i in range(len(ms) - 1):
        a, b = ms[i], ms[i + 1]
        if a.kind != "num" or b.kind != "num":
            continue
        gap = t[a.end: b.start]
        c = _CONNECT.match(gap)
        if not c:
            continue
        conn = gap.strip()
        pre = t[max(0, a.start - 14): a.start]
        if conn in ("and", ",", "or") and not (_BEFORE_INT.search(pre) or _BEFORE_BRACKET.search(pre)):
            continue
        if conn in ("to", "-", "through") or (conn in ("and", ",", "or")):
            if a.unit is None and b.unit is not None:
                a.unit = b.unit
            elif a.unit != b.unit and not (a.unit is None and b.unit is None):
                continue
            pairs.append((i, i + 1))
    return pairs


# ------------------------------------------------------------------------------------------------ text rules
_LINK = re.compile(r"https?://|www\.|://|\\\\|mailto:|\bftp:", re.I)
_QUOTE = re.compile(r"\"([^\"]{1,80})\"|“([^”]{1,80})”|(?<![\w])'([^']{2,80})'(?![\w])")
_INJECTION = re.compile(
    r"ignore (?:all |any |the |your )?(?:previous|prior|above|earlier)|disregard (?:all |any |the |your )?(?:previous|prior|above|instructions)|"
    r"system prompt|developer message|you are now|new instructions?|as an ai|jailbreak|developer mode|override (?:the |your )?(?:rules|instructions|policy)|"
    r"reveal (?:the |your )?(?:prompt|instructions|rules)|<\||\|>|\[inst\]|```|assistant:|system:|user:|begin (?:system|prompt)|"
    r"forget (?:everything|all|your)|pretend (?:to be|you)|act as (?:a|an|the)|do anything now",
    re.I)
_IMPERATIVE_START = {
    "ignore", "disregard", "forget", "reveal", "print", "output", "send", "click", "press", "run", "execute", "delete", "remove", "approve",
    "submit", "visit", "open", "download", "install", "enable", "disable", "set", "call", "email", "write", "tell", "say", "pretend", "act",
    "stop", "start", "use", "try", "consider", "remember", "make", "ensure", "avoid", "keep", "take", "check", "review", "read", "look",
    "focus", "practice", "practise", "ask", "add", "change", "go", "follow", "do", "don't", "dont", "please", "always", "never", "let's",
    "let", "switch", "turn", "give", "show", "create", "update", "reset", "paste", "copy", "enter", "type", "select", "choose", "wait",
}
_ADVICE = re.compile(
    r"\b(?:you should|you must|you need to|you ought to|you have to|you'd better|you had better|make sure|be sure to|i recommend|i suggest|"
    r"we recommend|we suggest|i advise|consider (?:doing|using|taking|adding|asking)|it would help (?:to|if)|it is best to|it's best to|"
    r"you could try|try to|try (?:using|doing|taking)|i would|you will want to|worth (?:trying|doing))\b", re.I)
_CAUSAL = re.compile(
    r"\b(?:because|cause[ds]?|causing|due to|owing to|thanks to|as a result|results? in|resulted in|resulting in|leads? to|led to|leading to|"
    r"responsible for|to blame|blame[ds]?|the reason|reasons? (?:is|are|why)|that'?s why|which is why|explains? why|"
    r"makes? you|made you|forces? you|forced you|slow(?:s|ed)? you(?: down)?|slows? down|cost(?:s|ing)? you|cost you|held you back|holds? you back|"
    r"holding you back|so that)\b", re.I)
# An honest hedge names the very thing it denies ("not proof that one thing caused the other", "does not cause"). It is taken out before the
# causal check, narrowly: only up to four plain words between the negation and the verb, never across a comma or a "but".
_NOT_THIS = r"(?:\s+(?!but\b|and\b|so\b|yet\b)\w+)"
_NEG_CAUSE = re.compile(
    rf"\bnot\s+(?:a\s+|an\s+|the\s+)?(?:proof|evidence|sign|signs|indication)\b{_NOT_THIS}{{0,4}}?\s+(?:caus\w*|produc\w*|lead\w*|result\w*|led)\b{_NOT_THIS}{{0,3}}"
    rf"|\b(?:do|does|did|can|could|would)\s+not{_NOT_THIS}{{0,3}}?\s+(?:caus\w*|produc\w*|lead|led|result)\b{_NOT_THIS}{{0,3}}"
    rf"|\b(?:doesn't|don't|cannot|can't){_NOT_THIS}{{0,3}}?\s+(?:caus\w*|produc\w*|lead|led|result)\b{_NOT_THIS}{{0,3}}", re.I)
_EXPERT_CLAIM = re.compile(
    r"\b(?:becom(?:e|es|ing) (?:an? )?(?:expert|as good)|will (?:soon |quickly |eventually )?(?:be|become|reach|match|catch up|improve|get (?:better|faster|quicker)|learn|close)|"
    r"expert[- ]level|as (?:good|fast|quick|skilled|efficient) as (?:an? |the )?(?:expert|experts)|match(?:es|ing)? (?:the )?experts?|"
    r"reach(?:es|ing)? (?:the )?expert|no longer (?:an? )?novice|clos(?:e|es|ing|ed) the gap|catch(?:es|ing)? up|guarantee[sd]?|"
    r"going to (?:improve|get (?:better|faster)|become)|you(?:'ll| will) (?:be|get|improve|learn|become)|in (?:no|a few) (?:time|weeks|days)|"
    r"turn(?:s|ed|ing)? (?:you )?into an expert)\b", re.I)
_POS_DIR = re.compile(r"\b(?:slower|longer|extra|lost|additional|more time|taking more|behind|late)\b", re.I)
_NEG_DIR = re.compile(r"\b(?:faster|quicker|shorter|saved|saving|saves|less time|ahead of|ahead|earlier)\b", re.I)
_RANK_TOP = re.compile(r"\b(?:largest|biggest|main|top|greatest|leading|dominant|most important|chief)\b", re.I)
_RANK_LOW = re.compile(r"\b(?:smallest|least|tiniest|minor|lowest)\b", re.I)
_SHARE_MOST = re.compile(r"\b(?:most of|the majority|the bulk|mostly|mainly|largely|primarily|nearly all|almost all)\b", re.I)
_ID_UPPER = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_ID_SNAKE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")
_ID_ALLOWED_UPPER = {"GBP", "NHS", "UK", "USD", "ROUTINE", "ID"}
_KNOWN_SNAKE = set(V.HABITS) | set(V.MENU_IDS) | {"p_now"}
# a cause or a share of time attributed to a noun phrase: the phrase must name a known thing
_ATTR_FRAMES = [
    re.compile(r"\b(?:associat(?:es|ed|ing)|attribut(?:es|ed|ing)|link(?:s|ed|ing)|ti(?:es|ed))\s+(?P<np>[^.;:!?]+)", re.I),
    re.compile(r"\b(?:associated with|linked to|tied to|connected to|goes with|went with|goes to|went to|comes from|came from|"
               r"shows? up (?:in|as)|sits? in|lies? in|lost (?:time )?(?:to|in|on|through)|spent (?:\S+ )*?(?:on|in)|"
               r"attributed to|assigned to|(?:mostly|mainly|largely|partly|especially|particularly) (?:in|from|on|with|through))\s+"
               r"(?P<np>[^.;:!?]+)", re.I),
    re.compile(r"(?P<np>[A-Za-z][A-Za-z \-']{2,48}?)\s+(?:is|are|was|were)\s+(?:associated with|linked to|tied to|connected to)\b", re.I),
    # possessive quantifiers (Python 3.11+): the repeated number-and-unit group cannot backtrack, so a long run of digits is linear
    re.compile(r"\bspent\s++(?:(?:about|around|roughly|just over|over|nearly)\s++)?(?:(?:\d[\d.,:]*+|an? (?=minute|hour|second)|half an? (?=minute|hour))\s*+"
               r"(?:seconds?+|minutes?+|hours?+|secs?+|mins?+|s|m|h)?+\s*+(?:and\s++)?+)++(?P<np>[a-z][^.;:!?]+)", re.I),
]
_CLAUSE_VERB = re.compile(r"\b(?:is|are|was|were|be|been|has|have|had|gives?|shows?|peaked|averaged|reached|would|will|can|could|may|might|"
                          r"took|takes?|spent|went|goes|includes?|holds?|rests?)\b", re.I)
_NP_NEUTRAL = re.compile(
    r"\b(?:this|that|the|your|you|case|task|work|nearest|expert|experts|reference|cohort|average|people|person|workers?|novices?|"
    r"sample|data|time|gap|difference|steps?|alignment|stuck|reading|model|rule|routine|routines|check|checks|runs?|trust|rung|shadow|"
    r"approval|ladder|interval|intervals|error|errors|figure|figures|calculators?|households?|result|results|extra|total|part|rest|"
    r"remainder|share|habits?|cog|cogs|step|first|second|third|others?|each|all|both|these|those|it|them|one|ones|more|less|"
    r"than|of|in|on|to|for|with|and|or|a|an|at|by|from|as|per|about|around|over|under|between|now|today|week|weeks|"
    r"seconds?|minutes?|hours?|percent|pounds?|below|above|largest|biggest|main|smallest|greatest|top|leading|mean|recorded|alignment|"
    r"longer|shorter|slower|faster|saved|across|their|its|our|novices?|mostly|mainly|just|roughly|approximately|nearly|almost|"
    r"slightly|bit|little|close|half|couple|minus|plus|around|over|under|per|an?|the|here|there|also|again|too|overall|altogether|"
    r"extra|only|about|just|roughly)\b", re.I)

_ATTR_ALLOWED_PHRASES = None


def _compile_known_names() -> list[tuple[re.Pattern[str], str, str]]:
    """Phrases by which a sentence names a habit or a routine. (Cogs are named by their ids; their plain-English phrases only count as
    known words for the unknown-habit rule, below, because a phrase such as 'entering the household' also sits inside a routine's name.)"""
    out: list[tuple[re.Pattern[str], str, str]] = []
    for hid, pat in V.HABIT_PATTERNS.items():
        out.append((re.compile(rf"\b(?:{pat})\b", re.I), "habit", hid))
    for rid, name in V.ROUTINE_NAME.items():
        out.append((re.compile(rf"\b{re.escape(name)}\b", re.I), "routine", rid))
    return out


def _known_phrases() -> list[re.Pattern[str]]:
    return [rx for rx, _, _ in _KNOWN_NAMES] + [re.compile(rf"\b{re.escape(n)}\b", re.I) for n in V.COG_NAME.values() if " " in n]


_KNOWN_NAMES = _compile_known_names()
_KNOWN_PHRASES = _known_phrases()
_HABIT_RX = {hid: re.compile(rf"\b(?:{pat})\b", re.I) for hid, pat in V.HABIT_PATTERNS.items()}


def named_things(text: str) -> dict[str, set[str]]:
    """Habits, cogs and routines a sentence names (by display phrase or id)."""
    t = normalise(text)
    found: dict[str, set[str]] = {"habit": set(), "cog": set(), "routine": set()}
    for rx, kind, ident in _KNOWN_NAMES:
        if rx.search(t):
            found[kind].add(ident)
    for tok in _ID_UPPER.findall(t):
        if tok in V.COG_IDS:
            found["cog"].add(tok)
    for tok in _ID_SNAKE.findall(t):
        if tok in V.HABITS:
            found["habit"].add(tok)
    for rid in V.ROUTINE_KINDS:
        if rid in t:
            found["routine"].add(rid)
    return found


def _allowed_quotes() -> set[str]:
    s = {x.lower() for x in V.HABIT_NAME.values()} | {x.lower() for x in V.ROUTINE_NAME.values()} | {x.lower() for x in V.COG_NAME.values()}
    s |= {x.lower() for x in V.HABITS} | {x.lower() for x in V.COG_IDS} | {x.lower() for x in V.ROUTINE_KINDS}
    s |= {m.lower() for m in V.LABEL_TO_HABIT}
    return s


_ALLOWED_QUOTES = _allowed_quotes()


# ------------------------------------------------------------------------------------------------ the sentence check
class _Ctx:
    def __init__(self, tab: FactTable, req: ExplainRequest | None) -> None:
        self.tab = tab
        self.req = req
        self.ambient = [tab.facts[p] for p in AMBIENT if p in tab.facts]

    def cited(self, uses: Iterable[str]) -> tuple[list[Fact], list[str]]:
        """Facts a sentence's citations cover (plus the interval companions of a cited point, plus the ambient facts), and the
        citations that name nothing."""
        out: dict[str, Fact] = {}
        bad: list[str] = []
        for u in uses:
            covered = self.tab.under(u)
            if not covered and not self.tab.known(u):
                bad.append(u)
                continue
            for f in covered:
                out[f.path] = f
                # citing a value covers the interval written beside it (same item)
                for lo, hi, pt in self.tab.intervals:
                    if pt == f.path or f.path in (lo, hi):
                        out[lo] = self.tab.facts[lo]
                        out[hi] = self.tab.facts[hi]
                        if pt and pt in self.tab.facts:
                            out[pt] = self.tab.facts[pt]
        for f in self.ambient:
            out[f.path] = f
        return list(out.values()), bad


def _fact_accepts(m: Mention, f: Fact) -> bool:
    d = m.denoted()
    q = m.qualifier
    if m.unit in TIME_BASE:
        if f.unit not in TIME_BASE:
            return False
        return accepts(d, q, m.decimals, m.step_units(), abs(f.value) * UNIT_SCALE_S[f.unit], "s")
    if m.unit == "pct":
        return f.unit == "frac" and accepts(d, q, m.decimals, 1.0, abs(f.value) * 100.0, "other")
    if m.unit == "gbp":
        return f.unit == "gbp" and accepts(d, q, m.decimals, 1.0, abs(f.value), "gbp")
    if m.unit == "ph":
        return f.unit == "per_hour" and accepts(d, q, m.decimals, 1.0, abs(f.value), "other")
    if m.unit == "count":
        return f.unit == "count" and m.decimals == 0 and _noun_ok(m, f) and accepts(d, q, 0, 1.0, abs(f.value), "other")
    if m.unit == "weeks":
        return f.unit == "weeks" and m.decimals == 0 and accepts(d, q, 0, 1.0, abs(f.value), "other")
    if m.unit is None:
        if f.unit == "frac":
            return d <= 1.0 + 1e-9 and m.decimals >= 1 and accepts(d, q, m.decimals, 1.0, abs(f.value), "other")
        if f.unit == "score":
            return m.decimals >= 1 and accepts(d, q, m.decimals, 1.0, abs(f.value), "other")
        if f.unit == "count":
            return m.decimals == 0 and _noun_ok(m, f) and accepts(d, q, 0, 1.0, abs(f.value), "other")
        return False
    return False


def _noun_ok(m: Mention, f: Fact) -> bool:
    """A count followed by a noun ("16 instances") only matches a count whose own nouns include it ("24 people", "21 times"). A bare
    count, or a count the packet gives no nouns for, is not judged: the number still has to match the field."""
    if not m.noun or not f.nouns:
        return True
    w = m.noun.lower()
    return w in f.nouns or w.rstrip("s") in {n.rstrip("s") for n in f.nouns}


def _compatible(m: Mention, f: Fact) -> bool:
    if m.unit in TIME_BASE:
        return f.unit in TIME_BASE
    return {"pct": "frac", "gbp": "gbp", "ph": "per_hour", "count": "count", "weeks": "weeks"}.get(m.unit or "", None) == f.unit or (m.unit is None and f.unit in ("frac", "score", "count"))


def _near_fact(m: Mention, f: Fact) -> bool:
    """Is the mention close to the fact in the fact's own base (so a wrong rounding is told apart from an invented number)?"""
    d = m.denoted()
    if m.is_time:
        return near(d, abs(f.value) * UNIT_SCALE_S[f.unit], 3.0)
    if m.unit == "pct":
        return near(d, abs(f.value) * 100.0, 2.0)
    if m.unit == "gbp":
        return near(d, abs(f.value), 5.0)
    return near(d, abs(f.value), 0.5 if f.unit == "count" else 0.02)


def _sign_agrees(m: Mention, f: Fact) -> bool:
    """For the ends of an interval: a negative end is written with its sign."""
    if abs(f.value) < 0.05:
        return True
    return (m.raw < 0) == (f.value < 0)


def _direction(text: str) -> int:
    pos, neg = bool(_POS_DIR.search(text)), bool(_NEG_DIR.search(text))
    return 0 if pos == neg else (1 if pos else -1)


def _triple_of(tab: FactTable, path: str) -> str | None:
    """The key (the lo path) of the interval triple a fact belongs to, or None for a fact that has no interval."""
    for lo, hi, pt in tab.intervals:
        if path in (lo, hi, pt):
            return lo
    return None


def check_sentence(text: str, uses: list[str], ctx: _Ctx, counts: dict[str, int]) -> list[str]:
    """Reason codes for one sentence (empty list means it passes)."""
    codes: list[str] = []
    t = normalise(text)
    tab = ctx.tab

    def add(c: str) -> None:
        if c not in codes:
            codes.append(c)

    if not t.strip():
        return ["empty_text"]
    if len(t) > MAX_EXPANDED:
        add("too_long")
    if re.search(r"[{}\u2774\u2775]", t):
        add("bad_placeholder")
    if re.search(r"\bstale\b", t, re.I) and not any(v == "stale" for p_, v in tab.labels.items() if p_.endswith(".status")):
        add("stale_claim_false")
    # ---- shapes that must never ride along
    if _LINK.search(t):
        add("link")
    for rule in privacy_patterns.scan_text(t, names=False):
        add(f"pii:{rule}")
    for m in _QUOTE.finditer(t):
        inner = next(g for g in m.groups() if g is not None).strip().lower()
        if inner not in _ALLOWED_QUOTES:
            add("quoted_string")
    if _INJECTION.search(t):
        add("injection")
    first = re.sub(r"^[\W_]+", "", t).split(" ")[0].lower().strip(",.;:!") if t.strip() else ""
    if first in _IMPERATIVE_START:
        add("instruction_like")
    if _ADVICE.search(t):
        add("unvetted_advice")
    if _CAUSAL.search(_NEG_CAUSE.sub(" ", t)):
        add("causal_claim")
    if _EXPERT_CLAIM.search(t):
        add("expert_claim")

    # ---- citations
    cited, bad = ctx.cited(uses)
    for _ in bad:
        add("unknown_field")

    # ---- id-shaped tokens
    for tok in _ID_UPPER.findall(t):
        if tok not in V.COG_IDS and tok not in _ID_ALLOWED_UPPER:
            add("unknown_id")
    for tok in _ID_SNAKE.findall(t):
        if tok not in _KNOWN_SNAKE and tok not in V.COG_IDS:
            add("unknown_id")

    # ---- level and rung ids must be the packet's own
    for tok in re.findall(r"\bL[1-4]\b", t):
        if tok not in tab.levels:
            add("name_not_in_packet")
    for tok in re.findall(r"\bA[0-3]\b", t):
        if tok not in tab.rungs:
            add("name_not_in_packet")

    # ---- names
    named = named_things(t)
    counts["names"] += sum(len(v) for v in named.values())
    cited_items = {(f.coll, f.item) for f in cited if f.coll and f.item}
    for hid in named["habit"]:
        if hid not in tab.habits and hid not in tab.cohort_habits:
            add("name_not_in_packet")
        elif ("habit", hid) not in cited_items and ("cohort_habit", hid) not in cited_items:
            add("name_not_cited")
    for cid in named["cog"]:
        if cid not in tab.cogs:
            add("name_not_in_packet")
        elif ("cog", cid) not in cited_items:
            add("name_not_cited")
    for rid in named["routine"]:
        if rid not in tab.routines:
            add("name_not_in_packet")
        elif ("routine", rid) not in cited_items:
            add("name_not_cited")
    _unknown_habit_cue(t, add)

    # ---- numbers
    ms = extract_mentions(t)
    pairs = find_intervals(ms, t)
    in_pair = {i for p in pairs for i in p}
    all_facts = list(tab.facts.values())
    point_owners: list[tuple[Mention, list[Fact]]] = []
    matched_for: dict[int, list[Fact]] = {}
    for i, m in enumerate(ms):
        if m.kind == "derived":
            add("derived_ratio")
            continue
        if m.kind == "vague":
            add("vague_quantity")
            continue
        counts["numbers"] += 1
        got = [f for f in cited if _fact_accepts(m, f)]
        if not got:
            if any(_fact_accepts(m, f) for f in all_facts):
                add("uncited_number")
            elif any(_compatible(m, f) and _near_fact(m, f) for f in cited):
                add("wrong_rounding")
            else:
                add("invented_number")
            continue
        matched_for[i] = got
        if i not in in_pair:
            point_owners.append((m, got))
        # direction of a signed difference
        signed = [f for f in got if f.signed and abs(f.value) >= 0.05]
        if signed and len(signed) == len(got):
            neg = {f.value < 0 for f in signed}
            if len(neg) == 1:
                d = _direction(t)
                if neg == {True} and d != -1:
                    add("wrong_direction")
                elif neg == {False} and d == -1:
                    add("wrong_direction")
    # ---- intervals
    interval_owner_items: list[str] = []
    for (i, j) in pairs:
        counts["intervals"] += 1
        a, b = ms[i], ms[j]
        if i not in matched_for or j not in matched_for:
            continue                                   # an unmatched end is already a rejection
        ok_pair = None
        for lo, hi, pt in tab.intervals:
            flo, fhi = tab.facts[lo], tab.facts[hi]
            if flo in cited and fhi in cited and flo in matched_for[i] and fhi in matched_for[j] and _sign_agrees(a, flo) and _sign_agrees(b, fhi):
                ok_pair = (lo, hi, pt)
                break
        if ok_pair is None:
            add("swapped_interval")
            continue
        interval_owner_items.append(ok_pair[0])
    for (m, got) in point_owners:
        for owner in interval_owner_items:
            owners = {_triple_of(tab, f.path) for f in got}
            owners.discard(None)
            if owners and owner not in owners:
                add("interval_other_item")
    # ---- a number that fits only a habit the sentence does not name, while it names another
    if named["habit"]:
        for (m, got) in point_owners:
            owners = [f for f in got if f.coll in ("habit", "cohort_habit")]
            if owners and len(owners) == len(got) and not any(f.item in named["habit"] for f in owners):
                add("swapped_attribution")
    # ---- two or more habits named: each name takes the next number after it, which must be that habit's own
    if len(named["habit"]) >= 2:
        spans = sorted(((m.start(), m.end(), hid) for hid, rx in _HABIT_RX.items() for m in rx.finditer(t)), key=lambda x: x[0])
        for k, (st, en, hid) in enumerate(spans):
            nxt = spans[k + 1][0] if k + 1 < len(spans) else len(t)
            for i, m in enumerate(ms):
                if m.kind == "num" and en <= m.start < nxt and i in matched_for:
                    owners = {f.item for f in matched_for[i] if f.coll in ("habit", "cohort_habit")}
                    if owners and hid not in owners:
                        add("swapped_attribution")
                    break
    # ---- rank and share claims
    _rank_claims(t, named["habit"], tab, cited, add)
    return codes


def _unknown_habit_cue(t: str, add: Any) -> None:
    """A cause or a share of time attributed to a phrase that names nothing in the vocabulary."""
    for rx in _ATTR_FRAMES:
        for m in rx.finditer(t):
            np_text = m.group("np")
            # the phrase ends at a clause break; drop numbers and bracketed asides, then split on "and" and commas
            np_text = re.sub(r"\([^)]*\)", " ", np_text)
            np_text = re.sub(r"[-\d][\d.,:]*%?", " ", np_text)
            np_text = re.split(r"\b(?:which|that|while|but|so|where|when|compared|against|than|for the|on this|in this|over)\b", np_text, maxsplit=1)[0]
            for chunk in re.split(r",|\band\b|\bor\b|/|\bwith\b|\bto\b", np_text):
                if _CLAUSE_VERB.search(chunk):
                    break                   # a new clause starts: the attributed phrase (or list) is over
                words = [w[:-2] if w.endswith("'s") else w for w in re.findall(r"[a-z][a-z'\-]*", chunk.lower())]
                content = [w for w in words if not _NP_NEUTRAL.fullmatch(w)]
                if not content:
                    continue
                if any(rx2.search(chunk) for rx2 in _KNOWN_PHRASES):
                    continue
                if _ID_UPPER.search(chunk) or _ID_SNAKE.search(chunk):
                    continue
                add("unknown_habit")


def _rank_claims(t: str, named: set[str], tab: FactTable, cited: list[Fact], add: Any) -> None:
    if not named:
        return
    use_cohort = any(f.coll == "cohort_habit" for f in cited) and not any(f.coll == "habit" for f in cited)
    scope: dict[str, float] = {}
    for f in tab.facts.values():
        if f.coll == ("cohort_habit" if use_cohort else "habit") and f.role == "point" and f.path.endswith(".seconds"):
            scope[f.item or ""] = f.value
    pos = {k: v for k, v in scope.items() if v > 0}
    if not pos or not (named & set(pos)):
        return
    order = sorted(pos, key=lambda k: -pos[k])
    k = len(named & set(pos))
    if _RANK_TOP.search(t):
        if any(order.index(h) + 1 > k for h in named if h in order):
            add("rank_claim_false")
    if _RANK_LOW.search(t):
        n = len(order)
        if any(order.index(h) + 1 < n - k + 1 for h in named if h in order):
            add("rank_claim_false")
    if _SHARE_MOST.search(t):
        tot = sum(pos.values())
        if tot <= 0 or sum(pos[h] for h in named if h in pos) / tot < 0.5:
            add("share_claim_false")


_VALIDATORS: dict[int, tuple[dict[str, Any], jsonschema.Draft202012Validator]] = {}


def _validator(schema: dict[str, Any]) -> jsonschema.Draft202012Validator:
    """One compiled validator per schema object (``jsonschema.validate`` re-checks the schema on every call, which dominated the time)."""
    hit = _VALIDATORS.get(id(schema))
    if hit is not None and hit[0] is schema:
        return hit[1]
    v = jsonschema.Draft202012Validator(schema)
    if len(_VALIDATORS) > 64:
        _VALIDATORS.clear()
    _VALIDATORS[id(schema)] = (schema, v)
    return v


# ------------------------------------------------------------------------------------------------ the reply check
def check_reply(reply: Any, source: ExplainRequest | EvidencePacket | FactTable, *, schema: dict[str, Any] | None = None,
                menu: Iterable[str] | None = None) -> Verdict:
    """Check a model reply against the packet it was written from. ``source`` is the request (preferred, so ``question.asked_s`` is
    a citable fact), the packet or a prebuilt fact table. ``menu`` is the list of coach ids that apply; chosen ids outside it are
    dropped (the model proposes, code decides) and listed in ``dropped_actions``."""
    tab = source if isinstance(source, FactTable) else facts(source)
    req = source if isinstance(source, ExplainRequest) else None
    try:
        _validator(schema or REPLY_SCHEMA).validate(reply)
    except jsonschema.ValidationError:
        return Verdict(ok=False, schema_ok=False, rejected=[SentenceResult("reply", 0, ["schema"])])
    reply = expand_placeholders(reply, tab)
    ctx = _Ctx(tab, req)
    v = Verdict(ok=True, expanded=reply)
    counts = {"names": 0, "numbers": 0, "intervals": 0}
    for sec in reply["sections"]:
        for i, s in enumerate(sec["sentences"]):
            v.checked["sentences"] += 1
            codes = check_sentence(s["text"], list(s["uses"]), ctx, counts)
            if not s["uses"] and not codes:
                nums = [m for m in extract_mentions(s["text"]) if m.kind == "num"]
                if nums or any(named_things(s["text"]).values()):
                    codes.append("no_citation")
            if codes:
                v.rejected.append(SentenceResult(sec["kind"], i, codes))
    v.checked.update(counts)
    if menu is not None:
        allowed = set(menu)
        v.dropped_actions = [a for a in reply.get("coach_actions", []) if a not in allowed]
    v.ok = not v.rejected
    return v
