"""The static guard (PRV-1): no module in the extension layers reaches a model except through privacy/egress.py.

Two halves: self-tests that prove the scanner catches each kind of violation (so an empty result means something), and the
scan of the real tree as it stands now. When another track adds a module that imports a model client or ModelPort, the second
half fails with the file and line.
"""
from __future__ import annotations

import textwrap

import pytest

from understudy_engine.privacy import guard
from understudy_engine.privacy.guard import scan_source, scan_tree


def v(src: str, path: str = "calendar/x.py"):
    return scan_source(textwrap.dedent(src), path)[0]


def rules(src: str, path: str = "calendar/x.py"):
    return {x.rule for x in v(src, path)}


# --------------------------------------------------------------------------- the scanner catches what it should
@pytest.mark.parametrize("src", [
    "import openai",
    "from openai import OpenAI",
    "import anthropic",
    "from google import genai",
    "import google.generativeai as g",
    "import litellm",
    "import requests",
    "import aiohttp",
    "import httpx",
    "import urllib.request",
    "from urllib.request import urlopen",
    "import http.client",
    "import socket",
    "def f():\n    import httpx\n    return httpx.get('https://example.org')",
    "import importlib\nm = importlib.import_module('openai')",
    "m = __import__('anthropic')",
])
def test_model_and_network_imports_are_caught(src):
    assert rules(src), src


@pytest.mark.parametrize("src", [
    "from understudy_agent.models import get_model_port",
    "from understudy_agent.models.port import ModelPort",
    "import understudy_agent.models",
    "def f(port: ModelPort): ...",
    "p = get_model_port()",
    "from understudy_agent.models.openai_provider import OpenAIProvider",
    "x = something.OpenAIProvider()",
])
def test_model_port_names_are_caught(src):
    assert rules(src), src


@pytest.mark.parametrize("src", [
    "def f(port): return port.plan([], None)",
    "def f(self): return self.model.check('x', {})",
    "def f(llm): return llm.read('x', {})",
    "def f(client): return client.check('p', {})",
    "def f(p): return p.computer_step('g', b'', [])",
    "def f(p): return p.vision(b'', 'x')",
    "def f(self): return self._provider.plan([], None)",
])
def test_model_calls_are_caught_by_method_and_receiver(src):
    assert "model_call" in rules(src), src


@pytest.mark.parametrize("src", ["subprocess.run(['curl', 'https://x'])", "os.system('wget http://x')"])
def test_shelling_out_to_fetchers_is_caught(src):
    assert "shell_fetch" in rules(src)


@pytest.mark.parametrize("src", [
    "import json, re, ast, subprocess, hashlib\nfrom datetime import datetime",
    "from understudy_engine.privacy import egress\negress.send('x', {})",
    "def f(items):\n    return items.read()\n",
    "def f(plan): return plan.check(1)",                 # not port-like receivers
    "x = 'https://json-schema.org/draft-07/schema#'",     # a URL literal alone is not egress
    "\"\"\"See https://docs.example.org for details.\"\"\"\nimport json",
    "import importlib\nm = importlib.import_module(name)",   # dynamic by variable: documented limit, not flagged
])
def test_ordinary_code_is_not_flagged(src):
    assert v(src) == [], v(src)


# --------------------------------------------------------------------------- allow entries are narrow
def test_allowed_file_may_use_its_client_but_not_a_model_client_or_another_host():
    ok = "import httpx\nc = httpx.Client()\nc.get('http://127.0.0.1:8089/health')\n"
    assert v(ok, "localmodel/client.py") == []
    assert "network_import" in rules(ok, "localmodel/other.py")                       # same code, not allow-listed
    assert "model_client_import" in rules("import httpx\nimport openai\n", "localmodel/client.py")
    assert "model_port_name" in rules("import httpx\nfrom x import ModelPort\n", "localmodel/client.py")
    assert "remote_url" in rules("import httpx\nhttpx.get('https://api.example.org/v1')\n", "localmodel/client.py")
    assert "network_import" in rules("import requests\n", "localmodel/client.py")      # only the listed imports are allowed


def test_graph_plugin_may_name_only_the_graph_host():
    ok = "import urllib.request\nU = 'https://graph.microsoft.com/v1.0/me/events'\n"
    assert v(ok, "plugins/graph_common.py") == []
    assert "remote_url" in rules("import urllib.request\nU = 'https://evil.example.org/x'\n", "plugins/graph_common.py")
    assert "network_import" in rules(ok, "plugins/other.py")


