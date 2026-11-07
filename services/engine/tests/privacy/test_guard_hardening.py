"""The static guard against evasion (REVIEW-PRIVACY P1): alias tracking, constant folding, processes, dynamic code, and the agent service.

The first block is the reviewer's own reproducer set (evals/review/privacy/test_p1_guard_bypass.py, copied here, not imported, so this file stands alone): every
one of those snippets passed the old guard silently; each must now be flagged, in an ordinary layer and in a pure-compute layer. The rest are further
evasions, the false-positive controls, and the agent-package scan with its reviewed allow list.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from understudy_engine.privacy import guard, netscan
from understudy_engine.privacy.guard_samples import AGENT_CLEAN, CLEAN, EXTRA, REVIEWER_AGENT, REVIEWER_LAYER, ROUND2, ROUND2_CONTROL

LAYER = "calendar/x.py"
PURE = "mlv2/x.py"
AGENT = "understudy_agent/voice/x.py"
RUNTIME = "understudy_agent/runtime/x.py"


def rules_of(src: str, path: str = LAYER) -> set[str]:
    return {v.rule for v in guard.scan_source(textwrap.dedent(src), path)[0]}


# --------------------------------------------------------------------------- the reviewer's evasions: each expected rule
@pytest.mark.parametrize("name", sorted(REVIEWER_LAYER))
def test_each_reviewer_evasion_is_flagged_in_an_extension_layer(name):
    src, expected = REVIEWER_LAYER[name]
    got = rules_of(src, LAYER)
    assert got, f"{name} is still invisible to the guard"
    assert got & expected, f"{name}: flagged as {got}, expected one of {expected}"


@pytest.mark.parametrize("name", sorted(REVIEWER_LAYER))
def test_each_reviewer_evasion_is_flagged_in_a_pure_compute_layer_too(name):
    assert rules_of(REVIEWER_LAYER[name][0], PURE), f"{name} is invisible in a pure-compute layer"


@pytest.mark.parametrize("name", sorted(REVIEWER_AGENT))
def test_each_reviewer_agent_side_evasion_is_flagged(name):
    src = REVIEWER_AGENT[name]
    assert guard.scan_agent_source(src, AGENT)[0], name
    assert guard.provider_endpoint_violations(src, AGENT), name               # the reviewer's entry point sees it too
    assert guard.scan_runtime_source(src, RUNTIME), name                      # and so does the runtime rule


def test_other_hosted_model_hosts_and_sdks_are_named_not_just_gemini_and_openai():
    for host in ("api.anthropic.com", "openrouter.ai", "api.groq.com", "api.mistral.ai", "api.together.xyz"):
        assert guard.provider_endpoint_violations(f"U = 'https://{host}/v1'\n", "understudy_engine/x.py", include_agent_network=False)
    for sdk in ("anthropic", "cohere", "mistralai", "groq", "litellm", "openai"):
        assert guard.provider_endpoint_violations(f"import {sdk}\n", "understudy_engine/x.py", include_agent_network=False)


# --------------------------------------------------------------------------- more evasions (aliases, folding, processes, dynamic code)
@pytest.mark.parametrize("src,rule", EXTRA, ids=[f"{i:02d}" for i in range(len(EXTRA))])
def test_further_evasions_are_flagged(src, rule):
    assert rule in rules_of(src, LAYER), f"{src!r}: got {rules_of(src, LAYER)}"


@pytest.mark.parametrize("src", CLEAN)
def test_ordinary_code_is_not_flagged_by_the_hardened_scan(src):
    assert rules_of(src, LAYER) == set(), rules_of(src, LAYER)


def test_a_url_in_a_docstring_or_a_schema_id_is_not_egress_in_an_ordinary_layer():
    assert rules_of('"""See https://example.org/docs."""\nSCHEMA = {"$id": "https://json-schema.org/draft/2020-12/schema"}\n', LAYER) == set()


