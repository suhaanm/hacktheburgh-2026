"""Item schemas: what fields a source's ``RawItem`` may carry, and which of them are sensitive text.

A manifest's ``schema`` names one of these. ``sensitive=True`` means raw content that may be held in memory while an
item is being turned into numbers and enums, and must never be logged, stored, queued or sent anywhere (PRV-1, PRV-4).
Everything else is a number, a boolean or an enum and is what a digest may keep.

Other tracks register their own item schemas with ``register_schema`` (the git adapter registers ``commit.v1``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

TYPES = ("str", "int", "float", "bool", "enum", "list_str")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    sensitive: bool = False
    enum: tuple[str, ...] = ()
    required: bool = False


@dataclass(frozen=True)
class ItemSchema:
    id: str
    kind: str
    fields: dict[str, FieldSpec] = field(default_factory=dict)
    description: str = ""

    @property
    def sensitive_fields(self) -> frozenset[str]:
        return frozenset(n for n, f in self.fields.items() if f.sensitive)


def _schema(id_: str, kind: str, description: str, *specs: FieldSpec) -> ItemSchema:
    return ItemSchema(id_, kind, {s.name: s for s in specs}, description)


SHOW_AS = ("free", "tentative", "busy", "oof", "working_elsewhere")
STATUS = ("confirmed", "tentative", "cancelled")
RESPONSE = ("organizer", "accepted", "tentative", "declined", "none")
PROVIDER = ("none", "teams", "zoom", "meet", "other")
SENSITIVITY = ("normal", "private", "personal", "confidential")
SHELL = ("zsh", "bash", "fish", "unknown")

CALENDAR_EVENT_V1 = _schema(
    "calendar_event.v1", "calendar_event",
    "One calendar entry (a single occurrence; recurring series are already expanded). Titles, people and places are raw text.",
    FieldSpec("title", "str", sensitive=True),
    FieldSpec("organizer", "str", sensitive=True),
    FieldSpec("attendees", "list_str", sensitive=True),
    FieldSpec("location", "str", sensitive=True),
    FieldSpec("series_id", "str", sensitive=True),
    FieldSpec("source_id", "str", sensitive=True),
    FieldSpec("n_attendees", "int"),
    FieldSpec("all_day", "bool"),
    FieldSpec("recurring", "bool"),
    FieldSpec("online", "bool"),
    FieldSpec("show_as", "enum", enum=SHOW_AS),
    FieldSpec("status", "enum", enum=STATUS),
    FieldSpec("response", "enum", enum=RESPONSE),
    FieldSpec("provider", "enum", enum=PROVIDER),
    FieldSpec("sensitivity", "enum", enum=SENSITIVITY),
    FieldSpec("attended_s", "int"),
)

SHELL_TIME_V1 = _schema(
    "shell_time.v1", "shell_time",
    "A shell command's timestamp (CAP-8). The command text is discarded while parsing and never reaches an item.",
    FieldSpec("shell", "enum", enum=SHELL),
    FieldSpec("duration_s", "int"),
)

COMMIT_V1 = _schema(
    "commit.v1", "commit",
    "One commit from a local repository (registered here for the git-analysis track; it may register its own).",
    FieldSpec("sha", "str", sensitive=True),
    FieldSpec("author", "str", sensitive=True),
    FieldSpec("message", "str", sensitive=True),
    FieldSpec("paths", "list_str", sensitive=True),
    FieldSpec("n_files", "int"),
    FieldSpec("additions", "int"),
    FieldSpec("deletions", "int"),
    FieldSpec("test_files", "int"),
    FieldSpec("is_revert", "bool"),
    FieldSpec("is_merge", "bool"),
)

_REGISTRY: dict[str, ItemSchema] = {s.id: s for s in (CALENDAR_EVENT_V1, SHELL_TIME_V1, COMMIT_V1)}


def register_schema(schema: ItemSchema) -> None:
    """Add or replace an item schema (another track's source registers its own)."""
    _REGISTRY[schema.id] = schema


def get_schema(schema_id: str) -> ItemSchema | None:
    return _REGISTRY.get(schema_id)


def schema_ids() -> list[str]:
    return sorted(_REGISTRY)


_PY = {"str": str, "int": int, "float": (int, float), "bool": bool}


def check_item(schema: ItemSchema, kind: str, fields: dict[str, Any]) -> list[str]:
    """Problems with an item against its schema, described by field name and type only (never by value)."""
    out: list[str] = []
    if kind != schema.kind:
        out.append(f"kind is not {schema.kind}")
    for name, value in fields.items():
        spec = schema.fields.get(name)
        if spec is None:
            out.append(f"unknown field {name}")
            continue
        if spec.type == "enum":
            if value not in spec.enum:
                out.append(f"field {name} is not one of the allowed values")
        elif spec.type == "list_str":
            if not (isinstance(value, (list, tuple)) and all(isinstance(x, str) for x in value)):
                out.append(f"field {name} is not a list of text")
        elif spec.type == "bool":
            if not isinstance(value, bool):
                out.append(f"field {name} is not a bool")
        elif spec.type in ("int", "float"):
            if isinstance(value, bool) or not isinstance(value, _PY[spec.type]):
                out.append(f"field {name} is not a {spec.type}")
        elif not isinstance(value, str):
            out.append(f"field {name} is not text")
    for name, spec in schema.fields.items():
        if spec.required and name not in fields:
            out.append(f"missing field {name}")
    return out


def strip_sensitive(schema: ItemSchema, fields: dict[str, Any]) -> dict[str, Any]:
    """The non-sensitive part of an item: what a digest may keep."""
    sens = schema.sensitive_fields
    return {k: v for k, v in fields.items() if k not in sens}


def sensitive_names(schema_ids_: Iterable[str] | None = None) -> set[str]:
    ids = list(schema_ids_) if schema_ids_ is not None else list(_REGISTRY)
    out: set[str] = set()
    for i in ids:
        s = _REGISTRY.get(i)
        if s:
            out |= s.sensitive_fields
    return out
