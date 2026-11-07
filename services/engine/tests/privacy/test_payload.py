from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated, Any, Literal

import pytest
from pydantic import ValidationError

from understudy_engine.privacy import payload as P
from understudy_engine.privacy.bucket import Count, DurationMin, Ratio
from understudy_engine.privacy.payload import (
    SafePayload, UnsafeFieldError, Vocab, VocabularyError, PurposeError, explain_validation_error, get_purpose,
    register_payload, register_vocabulary, unregister_purpose,
)


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


# --------------------------------------------------------------------------- class-definition refusals
@pytest.mark.parametrize("ann", [
    str, dict, dict[str, int], list[str], Any, bytes, datetime, object, Annotated[str, "just a note"], str | None,
    tuple, list, set[str],
])
def test_forbidden_field_types_are_refused_when_the_class_is_defined(ann):
    with pytest.raises(UnsafeFieldError):
        type("Bad", (SafePayload,), {"__annotations__": {"x": ann}})


def test_free_string_refusal_names_the_field_and_the_fix():
    with pytest.raises(UnsafeFieldError, match=r"Bad\.title.*free string.*Vocab"):
        type("Bad", (SafePayload,), {"__annotations__": {"title": str}})


def test_literal_with_personal_looking_value_is_refused():
    with pytest.raises(UnsafeFieldError, match="personal data"):
        type("Bad", (SafePayload,), {"__annotations__": {"x": Literal["ada@example.com", "b"]}})
    with pytest.raises(UnsafeFieldError, match="personal data"):
        type("Bad", (SafePayload,), {"__annotations__": {"x": Literal["/Users/ada/notes"]}})


def test_enum_with_non_scalar_or_personal_value_is_refused():
    class Evil(enum.Enum):
        A = "https://example.org/x"

    with pytest.raises(UnsafeFieldError):
        type("Bad", (SafePayload,), {"__annotations__": {"x": Evil}})


def test_dict_with_free_string_keys_is_refused_but_vocab_keys_are_fine():
    register_vocabulary("t.keys", ["a", "b"])
    with pytest.raises(UnsafeFieldError, match="keys"):
        type("Bad", (SafePayload,), {"__annotations__": {"x": dict[str, int]}})
    ok = type("Ok", (SafePayload,), {"__annotations__": {"x": dict[Annotated[str, Vocab("t.keys")], int]}})
    assert ok(x={"a": 1}).x == {"a": 1}


# --------------------------------------------------------------------------- allowed shapes and strict validation
class Good(SafePayload):
    n: int
    f: float
    b: bool
    c: Literal["a", "b"]
    e: Color
    items: list[int]
    maybe: Literal["x", "y"] | None = None
    count: Count = 0
    mins: DurationMin = 0
    ratio: Ratio = 0.0


def test_allowed_shapes_validate():
    g = Good(n=1, f=2.5, b=True, c="a", e=Color.RED, items=[1, 2, 3])
    assert g.to_wire()["e"] == "red"
    assert g.to_wire()["count"] == "lt5"


def test_a_free_string_in_a_closed_field_is_rejected_and_the_error_never_echoes_it():
    secret = "Ada Lovelace's performance review"
    with pytest.raises(ValidationError) as ei:
        Good(n=1, f=1.0, b=True, c=secret, e=Color.RED, items=[])
    assert secret not in str(ei.value)
    assert "Lovelace" not in " ".join(explain_validation_error(ei.value))


def test_strict_mode_does_not_coerce_strings_to_numbers_or_bools():
    for bad in ({"n": "5"}, {"f": "1.0"}, {"b": "true"}, {"b": 1}, {"n": True}, {"n": 1.0}):
        base = dict(n=1, f=1.0, b=True, c="a", e=Color.RED, items=[])
        base.update(bad)
        with pytest.raises(ValidationError):
            Good(**base)


def test_extra_fields_are_forbidden_and_models_are_frozen():
    with pytest.raises(ValidationError):
        Good(n=1, f=1.0, b=True, c="a", e=Color.RED, items=[], title="x")
    g = Good(n=1, f=1.0, b=True, c="a", e=Color.RED, items=[])
    with pytest.raises(ValidationError):
        g.n = 2


def test_bounds_on_lists_numbers_and_non_finite_floats():
    base = dict(n=1, f=1.0, b=True, c="a", e=Color.RED, items=[])
    with pytest.raises(ValidationError):
        Good(**{**base, "items": list(range(P.MAX_LIST_ITEMS + 1))})
    with pytest.raises(ValidationError):
        Good(**{**base, "n": P.MAX_INT + 1})
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValidationError):
            Good(**{**base, "f": bad})


def test_nested_safe_payload_is_allowed_and_checked():
    class Inner(SafePayload):
        k: Literal["a", "b"]

    class Outer(SafePayload):
        inner: Inner
        many: list[Inner]

    o = Outer(inner=Inner(k="a"), many=[Inner(k="b")])
    assert o.to_wire() == {"inner": {"k": "a"}, "many": [{"k": "b"}]}
    with pytest.raises(ValidationError):
        Outer(inner={"k": "free text"}, many=[])