# --------------------------------------------------------------------------- pure compute: process and url rules, no exceptions
def test_pure_compute_refuses_any_process_and_any_url():
    assert "pure_compute_import" in rules_of("import subprocess\n", PURE)
    assert "pure_compute_url" in rules_of("U = 'https://example.org/data.csv'\n", PURE)
    assert "pure_compute_call" in rules_of("import os\nos.system('ls')\n", PURE)


# --------------------------------------------------------------------------- the agent service scan and its reviewed allow list
def test_the_real_agent_service_is_clean_and_the_provider_package_and_runtime_are_the_only_skips():
    rep = guard.scan_agent()
    assert rep.files and rep.ok, "\n".join(map(str, rep.violations))
    assert not any(f.startswith(guard.AGENT_SKIP) for f in rep.files)
    names = {Path(f).name for f in rep.files}
    for must in ("handoff_io.py", "server.py", "tts.py", "runner.py", "base.py"):
        assert must in names, f"{must} is not under the agent scan"
    assert guard.scan_runtime().files, "the agent runtime is not scanned"


def test_a_new_agent_file_that_uses_the_network_fails_until_it_is_reviewed(tmp_path):
    root = tmp_path / "understudy_agent"
    (root / "voice").mkdir(parents=True)
    (root / "voice" / "new_client.py").write_text("import httpx\nhttpx.post('http://127.0.0.1:7700/x', json={})\n")
    (root / "ok.py").write_text("import json\n")
    rep = guard.scan_agent(root)
    assert rep.violations and {v.rule for v in rep.violations} == {"network_import"} and all(v.file.endswith("voice/new_client.py") for v in rep.violations)
    rep2 = guard.scan_runtime(root / "voice")
    assert any(v.rule == "network_import" for v in rep2.violations)


def test_a_reviewed_agent_file_may_use_only_what_its_entry_names(monkeypatch):
    monkeypatch.setitem(guard.AGENT_ALLOW, "understudy_agent/voice/ok_client.py", netscan.Allow("test entry", frozenset({"httpx"})))
    ok = "import httpx\nBASE = 'http://127.0.0.1:7700'\nhttpx.get(BASE + '/health')\n"
    assert guard.scan_agent_source(ok, "understudy_agent/voice/ok_client.py")[0] == []
    assert "network_import" in {v.rule for v in guard.scan_agent_source("import requests\nBASE='http://127.0.0.1'\n", "understudy_agent/voice/ok_client.py")[0]}
    assert "remote_url" in {v.rule for v in guard.scan_agent_source("import httpx\nhttpx.get('https://evil.example/x')\nB='127.0.0.1'\n", "understudy_agent/voice/ok_client.py")[0]}
    assert "network_import" in {v.rule for v in guard.scan_agent_source("import socket\n", "understudy_agent/voice/ok_client.py")[0]}


def test_a_loopback_client_must_be_demonstrably_loopback(monkeypatch):
    monkeypatch.setitem(guard.AGENT_ALLOW, "understudy_agent/voice/lb.py", netscan.Allow("test entry", frozenset({"httpx"})))
    no_evidence = "import httpx\nimport os\nBASE = os.environ['URL']\nhttpx.get(BASE)\n"
    assert "loopback_not_demonstrated" in {v.rule for v in guard.scan_agent_source(no_evidence, "understudy_agent/voice/lb.py")[0]}
    for evidence in ("BASE = 'http://127.0.0.1:7700'\n", "BASE = 'http://localhost:7700'\n", "H = 'localhost'\n"):
        assert guard.scan_agent_source("import httpx\nimport os\n" + evidence + "httpx.get(BASE if 'BASE' in dir() else H)\n", "understudy_agent/voice/lb.py")[0] == []


