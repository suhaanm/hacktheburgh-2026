"""S-08 (High, fixed): the 7 Nov failure mode. `mac_check --real` used to return ok:true as soon as no guard fired, with no read-back. Runs the REAL
run_check and the REAL QuartzBackend over a fake OS. A real run now needs the owner's one-time token (S-14), which the test issues exactly as the
dry run would. ok must be true only when the document read back through the OS equals what was typed; a document that cannot be read back is not
proven, and one that reads back something else is a failure."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from understudy_agent.tiers.mac_check import run_check, run_description
from understudy_agent.tiers.owner_present import issue_owner_token


def serve_osascript(monkeypatch, fake_os, document):
    base = subprocess.run          # the FakeOS stub: screencapture bytes; osascript answers with `document` (None = AppleScript fails)
    def run(args, *a, **k):
        if Path(str(args[0])).name == "osascript":
            if document is None:
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0, stdout=document, stderr="")
        return base(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", run)


async def real_run(fake_os):
    fake_os.win("TextEdit", 100, 100, 400, 300)
    tok = issue_owner_token(run_description("TextEdit", (600, 500), "hello"))
    return await run_check("TextEdit", (600, 500), "hello", real=True, owner_token=tok, countdown_s=0)       # px (600,500) / scale 2 = pt (300,250)


@pytest.mark.parametrize("document,ok,post", [(None, False, "unavailable"), ("something else", False, "failed"), ("hello", True, "passed")])
async def test_ok_follows_the_read_back_and_nothing_else(fake_os, monkeypatch, document, ok, post):
    monkeypatch.setenv("UNDERSTUDY_REAL_ACTUATOR", "1")
    serve_osascript(monkeypatch, fake_os, document)
    out = await real_run(fake_os)
    assert fake_os.typed() == "hello", out                 # the keystrokes were posted in every case: the guards alone say nothing
    assert (out["ok"], out.get("postcondition")) == (ok, post), out


async def test_a_real_run_without_the_owner_token_types_nothing(fake_os, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_REAL_ACTUATOR", "1")
    fake_os.win("TextEdit", 100, 100, 400, 300)
    out = await run_check("TextEdit", (600, 500), "hello", real=True, countdown_s=0)
    assert out["ok"] is False and fake_os.typed() == "" and fake_os.clicks() == []