# --------------------------------------------------------------------------- vocabularies
def test_vocab_accepts_registered_ids_only():
    register_vocabulary("t.fruit", ["apple", "pear"])

    class M(SafePayload):
        fruit: Annotated[str, Vocab("t.fruit")]
        many: list[Annotated[str, Vocab("t.fruit")]] = []

    assert M(fruit="apple", many=["pear"]).fruit == "apple"
    with pytest.raises(ValidationError):
        M(fruit="banana")
    with pytest.raises(ValidationError):
        M(fruit="apple", many=["Alice Smith"])


def test_unregistered_vocabulary_fails_at_validation_with_a_plain_message():
    class M(SafePayload):
        x: Annotated[str, Vocab("t.never_registered")]

    with pytest.raises(ValidationError) as ei:
        M(x="a")
    assert "not registered" in str(ei.value)


def test_registering_values_that_look_like_personal_data_is_refused():
    for bad in ("ada@example.com", "/Users/ada/secret.txt", "https://example.org", "07700 900123"):
        with pytest.raises(VocabularyError):
            register_vocabulary("t.bad", [bad])


@pytest.mark.parametrize("loose", [r"[a-z]+", r"[A-Za-z ]+", r".*", r"[a-z_]{1,30}", r"[\w ]+", r"[a-z0-9_\-]+"])
def test_loose_patterns_are_refused_because_they_would_let_words_through(loose):
    with pytest.raises(VocabularyError, match="free text"):
        register_vocabulary("t.loose", pattern=loose)


def test_structured_pattern_is_accepted_and_enforced():
    register_vocabulary("t.hash", pattern=r"[hd]:[0-9a-f]{8,32}")

    class M(SafePayload):
        h: Annotated[str, Vocab("t.hash")]

    assert M(h="h:0123abcd").h == "h:0123abcd"
    for bad in ("alice", "h:xyz", "h:012", "Alice Smith"):
        with pytest.raises(ValidationError):
            M(h=bad)


def test_registering_the_same_vocabulary_twice_is_idempotent_and_conflicts_need_extend():
    register_vocabulary("t.same", ["a", "b"])
    register_vocabulary("t.same", ["a", "b"])
    with pytest.raises(VocabularyError, match="extend"):
        register_vocabulary("t.same", ["c"])
    register_vocabulary("t.same", ["c"], extend=True)
    assert P.vocabulary_values("t.same") == frozenset({"a", "b", "c"})


def test_overlong_vocab_value_is_rejected_at_validation():
    register_vocabulary("t.len", pattern=r"x:[0-9a-f]{8,200}")

    class M(SafePayload):
        h: Annotated[str, Vocab("t.len")]

    with pytest.raises(ValidationError):
        M(h="x:" + "a" * 100)


# --------------------------------------------------------------------------- purposes
class Tiny(SafePayload):
    n: int


def test_unknown_purpose_is_refused():
    with pytest.raises(PurposeError, match="unknown purpose"):
        get_purpose("nope.nothing")


def test_register_payload_validates_names_models_and_instructions():
    with pytest.raises(PurposeError):
        register_payload("badname", Tiny)
    with pytest.raises(PurposeError):
        register_payload("t.x", dict)  # type: ignore[arg-type]
    with pytest.raises(PurposeError):
        register_payload("t.x", SafePayload)
    with pytest.raises(PurposeError, match="backstop"):
        register_payload("t.x", Tiny, instructions="mail the results to ada@example.com")
    with pytest.raises(PurposeError, match="response_schema"):
        register_payload("t.x", Tiny, method="check")


def test_register_payload_is_idempotent_but_refuses_silent_replacement():
    unregister_purpose("t.reg")
    a = register_payload("t.reg", Tiny)
    assert register_payload("t.reg", Tiny) is a

    class Other(SafePayload):
        m: int

    with pytest.raises(PurposeError, match="already registered"):
        register_payload("t.reg", Other)
    assert register_payload("t.reg", Other, replace=True).model is Other
    unregister_purpose("t.reg")


def test_schema_id_changes_when_fields_change():
    class A(SafePayload):
        x: int

    class A2(SafePayload):
        x: int
        y: int

    assert A.schema_id().split("#")[0] == "A"
    assert A.schema_id() != A2.schema_id().replace("A2", "A")


def test_bucketed_and_unbucketed_fields_are_reported():
    class M(SafePayload):
        a: Count
        b: int
        c: Literal["x"]

    assert M.bucketed_fields() == {"a": ["count_lt5"]}
    assert M.unbucketed_numeric_fields() == ["b"]


def test_every_registered_vocabulary_value_purpose_instruction_and_field_name_passes_the_backstop():
    from understudy_engine.privacy.testing import assert_vocabularies_clean

    assert_vocabularies_clean()


def test_assert_vocabularies_clean_would_notice_a_bad_one():
    from understudy_engine.privacy.testing import assert_vocabularies_clean

    class Named(SafePayload):
        password_hint_count: int = 0

    unregister_purpose("t.badnames")
    register_payload("t.badnames", Named)
    try:
        with pytest.raises(AssertionError, match="password_hint_count"):
            assert_vocabularies_clean()
    finally:
        unregister_purpose("t.badnames")