def test_a_remote_entry_must_carry_the_one_host_it_names(monkeypatch):
    monkeypatch.setitem(guard.AGENT_ALLOW, "understudy_agent/voice/remote.py", netscan.Allow("test entry", frozenset({"httpx"}), frozenset({"api.example.org"})))
    assert guard.scan_agent_source("import httpx\nU = 'https://api.example.org/v1'\n", "understudy_agent/voice/remote.py")[0] == []
    r = {v.rule for v in guard.scan_agent_source("import httpx\nU = 'https://other.example.org/v1'\nV = 'https://api.example.org'\n", "understudy_agent/voice/remote.py")[0]}
    assert "remote_url" in r
    assert "remote_not_demonstrated" in {v.rule for v in guard.scan_agent_source("import httpx\nU = '127.0.0.1'\n", "understudy_agent/voice/remote.py")[0]}


def test_every_allow_entry_names_a_real_file_and_is_still_needed():
    """A stale entry is a hole waiting for a new use: each reviewed entry must match a file, and removing it must produce a violation."""
    problems = []
    for table, root, rel_root, kind in ((guard.ALLOW, guard.ENGINE_PKG, "", "layer"), (guard.AGENT_ALLOW, guard.AGENT_PKG.parent, "", "agent")):
        for pat, allow in list(table.items()):
            files = sorted(root.glob(pat))
            if not files:
                problems.append(f"{pat}: no such file")
                continue
            for f in files:
                rel = f.relative_to(root).as_posix()
                src = f.read_text(encoding="utf-8")
                with_entry = guard.scan_source(src, rel, kind=kind)[0]
                saved = dict(table)
                table.pop(pat)
                try:
                    without = guard.scan_source(src, rel, kind=kind)[0]
                finally:
                    table.update(saved)
                if with_entry:
                    problems.append(f"{rel}: still violates with its entry: {with_entry[0]}")
                if not without:
                    problems.append(f"{rel}: its entry is not needed (no violation without it): {allow.reason[:50]}")
    assert problems == [], "\n".join(problems)


def _module_constant(path: Path, name: str) -> str | None:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            return node.value.value if isinstance(node.value, ast.Constant) else None
    return None


def test_the_loopback_constants_named_in_allow_entries_really_are_loopback_literals():
    checks = {
        "understudy_agent/sandbox_sites/runner.py": [guard.AGENT_PKG / "sandbox_sites" / "specs.py"],
        "understudy_agent/sandbox_roles/base.py": [guard.AGENT_PKG / "sandbox_roles" / "__init__.py"],
        "localmodel/server.py": [guard.ENGINE_PKG / "localmodel" / "config.py"],
    }
    for key, defining in checks.items():
        entry = guard.AGENT_ALLOW.get(key) or guard.ALLOW.get(key)
        assert entry is not None and entry.loopback_names, key
        for name in entry.loopback_names:
            const = name.split(".")[-1]
            assert any(_module_constant(p, const) in netscan.LOOPBACK_HOSTS for p in defining), f"{key}: {name} is not a loopback literal"


def test_the_local_model_client_really_refuses_a_remote_host():
    from understudy_engine.localmodel import client

    assert client.assert_loopback("http://127.0.0.1:8089/") == "http://127.0.0.1:8089"
    for bad in ("http://example.org", "https://api.openai.com/v1", "http://192.168.1.5:8089"):
        with pytest.raises(client.ClientError):
            client.assert_loopback(bad)


# --------------------------------------------------------------------------- pending exceptions are not accepted exceptions
def test_the_voice_exception_is_listed_as_pending_not_silently_accepted():
    pend = {p["file"]: p for p in guard.pending_exceptions()}
    assert "understudy_agent/voice/tts.py" in pend and "outside the egress guard" in pend["understudy_agent/voice/tts.py"]["pending"]
    assert guard.AGENT_ALLOW["understudy_agent/voice/tts.py"].pending