def test_fstring_urls_must_start_with_loopback_or_a_named_helper():
    src = "import httpx\ndef f(host, port):\n    return httpx.get(f'http://{host}:{port}/x')\n"
    assert "remote_url" in rules(src, "localmodel/client.py")
    ok_lit = "import httpx\ndef f(port):\n    return httpx.get(f'http://127.0.0.1:{port}/x')\n"
    assert v(ok_lit, "localmodel/client.py") == []
    ok_named = "import socket\ndef f(config, port):\n    return f'http://{config.HOST}:{port}'\n"
    assert v(ok_named, "localmodel/server.py") == []
    assert "remote_url" in rules(ok_named.replace("config.HOST", "other.HOST"), "localmodel/server.py")


def test_unparseable_files_are_reported_not_skipped():
    assert "unparseable" in rules("def (:\n")


# --------------------------------------------------------------------------- the real tree
def test_no_extension_module_reaches_a_model_or_the_network_outside_the_allow_list():
    rep = scan_tree()
    assert rep.files, "no guarded files found: the guard is looking in the wrong place"
    assert rep.ok, "extension modules must send content to a model only through privacy.egress.send:\n" + "\n".join(map(str, rep.violations))


def test_the_guard_covers_the_directories_that_exist():
    rep = scan_tree()
    present = {d for d in guard.GUARDED_DIRS if (guard.ENGINE_PKG / d).is_dir()}
    seen = {f.split("/")[0] for f in rep.files}
    assert present <= seen


def test_every_allow_entry_matches_a_real_file_or_is_removed():
    stale = [pat for pat in guard.ALLOW if not list(guard.ENGINE_PKG.glob(pat))]
    # entries for modules that another track has not written yet are tolerated only while the directory is absent
    stale = [p for p in stale if (guard.ENGINE_PKG / p.split("/")[0]).is_dir()]
    assert stale == [], f"guard.ALLOW has entries for files that no longer exist: {stale}"


def test_the_localmodel_host_constant_really_is_loopback():
    cfg = pytest.importorskip("understudy_engine.localmodel.config")
    assert cfg.HOST in guard.LOOPBACK_HOSTS


def test_egress_is_the_one_module_with_a_model_port_import_and_it_is_lazy():
    src = (guard.ENGINE_PKG / "privacy" / "egress.py").read_text()
    top_level = [ln for ln in src.splitlines() if ln.startswith(("import ", "from ")) and "understudy_agent" in ln]
    assert top_level == [], "egress must import the model port lazily, inside the function that needs it"
    assert "understudy_agent.models" in src


# --------------------------------------------------------------------------- the agent runtime (plans through ModelPort by design)
def rv(src: str):
    return {x.rule for x in guard.scan_runtime_source(textwrap.dedent(src), "runtime/x.py")}


def test_runtime_rule_flags_a_direct_call_without_a_ledger_record():
    assert rv("def f(self):\n    return self.port.plan([], None)\n") == {"unrecorded_model_call"}
    assert rv("def f(port):\n    return port.read('x', {})\n") == {"unrecorded_model_call"}
    assert rv("def f(self):\n    return self.port.computer_step('g', b'', [])\n") == {"unrecorded_model_call"}


def test_runtime_rule_accepts_a_direct_call_that_records_and_calls_that_go_through_egress():
    ok = "def f(self):\n    rtprivacy.record_raw_call('plan', 'm', 10, 'note')\n    return self.port.plan([], None)\n"
    assert rv(ok) == set()
    assert rv("def f(self):\n    ledger.record_direct(method='plan', model='m', bytes_sent=1)\n    return self.port.plan([], None)\n") == set()
    assert rv("def f(self, port):\n    return egress.send('agents.parent_plan', {}, port=port).output\n") == set()
    assert rv("def f(self):\n    return self.items.read()\n") == set()                 # not a port-like receiver


def test_runtime_rule_still_bans_provider_sdks_and_network_clients():
    assert "model_client_import" in rv("import openai\n")
    assert "model_client_import" in rv("from anthropic import Anthropic\n")
    assert "model_client_import" in rv("import httpx\n")
    assert "model_client_import" in rv("import urllib.request\n")


def test_the_real_runtime_has_no_unrecorded_direct_model_call_and_no_provider_import():
    rep = guard.scan_runtime()
    if not rep.files:
        pytest.skip("the agent runtime is not present")
    assert rep.ok, "the agent runtime must send payloads through egress.send and record every direct call:\n" + "\n".join(map(str, rep.violations))
