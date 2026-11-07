"""SOUND (passes): R0 over the REAL QuartzBackend (fake OS) posts no event of any kind: every write on the ReadOnlyBackend raises, run_r0 attempts none,
and an attempted write is counted, not performed. The preflight rehearsal also passes with a fake desktop and fails without the owner's attestations."""
from __future__ import annotations

import pytest

from understudy_agent.tiers.computer_use import ActuatorRefused, QuartzBackend
from understudy_agent.tiers.real_rungs import ReadOnlyBackend, run_r0


def test_r0_reads_the_real_window_list_and_posts_nothing(fake_os):
    fake_os.win("TextEdit", 100, 100, 400, 300)
    out = run_r0("TextEdit", [(600, 500)], QuartzBackend())
    assert out["all_in_target"] and out["events"] == 0 and fake_os.posted == [], out


def test_every_write_on_the_read_only_backend_raises_and_posts_nothing(fake_os):
    ro = ReadOnlyBackend(QuartzBackend())
    for call in (lambda: ro.mouse("down", 1, 1), lambda: ro.type_text("x"), lambda: ro.key(["enter"]), lambda: ro.scroll(0, 5)):
        with pytest.raises(ActuatorRefused):
            call()
    assert fake_os.posted == [] and len(ro.refused) == 4
    with pytest.raises(AttributeError):
        ro.CGEventPost                                     # nothing outside the reads is forwarded to the real backend