# --------------------------------------------------------------------------- the runtime: no network at all
def test_runtime_children_have_no_network_and_no_reviewed_exception(monkeypatch):
    monkeypatch.setitem(guard.AGENT_ALLOW, "understudy_agent/runtime/x.py", netscan.Allow("a mistaken entry", frozenset({"httpx"})))
    assert "network_import" in {v.rule for v in guard.scan_runtime_source("import httpx\nB='127.0.0.1'\n", "runtime/x.py")}
    assert "process_fetcher" in {v.rule for v in guard.scan_runtime_source("import subprocess\nsubprocess.run(['curl', 'x'])\n", "runtime/x.py")}
    assert guard.scan_runtime_source("import subprocess, sys\nsubprocess.run(['sandbox-exec', '-f', 'p.sb', sys.executable, 'f.py'])\n", "runtime/x.py") == []
    assert guard.scan_runtime_source("from ..models.port import ModelPort\ndef f(p: ModelPort): ...\n", "runtime/x.py") == []     # the port itself is its job


def test_relative_imports_resolve_to_the_real_package_names():
    a = netscan.Analyzer("", "understudy_agent/runtime/x.py", netscan.Policy(kind="runtime", package_root="understudy_agent"), None)
    assert a._abs_module(2, "models") == "understudy_agent.models" and a._abs_module(1, "policy") == "understudy_agent.runtime.policy"
    assert netscan.Analyzer("", "calendar/x.py", netscan.Policy(kind="layer"), None)._abs_module(2, "privacy") == "understudy_engine.privacy"
    # an extension layer importing the agent's model package through a relative path is still caught
    assert "model_client_import" in rules_of("from understudy_agent.models import get_model_port\n", "calendar/x.py")


# --------------------------------------------------------------------------- osascript: allowed only with a constant local script, only where reviewed
CU = "understudy_agent/tiers/computer_use.py"


def test_osascript_is_a_fetcher_everywhere_except_one_reviewed_file_and_there_only_with_a_constant_local_script():
    ok = "import subprocess\nsubprocess.run(['osascript', '-e', 'tell application \"TextEdit\" to get text of document 1'], capture_output=True)\n"
    assert guard.scan_agent_source(ok, CU)[0] == []
    assert "process_fetcher" in {v.rule for v in guard.scan_agent_source(ok, "understudy_agent/voice/x.py")[0]}                  # not reviewed there
    for risky in ('do shell script "curl https://x"', 'tell application "Safari" to open location "https://x"', 'do shell script "id"',
                  'tell application "Mail" to send'):
        src = f"import subprocess\nsubprocess.run(['osascript', '-e', {risky!r}])\n"
        assert "process_fetcher" in {v.rule for v in guard.scan_agent_source(src, CU)[0]}, risky
    unreadable = "import subprocess\nsubprocess.run(['osascript', '-e', script])\n"
    assert "process_fetcher" in {v.rule for v in guard.scan_agent_source(unreadable, CU)[0]}
    assert "process_fetcher" in {v.rule for v in guard.scan_agent_source("import subprocess\nsubprocess.run(['osascript', 'file.scpt'])\n", CU)[0]}
    assert "process_fetcher" in {v.rule for v in guard.scan_agent_source("import subprocess\nsubprocess.run(['curl', 'x'])\n", CU)[0]}     # other fetchers stay refused


# =========================================================================== round 2 (reviewer): allowlist, browsers, processes, model references, paths
ROUND2_EXPECT = {
    "dnspython": {"import_not_allowed"}, "dropbox": {"network_import"}, "dynamic_attribute_call": {"model_call"}, "gcs_upload": {"import_not_allowed"},
    "git_clone_remote_from_variable": {"process_git_unreviewed"}, "node_e_network": {"process_unreviewed"},
    "open_file_in_synced_folder": {"home_path", "synced_folder_path"}, "paho_mqtt": {"import_not_allowed"}, "partial_of_plan": {"model_call"},
    "perl_e": {"process_unreviewed"}, "playwright_goto_with_data": {"browser_automation"}, "posthog_telemetry": {"import_not_allowed"},
    "python_m_module": {"process_unreviewed"}, "redis_remote": {"network_import"}, "selenium": {"browser_automation"}, "sendmail_binary": {"process_unreviewed"},
    "sentry_sdk_ships_locals": {"import_not_allowed"}, "slack_sdk": {"network_import"}, "vars_dict_plan": {"model_call"},
    "which_curl_not_constant": {"process_fetcher", "process_unresolved"},
}


