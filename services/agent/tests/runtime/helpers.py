"""Shared test helpers: a tiny git repo, canary tokens, and a test-only exemplar whose scripts sleep."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from understudy_agent.runtime.exemplars.base import Exemplar, Menu, WorkspaceNeeds, register_exemplar, register_menu
from understudy_agent.runtime.results import register_schema, register_verifier
from understudy_agent.runtime.spec import Check, RoleDef, register_role


def git(cwd: Path, *args: str, date: str | None = None) -> str:
    import os

    env = {"PATH": os.environ["PATH"], "HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "Ada", "GIT_AUTHOR_EMAIL": "ada@example.test", "GIT_COMMITTER_NAME": "Ada",
           "GIT_COMMITTER_EMAIL": "ada@example.test"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def tiny_repo(dest: Path, *, readme: str = "A tiny repo.\n") -> Path:
    """Three commits: a feature without a test, a fix, and a test."""
    dest.mkdir(parents=True, exist_ok=True)
    git(dest, "init", "-q", "-b", "main")
    (dest / "README.md").write_text(readme)
    (dest / "src").mkdir()
    (dest / "src" / "billing.py").write_text("def total(xs):\n    return sum(xs)\n")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "Add billing total", date="2026-10-01T10:00:00Z")
    (dest / "src" / "billing.py").write_text("def total(xs):\n    return round(sum(xs), 2)\n")
    git(dest, "commit", "-aq", "-m", "Fix rounding in billing", date="2026-10-02T10:00:00Z")
    (dest / "tests").mkdir()
    (dest / "tests" / "test_billing.py").write_text("from src.billing import total\n\ndef test_t():\n    assert total([1]) == 1\n")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "Add tests for billing", date="2026-10-03T10:00:00Z")
    return dest


def wait_for(pred, timeout: float = 10.0, step: float = 0.02) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


def register_test_kinds() -> None:
    """test.nap: a child whose script sleeps `nap_s` seconds (default 30) then writes a result. Used for stop, kill,
    yield and revoke tests. The role is registered once per process."""
    from understudy_agent.runtime.exemplars import base

    if "test.nap" in base.KINDS:
        return
    register_schema("nap_v1", {"type": "object", "required": ["ok"], "additionalProperties": False,
                               "properties": {"ok": {"type": "boolean"}}})
    register_role(RoleDef("napper", "Test role whose script sleeps.", frozenset({"write_workspace", "run_python", "emit_result"}),
                          frozenset({"tmp"}), "nap_v1", "data_profiler"))
    tpl = {"nap": "import json, os, time\ntime.sleep(float(os.environ.get('NAP_S', '30')))\nopen('result.json','w').write(json.dumps({'ok': True}))\n",
           "nap_long": "import time\ntime.sleep(60)\n",
           "nap_short": "import json, time\ntime.sleep(1.2)\nopen('result.json','w').write(json.dumps({'ok': True}))\n",
           "quick": "import json\nopen('result.json','w').write(json.dumps({'ok': True}))\n",
           "escape": "import os\nopen(os.environ.get('CANARY_PATH', '/nonexistent/x'), 'w').write('pwned')\nopen('result.json','w').write('{\"ok\": true}')\n"}
    register_menu("napper", Menu(files={"script": "nap.py", "result": "result.json"}, templates=tpl), "Sleep, then report ok.")
    register_verifier("napper", lambda ctx: [Check(name="ok_true", ok=ctx.output.get("ok") is True)])

    def steps(role: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        tpl_id = params.get("template", "nap_short")
        seq = [{"tool": "write_workspace", "file": "script", "template": tpl_id}]
        seq += [{"tool": "run_python", "file": "script"}] * int(params.get("runs", 1))
        seq.append({"tool": "emit_result", "file": "result"})
        return seq

    register_exemplar(Exemplar(kind="test.nap", title="Test: sleep", describe="Test only.", roles=("napper",),
                               needs=lambda role, p: WorkspaceNeeds(), prepare=lambda p, d: dict(p), mock_steps=steps))
    # test.peek: a menu-mode child that READS a text file (so the local detector sees it) and then finishes
    register_schema("peek_v1", {"type": "object", "required": ["ok"], "additionalProperties": False,
                                "properties": {"ok": {"type": "boolean"}}})
    register_role(RoleDef("peeker", "Test role that reads one file.", frozenset({"read_file", "write_workspace", "emit_result"}),
                          frozenset({"tmp"}), "peek_v1", "data_profiler"))
    register_menu("peeker", Menu(files={"note": "input/note.txt", "result": "result.json", "script": "w.json"},
                                 templates={"ok": '{"ok": true}'}), "Read one file, then report ok.")
    register_verifier("peeker", lambda ctx: [Check(name="ok_true", ok=ctx.output.get("ok") is True)])
    register_exemplar(Exemplar(
        kind="test.peek", title="Test: read a file", describe="Test only.", roles=("peeker",),
        needs=lambda role, p: WorkspaceNeeds(inputs=((Path(p["note_path"]), "note.txt"),)), prepare=lambda p, d: dict(p),
        mock_steps=lambda role, p: [{"tool": "read_file", "file": "note"},
                                    {"tool": "write_workspace", "file": "result", "template": "ok"},
                                    {"tool": "emit_result", "file": "result"}]))
