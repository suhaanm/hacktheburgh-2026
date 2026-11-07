"""SafePayload: the only shape of content that may leave this machine from the extension layers (PRV-1).

A ``SafePayload`` field may be only:

* ``int``, ``float``, ``bool`` (finite, bounded),
* a ``Literal[...]`` or ``enum.Enum`` of strings, ints or bools (a closed set written in code),
* a string annotated ``Vocab("name")``: it must be one of the values (or match the structured pattern) registered for
  that fixed vocabulary with ``register_vocabulary``,
* a list or tuple of those, a ``dict`` whose keys are vocabulary ids or literals, an optional of those, or another
  ``SafePayload``.

Any other string, ``Any``, ``bytes``, ``datetime``, free ``dict`` or ``object`` is refused when the class is *defined*
(``UnsafeFieldError``) and, for values, when the payload is *validated* (the strict validator rejects any string that is
not in a closed set). Errors name field paths and error kinds, never values.

What this does not do: it cannot tell whether an allowed value is *about* something private (a count of one's own
secret meetings is still a count), and a determined author could smuggle text through lists of integers. The list and
integer bounds below only limit that; the threat model is accidental leakage by honest code.
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
import re
import threading
import types
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, GetCoreSchemaHandler, ValidationError, model_validator
from pydantic_core import core_schema

from .patterns import scan_text

MAX_LIST_ITEMS = 64
MAX_DICT_ITEMS = 64
MAX_INT = 10**9
MAX_PAYLOAD_BYTES = 8192
MAX_VOCAB_VALUE_LEN = 64


class UnsafeFieldError(TypeError):
    """A payload class declares a field that could carry free text. Raised when the class is defined."""


class VocabularyError(ValueError):
    """A vocabulary was registered badly, or a value is not in its vocabulary."""


class PurposeError(ValueError):
    """A purpose was registered badly, or is unknown."""


# --------------------------------------------------------------------------------------------------------- vocabularies
_PROBES = (
    "alice", "Alice Smith", "alice@example.com", "Q3 budget review", "/Users/alice/notes.txt", "fix payroll bug for Acme",
    "Weekly sync with Bob", "hello world", "meeting", "customer", "project-x", "Acme Corp", "revenue_forecast",
)


@dataclass(frozen=True)
class _Vocabulary:
    name: str
    values: frozenset[str] | None
    pattern: re.Pattern[str] | None

    def accepts(self, value: str) -> bool:
        if len(value) > MAX_VOCAB_VALUE_LEN:
            return False
        if self.values is not None and value in self.values:
            return True
        return self.pattern is not None and self.pattern.fullmatch(value) is not None


_vocab_lock = threading.RLock()
_VOCABS: dict[str, _Vocabulary] = {}
_NAME = re.compile(r"^[a-z][a-z0-9_.]{0,40}$")


def register_vocabulary(name: str, values: Any = None, *, pattern: str | None = None, extend: bool = False) -> None:
    """Register a fixed vocabulary of ids.

    ``values``: a closed set of strings (each is itself scanned by the backstop, so an email address cannot be
    registered as an id). ``pattern``: a *structured* regex (full match); it is refused if it accepts any of a battery of
    ordinary words, names, emails, titles and paths, so ``^[a-z_]+$`` cannot be used as a loophole. Registering the same
    vocabulary again with the same content is a no-op; ``extend=True`` unions new values in.
    """
    if not _NAME.match(name):
        raise VocabularyError(f"vocabulary name {name!r} must look like 'calendar.template' (lower case, dots, underscores)")
    if values is None and pattern is None:
        raise VocabularyError(f"vocabulary {name!r} needs values or a pattern")
    vals: frozenset[str] | None = None
    if values is not None:
        items = [values] if isinstance(values, str) else list(values)
        for v in items:
            if not isinstance(v, str) or not v or len(v) > MAX_VOCAB_VALUE_LEN:
                raise VocabularyError(f"vocabulary {name!r}: values must be non-empty strings of at most {MAX_VOCAB_VALUE_LEN} characters")
            bad = scan_text(v, names=False)
            if bad:
                raise VocabularyError(f"vocabulary {name!r}: a value looks like personal data ({', '.join(sorted(set(bad)))}); ids must be plain codes")
        vals = frozenset(items)
    rx: re.Pattern[str] | None = None
    if pattern is not None:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            raise VocabularyError(f"vocabulary {name!r}: bad pattern ({exc})") from exc
        loose = [p for p in _PROBES if rx.fullmatch(p)]
        if loose:
            raise VocabularyError(
                f"vocabulary {name!r}: the pattern accepts ordinary words or names, so it would let free text through. "
                "Use a closed set of values, or a structured pattern (for example a hash with a fixed prefix and length)."
            )
    with _vocab_lock:
        old = _VOCABS.get(name)
        if old is None:
            _VOCABS[name] = _Vocabulary(name, vals, rx)
            return
        merged_vals = old.values
        if vals is not None:
            if old.values is not None and old.values != vals and not extend:
                raise VocabularyError(f"vocabulary {name!r} is already registered with different values; pass extend=True to add to it")
            merged_vals = (old.values | vals) if (extend and old.values is not None) else vals
        merged_rx = old.pattern
        if rx is not None:
            if old.pattern is not None and old.pattern.pattern != rx.pattern and not extend:
                raise VocabularyError(f"vocabulary {name!r} is already registered with a different pattern")
            merged_rx = rx
        _VOCABS[name] = _Vocabulary(name, merged_vals, merged_rx)


def vocabulary_values(name: str) -> frozenset[str] | None:
    with _vocab_lock:
        v = _VOCABS.get(name)
    if v is None:
        raise VocabularyError(f"vocabulary {name!r} is not registered")
    return v.values


def vocabularies() -> dict[str, dict[str, Any]]:
    """Registered vocabularies, for docs and the Privacy screen: name -> {values, pattern}."""
    with _vocab_lock:
        return {
            n: {"values": sorted(v.values) if v.values is not None else None, "pattern": v.pattern.pattern if v.pattern else None}
            for n, v in sorted(_VOCABS.items())
        }


class Vocab:
    """Annotation marker: ``Annotated[str, Vocab("calendar.template")]``.

    The check runs at validation time against the registry (so tracks can register after importing), and the error never
    echoes the offending value.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"Vocab({self.name!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Vocab) and other.name == self.name

    def __hash__(self) -> int:
        return hash(("Vocab", self.name))

    def _check(self, value: str) -> str:
        with _vocab_lock:
            v = _VOCABS.get(self.name)
        if v is None:
            raise ValueError(f"vocabulary {self.name!r} is not registered")
        if not v.accepts(value):
            raise ValueError(f"not an id in the fixed vocabulary {self.name!r}")
        return value

    def __get_pydantic_core_schema__(self, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(self._check, handler(source))


@dataclass(frozen=True)
class Bucket:
    """Annotation marker for generalised fields (see ``bucket.py``). ``kind`` names the rule."""

    kind: str


# --------------------------------------------------------------------------------------------------------- field checks
def _lint_literal_values(where: str, values: list[Any]) -> str | None:
    for v in values:
        if v is None or isinstance(v, (bool, int)):
            continue
        if not isinstance(v, str):
            return f"{where}: literal values must be strings, ints or bools"
        if len(v) > MAX_VOCAB_VALUE_LEN:
            return f"{where}: a literal value is longer than {MAX_VOCAB_VALUE_LEN} characters"
        bad = scan_text(v, names=False)
        if bad:
            return f"{where}: a literal value looks like personal data ({', '.join(sorted(set(bad)))})"
    return None


def _problem(tp: Any, metadata: tuple[Any, ...], where: str) -> str | None:
    """Why ``tp`` is not an allowed field type, or None when it is."""
    origin = get_origin(tp)
    if origin is Annotated:
        base, *meta = get_args(tp)
        return _problem(base, tuple(metadata) + tuple(meta), where)
    if tp is bool or tp is int or tp is float or tp is None or tp is type(None):
        return None
    if tp is str:
        if any(isinstance(m, Vocab) for m in metadata):
            return None
        return (f"{where}: a free string field is not allowed. Use Literal[...] for a closed set, an Enum, "
                f"or Annotated[str, Vocab('<vocabulary>')] for an id from a fixed vocabulary.")
    if origin is Literal:
        return _lint_literal_values(where, list(get_args(tp)))
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return _lint_literal_values(where, [m.value for m in tp])
    if origin in (Union, types.UnionType):
        for a in get_args(tp):
            p = _problem(a, metadata, where)
            if p:
                return p
        return None
    if origin in (list, tuple, set, frozenset):
        args = [a for a in get_args(tp) if a is not Ellipsis]
        if not args:
            return f"{where}: untyped list or tuple is not allowed"
        for a in args:
            p = _problem(a, metadata, where)
            if p:
                return p
        return None
    if origin is dict:
        args = get_args(tp)
        if len(args) != 2:
            return f"{where}: untyped dict is not allowed"
        key, val = args
        kp = _key_problem(key, metadata, where)
        return kp or _problem(val, metadata, where)
    if isinstance(tp, type) and issubclass(tp, SafePayload):
        return None
    name = getattr(tp, "__name__", repr(tp))
    return f"{where}: type {name} is not allowed in a SafePayload (only int, float, bool, Literal, Enum, Vocab ids and lists of those)"


def _key_problem(tp: Any, metadata: tuple[Any, ...], where: str) -> str | None:
    origin = get_origin(tp)
    if origin is Annotated:
        base, *meta = get_args(tp)
        return _key_problem(base, tuple(metadata) + tuple(meta), where)
    if tp is str:
        if any(isinstance(m, Vocab) for m in metadata):
            return None
        return f"{where}: dict keys must be Literal, Enum or Annotated[str, Vocab(...)], never free strings"
    if origin is Literal or (isinstance(tp, type) and issubclass(tp, enum.Enum)):
        return _problem(tp, metadata, where)
    return f"{where}: dict keys must be Literal, Enum or Annotated[str, Vocab(...)]"


def _bucket_kinds(tp: Any, metadata: tuple[Any, ...] = ()) -> set[str]:
    kinds = {m.kind for m in metadata if isinstance(m, Bucket)}
    origin = get_origin(tp)
    if origin is Annotated:
        base, *meta = get_args(tp)
        return kinds | _bucket_kinds(base, tuple(meta))
    for a in get_args(tp):
        if a is not Ellipsis:
            kinds |= _bucket_kinds(a)
    return kinds


def _has_numeric(tp: Any) -> bool:
    origin = get_origin(tp)
    if origin is Annotated:
        return _has_numeric(get_args(tp)[0])
    if tp is int or tp is float:
        return True
    return any(_has_numeric(a) for a in get_args(tp) if a is not Ellipsis)


# --------------------------------------------------------------------------------------------------------- the base class
class SafePayload(BaseModel):
    """Base class for everything that may be sent to a remote model. Subclass it and declare only allowed fields."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True, validate_default=True, allow_inf_nan=False,
    )

    #: Optional human description shown on the Privacy screen.
    description: ClassVar[str] = ""

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cfg = cls.model_config
        if cfg.get("extra") != "forbid" or cfg.get("strict") is not True or cfg.get("arbitrary_types_allowed"):
            raise UnsafeFieldError(
                f"{cls.__name__}: a SafePayload must keep extra='forbid' and strict=True and must not allow arbitrary types "
                "(overriding them would let free text in)")
        for name, info in cls.model_fields.items():
            if name == "model_config":
                continue
            problem = _problem(info.annotation, tuple(info.metadata), f"{cls.__name__}.{name}")
            if problem:
                raise UnsafeFieldError(problem)

    @model_validator(mode="after")
    def _bounds(self) -> "SafePayload":
        for name in type(self).model_fields:
            _check_bounds(getattr(self, name), name)
        return self

    # ---- helpers used by egress and the ledger
    @classmethod
    def schema_id(cls) -> str:
        """Stable id: class name plus a short hash of the JSON schema, so a change of fields changes the id."""
        raw = json.dumps(cls.model_json_schema(), sort_keys=True, separators=(",", ":"))
        return f"{cls.__name__}#{hashlib.sha256(raw.encode()).hexdigest()[:8]}"

    @classmethod
    def field_names(cls) -> list[str]:
        return list(cls.model_fields)

    @classmethod
    def bucketed_fields(cls) -> dict[str, list[str]]:
        """Field name -> bucket kinds applied to it (empty for fields that are sent as they are)."""
        out: dict[str, list[str]] = {}
        for name, info in cls.model_fields.items():
            kinds = _bucket_kinds(info.annotation, tuple(info.metadata))
            if kinds:
                out[name] = sorted(kinds)
        return out

    @classmethod
    def unbucketed_numeric_fields(cls) -> list[str]:
        """Numeric fields sent without a generalisation rule (informational, shown in the ledger line)."""
        buck = cls.bucketed_fields()
        return [n for n, i in cls.model_fields.items() if n not in buck and _has_numeric(i.annotation)]

    def to_wire(self) -> dict[str, Any]:
        """The JSON-ready dict that is sent and recorded (after bucketing)."""
        return json.loads(self.model_dump_json())


def _check_bounds(value: Any, where: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        if abs(value) > MAX_INT:
            raise ValueError(f"{where}: integer is outside the allowed range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{where}: number is not finite")
        if abs(value) > MAX_INT:
            raise ValueError(f"{where}: number is outside the allowed range")
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError(f"{where}: more than {MAX_LIST_ITEMS} list items")
        for i, v in enumerate(value):
            _check_bounds(v, f"{where}[{i}]")
        return
    if isinstance(value, dict):
        if len(value) > MAX_DICT_ITEMS:
            raise ValueError(f"{where}: more than {MAX_DICT_ITEMS} entries")
        for k, v in value.items():
            _check_bounds(v, f"{where}.{k}")
        return
    if isinstance(value, enum.Enum):
        return
    if isinstance(value, SafePayload):
        return


def explain_validation_error(exc: ValidationError) -> list[str]:
    """Plain lines naming field paths and error kinds, never the offending values."""
    out = []
    for e in exc.errors(include_input=False, include_url=False, include_context=False):
        loc = ".".join(str(x) for x in e.get("loc", ())) or "(payload)"
        msg = str(e.get("msg", "invalid"))
        out.append(f"{loc}: {msg}")
    return out[:8]


# --------------------------------------------------------------------------------------------------------- purposes
DEFAULT_INSTRUCTIONS = (
    "You receive one JSON object of numbers, codes and fixed ids produced by local code. Use only what it contains. "
    "Do not invent names, places, dates or facts, and do not ask for more information. Answer in the requested JSON format."
)
_PURPOSE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
Method = Literal["plan", "check"]


@dataclass(frozen=True)
class Purpose:
    name: str
    model: type[SafePayload]
    instructions: str
    response_schema: dict[str, Any] | None = None
    method: Method = "plan"
    description: str = ""
    schema: str = field(default="")

    def public(self) -> dict[str, Any]:
        return {
            "purpose": self.name, "schema": self.schema, "method": self.method, "description": self.description,
            "fields": self.model.field_names(), "bucketed": self.model.bucketed_fields(),
            "unbucketed_numeric": self.model.unbucketed_numeric_fields(),
        }


_purpose_lock = threading.RLock()
_PURPOSES: dict[str, Purpose] = {}


def register_payload(
    purpose: str, model: type[SafePayload], *, instructions: str = DEFAULT_INSTRUCTIONS,
    response_schema: dict[str, Any] | None = None, method: Method = "plan", description: str = "", replace: bool = False,
) -> Purpose:
    """Register what may be sent for ``purpose`` (for example ``calendar.suggestion_wording``).

    ``instructions`` is static text written in code; it is scanned by the backstop here and again on every send. Unknown
    purposes are refused by ``egress.send``. Registering the same purpose again with an identical model is a no-op.
    """
    if not _PURPOSE.match(purpose):
        raise PurposeError(f"purpose {purpose!r} must look like 'calendar.suggestion_wording'")
    if not (isinstance(model, type) and issubclass(model, SafePayload)) or model is SafePayload:
        raise PurposeError(f"purpose {purpose!r}: the payload model must be a subclass of SafePayload")
    if method not in ("plan", "check"):
        raise PurposeError(f"purpose {purpose!r}: method must be 'plan' or 'check'")
    if method == "check" and response_schema is None:
        raise PurposeError(f"purpose {purpose!r}: a 'check' purpose needs a response_schema")
    bad = scan_text(instructions)
    if bad:
        raise PurposeError(f"purpose {purpose!r}: the instructions trip the privacy backstop ({', '.join(sorted(set(bad)))})")
    entry = Purpose(purpose, model, instructions, response_schema, method, description or model.description, model.schema_id())
    with _purpose_lock:
        old = _PURPOSES.get(purpose)
        if old is not None and not replace:
            same = old.schema == entry.schema and old.instructions == entry.instructions and old.method == entry.method \
                and old.response_schema == entry.response_schema
            if not same:
                raise PurposeError(f"purpose {purpose!r} is already registered with a different payload; pass replace=True to change it")
            return old
        _PURPOSES[purpose] = entry
    return entry


def get_purpose(purpose: str) -> Purpose:
    with _purpose_lock:
        p = _PURPOSES.get(purpose)
    if p is None:
        raise PurposeError(f"unknown purpose {purpose!r}: nothing is allowed to leave for it. Register it with register_payload first")
    return p


def purposes() -> dict[str, Purpose]:
    with _purpose_lock:
        return dict(_PURPOSES)


def unregister_purpose(purpose: str) -> None:
    """Test helper."""
    with _purpose_lock:
        _PURPOSES.pop(purpose, None)