@pytest.mark.parametrize("name", sorted(ROUND2))
def test_each_round2_reviewer_evasion_is_flagged_by_the_expected_rule(name):
    got = rules_of(ROUND2[name], LAYER)
    assert got, f"{name} is silent"
    assert got & ROUND2_EXPECT[name], f"{name}: flagged as {got}, expected one of {ROUND2_EXPECT[name]}"
    assert rules_of(ROUND2[name], PURE), f"{name} is silent in a pure-compute layer"


def test_the_round2_control_stays_clean_and_every_round2_case_has_an_expected_rule():
    assert rules_of(ROUND2_CONTROL, LAYER) == set() and set(ROUND2) == set(ROUND2_EXPECT)


# ---- the import allowlist
@pytest.mark.parametrize("src", [
    "import json, re, os, sys, math, hashlib\nfrom datetime import datetime\nfrom collections import defaultdict\n",
    "import numpy as np\nimport pandas as pd\nimport scipy.stats\nfrom sklearn.linear_model import LogisticRegression\nimport statsmodels.api as sm\n",
    "import lifelines, yaml, jsonschema, orjson\nfrom pydantic import BaseModel\nfrom fastapi import APIRouter\nimport threadpoolctl\n",
    "from understudy_engine.privacy import egress\nfrom ..store import paths\nfrom . import sibling\nimport understudy_agent.security\n",
    "import importlib\nm = importlib.import_module('numpy')\n",
])
def test_allowed_imports_pass_in_a_layer(src):
    assert rules_of(src, LAYER) == set(), rules_of(src, LAYER)


@pytest.mark.parametrize("src", ["import dns.resolver\n", "import sentry_sdk\n", "from google.cloud import storage\n", "import pyaudio\n", "import cv2\n",
                                 "import importlib\nm = importlib.import_module('posthog')\n", "import elevenlabs\n", "import docx\n"])
def test_other_third_party_imports_are_refused_in_a_layer_until_reviewed(src, monkeypatch):
    assert rules_of(src, LAYER) & {"import_not_allowed", "network_import", "model_client_import"}
    assert "import_not_allowed" in rules_of("import dns.resolver\n", LAYER)
    monkeypatch.setitem(guard.ALLOW, "calendar/needs_docx.py", netscan.Allow("reviewed for this test", frozenset({"docx"})))
    assert guard.scan_source("import docx\n", "calendar/needs_docx.py")[0] == []


def test_the_agent_package_is_not_held_to_the_layer_allowlist_but_still_to_the_network_rules():
    assert guard.scan_agent_source("import pyaudio\nimport PIL\nfrom playwright.async_api import async_playwright\nimport numpy\n", "understudy_agent/tiers/x.py")[0] == []
    assert "network_import" in {v.rule for v in guard.scan_agent_source("import requests\n", "understudy_agent/tiers/x.py")[0]}


@pytest.mark.parametrize("src", ["from playwright.sync_api import sync_playwright\n", "import selenium.webdriver\n", "import pyppeteer\n",
                                 "import importlib\nimportlib.import_module('playwright.sync_api')\n"])
def test_browser_automation_is_refused_in_a_layer(src):
    assert "browser_automation" in rules_of(src, LAYER) and "browser_automation" in rules_of(src, PURE)


