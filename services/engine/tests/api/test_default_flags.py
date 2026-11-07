"""D48 (owner, 7 Nov 2026): the running product has its layers on without environment variables; an explicit 0 still turns one off."""
from __future__ import annotations

from understudy_engine.api.flags import DEFAULT_ON, apply_default_flags, extension_flags

NEVER_DEFAULTED = (
    "UNDERSTUDY_REAL_ACTUATOR", "ALONGSIDE_AGENCY_LOOP", "UNDERSTUDY_JXA_CLICK", "UNDERSTUDY_LEGACY_REMOTE",
    "UNDERSTUDY_FLAG_WAKE", "UNDERSTUDY_FLAG_SCAM", "UNDERSTUDY_FLAG_FILES", "UNDERSTUDY_VOICE_DEBUG_TEXT",
    "UNDERSTUDY_CU_FRAME_HINT", "UNDERSTUDY_INSIGHTS_HELDOUT",
)


def test_unset_flags_become_on_and_every_layer_follows():
    env: dict[str, str] = {}
    changed = apply_default_flags(env)
    assert sorted(changed) == sorted(DEFAULT_ON)
    assert all(env[n] == "1" for n in DEFAULT_ON)
    flags = extension_flags(lambda name: env.get(name, "").strip().lower() in ("1", "true", "yes", "on"))
    assert flags and all(flags.values())


def test_an_explicit_value_wins_including_zero_and_empty_is_filled():
    env = {"UNDERSTUDY_X": "0", "UNDERSTUDY_VOICE": "0", "UNDERSTUDY_X_LIVE": "", "UNDERSTUDY_X_GEMINI": "1"}
    apply_default_flags(env)
    assert env["UNDERSTUDY_X"] == "0" and env["UNDERSTUDY_VOICE"] == "0"
    assert env["UNDERSTUDY_X_LIVE"] == "1" and env["UNDERSTUDY_X_GEMINI"] == "1"


def test_safety_arm_switches_legacy_remote_and_guards_are_never_defaulted():
    env: dict[str, str] = {}
    apply_default_flags(env)
    for name in NEVER_DEFAULTED:
        assert name not in env
        assert name not in DEFAULT_ON


def test_applying_defaults_twice_changes_nothing_the_second_time():
    env: dict[str, str] = {}
    apply_default_flags(env)
    assert apply_default_flags(env) == []
