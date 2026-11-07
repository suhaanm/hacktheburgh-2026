"""S-24 (functional blocker for R1, FIXED: a countdown that re-reads the front app): the scripted R1 refuses at its first action when it is started from the shell of the app that
is frontmost when the owner presses Enter (the Claude app, or a terminal), because MacActuator._guard requires the TARGET to be frontmost and
mac_check has no countdown and no activation step. The owner has about 0.3 s (one screenshot) to click TextEdit. Real run_check + real QuartzBackend
on a fake OS whose frontmost app is the shell. The fix is a visible countdown that polls the kill file and re-reads the front app, or an explicit
`open -a TextEdit` step, then the same guards."""
from __future__ import annotations

from understudy_agent.tiers.mac_check import run_check, run_description
from understudy_agent.tiers.owner_present import issue_owner_token


async def test_r1_started_from_the_shell_gives_the_owner_time_to_bring_the_target_forward(fake_os, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_REAL_ACTUATOR", "1")
    fake_os.front = "Claude"                                            # where the command was typed
    fake_os.win("TextEdit", 100, 100, 400, 300)
    tok = issue_owner_token(run_description("TextEdit", (600, 500), "hello"))
    out = await run_check("TextEdit", (600, 500), "hello", real=True, owner_token=tok, countdown_s=1.2)
    assert "frontmost app is 'Claude'" not in str(out), f"R1 cannot start from the shell: {out.get('reason')}"