# ---- processes: a constant program, and for git a constant read-only subcommand
@pytest.mark.parametrize("src", [
    "import subprocess\nsubprocess.run(['git', 'log', '--format=%H'])\n",
    "import subprocess\nsubprocess.run(['git', '-C', repo, 'log', '-n', '5'], capture_output=True)\n",
    "import subprocess\nsubprocess.run(['git', 'rev-parse', 'HEAD'])\n",
    "import subprocess\nsubprocess.run(['git', 'init', str(p)])\nsubprocess.run(['git', 'commit', '-m', 'x'])\nsubprocess.run(['git', 'add', '-A'])\n",
    "import subprocess\nsubprocess.run(['git', '--version'])\n",
    "import subprocess\nsubprocess.run('git log --oneline', shell=True)\n",
])
def test_git_with_a_constant_read_only_subcommand_is_fine_in_a_layer(src):
    assert rules_of(src, LAYER) == set(), rules_of(src, LAYER)


@pytest.mark.parametrize("src,rule", [
    ("import subprocess\nsubprocess.run(['git', 'clone', remote, '/tmp/x'])\n", "process_git_unreviewed"),
    ("import subprocess\nsubprocess.run(['git', 'clone', '/local/repo', '/tmp/x'])\n", "process_git_unreviewed"),
    ("import subprocess\nsubprocess.run(['git', 'push'])\n", "process_git_network"),
    ("import subprocess\nsubprocess.run(['git', sub, 'x'])\n", "process_git_unreviewed"),
    ("import subprocess\nsubprocess.run(['git'])\n", "process_git_unreviewed"),
    ("import subprocess\nsubprocess.run(['node', '-e', 'x'])\n", "process_unreviewed"),
    ("import subprocess\nsubprocess.run(['ls', '-l'])\n", "process_unreviewed"),
    ("import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'pip', 'list'])\n", "process_unreviewed"),
    ("import subprocess\nsubprocess.run(cmd)\n", "process_unresolved"),
    ("import subprocess\nsubprocess.run(build_argv(x))\n", "process_unresolved"),
    ("import subprocess\nsubprocess.Popen([program, '-v'])\n", "process_unresolved"),
    ("import os\nos.system('ls')\n", "process_unreviewed"),
])
def test_anything_else_a_layer_starts_is_refused_until_reviewed(src, rule):
    assert rule in rules_of(src, LAYER), (src, rules_of(src, LAYER))


def test_a_reviewed_entry_may_name_the_other_programs_or_say_the_argv_is_built_elsewhere(monkeypatch):
    monkeypatch.setitem(guard.ALLOW, "calendar/runner.py", netscan.Allow("test", processes=frozenset({"ps"}), dynamic_process=True))
    assert guard.scan_source("import subprocess\nsubprocess.run(['ps', '-o', 'command=', '-p', '1'])\nsubprocess.run(cmd)\n", "calendar/runner.py")[0] == []
    monkeypatch.setitem(guard.ALLOW, "calendar/ps_only.py", netscan.Allow("test", processes=frozenset({"ps"})))
    assert guard.scan_source("import subprocess\nsubprocess.run(['ps', 'x'])\n", "calendar/ps_only.py")[0] == []
    assert "process_unresolved" in {v.rule for v in guard.scan_source("import subprocess\nsubprocess.run(cmd)\n", "calendar/ps_only.py")[0]}
    assert "process_unreviewed" in {v.rule for v in guard.scan_source("import subprocess\nsubprocess.run(['ls'])\n", "calendar/ps_only.py")[0]}
    # a reviewed entry never makes a fetcher acceptable
    assert "process_fetcher" in {v.rule for v in guard.scan_source("import subprocess\nsubprocess.run(['curl', 'x'])\n", "calendar/runner.py")[0]}


def test_the_agent_package_may_run_other_programs_without_review_but_not_fetchers():
    assert guard.scan_agent_source("import subprocess\nsubprocess.run(['screencapture', '-x', 'f.png'])\nsubprocess.run(cmd)\n", "understudy_agent/tiers/x.py")[0] == []
    assert "process_fetcher" in {v.rule for v in guard.scan_agent_source("import subprocess\nsubprocess.run(['wget', 'x'])\n", "understudy_agent/tiers/x.py")[0]}


def test_the_git_commands_the_git_layer_runs_start_with_git_log():
    from understudy_engine.gitanalysis import source

    argv = source.git_argv(Path("/tmp/repo"), "log", "-n", "1")
    assert argv[0] == "git" and "log" in argv
    src = Path(source.__file__).read_text()
    assert "git_argv(self.repo, *args)" in src and 'args = ["log"' in src


# ---- model methods reached without a plain call, and the false-positive controls for ordinary `plan` attributes
@pytest.mark.parametrize("src", [
    "import functools\nf = functools.partial(port.plan, msgs)\n",
    "from functools import partial\nf = partial(x.plan, msgs)\n",
    "import functools\nf = functools.partial(thing.vision, img)\n",
    "import threading\nthreading.Thread(target=x.plan, args=(m,)).start()\n",
    "def f(ex, port):\n    return ex.submit(port.plan, msgs)\n",
    "import asyncio\nasync def f(port):\n    return await asyncio.to_thread(port.plan, msgs)\n",
    "p = port.plan\n",
    "g = self.model.check\n",
    "import operator\nf = operator.attrgetter('plan')\n",
    "import operator\nf = operator.methodcaller('vision', img)\n",
    "f = getattr(x, 'plan')\n",
    "f = getattr(x, 'comp' + 'uter_step')\n",
    "def f(c):\n    return vars(c)['plan']\n",
    "def f(c):\n    return c.__dict__['vision']\n",
    "def f(c):\n    return type(c).__dict__['plan'](c, m)\n",
])
def test_a_reference_to_a_model_method_is_refused_without_a_call(src):
    assert "model_call" in rules_of(src, LAYER), (src, rules_of(src, LAYER))


@pytest.mark.parametrize("src", [
    "def f(ctx):\n    return ctx.plan.strategy\n",
    "def f(sx):\n    x = sx.plan\n    return emit(sx, sx.plan, 1)\n",
    "class A:\n    def __init__(self, plan):\n        self.plan = plan\n",
    "def f(row):\n    return row['plan']\n",
    "d = {'plan': 1}\nx = d['plan']\n",
    "def f(ctx):\n    for s in ctx.plan.stuck:\n        print(s)\n",
    "import functools\nf = functools.partial(print, 'plan')\n",
    "def f(o):\n    return getattr(o, 'name')\n",
    "def f(items):\n    return vars(items)['count']\n",
    "def f(plan):\n    return plan.steps\n",
])
def test_ordinary_plan_attributes_and_dictionary_keys_are_not_flagged(src):
    assert rules_of(src, LAYER) == set(), (src, rules_of(src, LAYER))


# ---- paths: no home folder, no synced folder
@pytest.mark.parametrize("src", [
    "from pathlib import Path\np = Path.home() / 'x'\n",
    "import pathlib\np = pathlib.Path.home()\n",
    "import os\np = os.path.expanduser('~/Documents')\n",
    "from pathlib import Path\np = Path('~/notes').expanduser()\n",
    "import os\nh = os.getenv('HOME')\n",
    "import os\nh = os.environ.get('HOME')\n",
])
def test_a_layer_may_not_reach_into_the_home_folder(src):
    assert "home_path" in rules_of(src, LAYER)


@pytest.mark.parametrize("path", ["~/Library/Mobile Documents/com~apple~CloudDocs/x", "/Users/a/Dropbox/x", "/Users/a/OneDrive - Corp/x", "/Users/a/Google Drive/x",
                                  "/Users/a/Library/CloudStorage/Box-Box/x", "/Volumes/Backup/x", "/Users/a/iCloud Drive/x"])
def test_a_layer_may_not_name_a_synced_folder(path):
    assert "synced_folder_path" in rules_of(f"P = {path!r}\n", LAYER)


def test_paths_under_the_data_directory_and_env_based_roots_are_fine():
    assert rules_of("import os\nfrom pathlib import Path\nroot = Path(os.environ.get('UNDERSTUDY_DATA_DIR', 'data')) / 'x'\nroot.mkdir(parents=True)\n", LAYER) == set()
    assert rules_of("from pathlib import Path\np = Path(env).expanduser()\n", LAYER) == set()


def test_only_two_reviewed_files_may_use_home_and_they_really_default_to_the_understudy_folder(monkeypatch):
    homes = sorted(k for k, a in guard.ALLOW.items() if a.home_path)
    assert homes == ["cue/paths.py", "proactive/paths.py"]
    monkeypatch.delenv("UNDERSTUDY_HOME", raising=False)
    from understudy_engine.proactive import paths as pp

    assert pp.home_dir() == Path.home() / ".understudy"
    try:
        from understudy_engine.cue import paths as cp
    except ImportError:
        return
    assert cp.home_dir() == Path.home() / ".understudy"


# ---- the pure packages: attention (engine) and context (agent)
def test_attention_and_context_are_flagged_layers_and_pure_compute():
    from understudy_engine.privacy import flags

    assert {"attention", "context"} <= set(flags.LAYERS) and "attention" in guard.GUARDED_DIRS and "attention" in guard.PURE_COMPUTE_DIRS
    assert "understudy_agent/context/" in guard.AGENT_PURE_PREFIXES
    assert rules_of("import subprocess\n", "attention/x.py") and rules_of("import requests\n", "attention/x.py")
    assert rules_of("import numpy as np\nfrom fastapi import APIRouter\nrouter = APIRouter()\n", "attention/routes.py") == set()


@pytest.mark.parametrize("src,rule", [
    ("import subprocess\n", "pure_compute_import"), ("import requests\n", "network_import"), ("from understudy_agent.models import get_model_port\n", "model_client_import"),
    ("import openai\n", "model_client_import"), ("U = 'https://example.org/x'\n", "pure_compute_url"), ("import os\nos.system('ls')\n", "pure_compute_call"),
    ("import pyaudio\n", "import_not_allowed"), ("def f(port):\n    return port.plan([], None)\n", "model_call"),
])
def test_the_agent_context_package_is_pure_compute_with_no_exceptions(src, rule, monkeypatch):
    path = "understudy_agent/context/assemble.py"
    monkeypatch.setitem(guard.AGENT_ALLOW, path, netscan.Allow("a mistaken entry", frozenset({"requests", "httpx", "socket"}), dynamic_process=True))
    assert rule in {v.rule for v in guard.scan_agent_source(src, path)[0]}, guard.scan_agent_source(src, path)[0]


def test_agent_context_may_import_numbers_json_and_its_own_package():
    ok = "import json, re\nimport numpy as np\nfrom pydantic import BaseModel\nfrom ..security import paths\nfrom understudy_agent.audit import AuditLog\n"
    assert guard.scan_agent_source(ok, "understudy_agent/context/assemble.py")[0] == []


def test_programs_and_servers_that_are_ordinary_for_the_agent_are_refused_in_a_layer_and_clean_in_the_agent_package():
    assert len(AGENT_CLEAN) == 5
    for src in AGENT_CLEAN:
        assert guard.scan_agent_source(src, "understudy_agent/tiers/x.py")[0] == [], src
        assert rules_of(src, LAYER) & {"process_unreviewed", "process_unresolved", "import_not_allowed"}, src


def test_pillow_is_allowed_only_as_pure_image_decoding_and_still_cannot_bring_the_network_with_it():
    assert rules_of("from PIL import Image\nim = Image.open(buf).resize((64, 64))\n", LAYER) == set()
    assert rules_of("from PIL import Image\nimport socket\n", LAYER) == {"network_import"}
    assert guard.scan_agent_source("from PIL import Image\nimport numpy as np\n", "understudy_agent/context/frames.py")[0] == []
