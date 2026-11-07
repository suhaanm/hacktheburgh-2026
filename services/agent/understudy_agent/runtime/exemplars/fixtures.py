"""Synthetic fixtures for the exemplars, with planted facts and a truth dict (BGA-4, BGA-6). Nobody and nothing here is real.

`make_dev_repo` writes a small REAL git repository (19 commits, fixed dates) with:

    * two giant commits (about 500 lines each) and a revert of each        -> commit analyst
    * `src/billing.py` and `src/exporter.py` changed often and never with a test, `src/auth.py` always with one -> test gaps
    * the number 0.2 written four times in `src/billing.py` (a magic number), behind passing unittest tests -> refactor
    * three fix commits in quick succession on billing and two on the exporter -> fix-after-fix chains

The git-analysis track has richer synthetic repos (`understudy_engine.gitanalysis.synth.make_repo`); the exemplars work on
those too (they only read history), this one adds code that can be refactored with tests that can be run.
`make_digests` writes digest records (fixed-vocabulary enums only) for the creative exemplar.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BILLING = '''"""Billing helpers."""


def net(amount):
    return amount * (1 - 0.2)


def tax(amount):
    return amount * 0.2


def gross(amount):
    return amount + amount * 0.2


def discount_cap(amount):
    return min(amount, 100) * 0.2
'''
EXPORTER = '''"""CSV export."""


def to_csv(rows):
    return "\\n".join(",".join(str(c) for c in r) for r in rows)
'''
AUTH = '''"""Authentication helpers."""


def is_valid(user, password):
    return bool(user) and len(password) >= 8
'''
REPORT = '''"""Reports."""


def title(name):
    return name.upper()
'''
TEST_BILLING = '''import unittest

from src import billing


class BillingTests(unittest.TestCase):
    def test_net(self):
        self.assertAlmostEqual(billing.net(100), 80.0)

    def test_tax(self):
        self.assertAlmostEqual(billing.tax(100), 20.0)

    def test_gross(self):
        self.assertAlmostEqual(billing.gross(100), 120.0)

    def test_discount_cap(self):
        self.assertAlmostEqual(billing.discount_cap(500), 20.0)
'''
TEST_AUTH = '''import unittest

from src import auth


class AuthTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(auth.is_valid("ada", "longenough"))
        self.assertFalse(auth.is_valid("ada", "short"))
'''
TEST_REPORT = '''import unittest

from src import report


class ReportTests(unittest.TestCase):
    def test_title(self):
        self.assertEqual(report.title("q3"), "Q3")
'''

TRUTH_DEV = {
    "n_commits": 19, "giant_commits": 4, "giant_threshold_lines": 450, "reverts": 2,
    "hot_untested": ["src/billing.py", "src/exporter.py"], "tested_hot": ["src/auth.py"],
    "refactor_literal": {"path": "src/billing.py", "literal": "0.2", "occurrences": 4},
}


def _stamp(day: int, minute: int) -> str:
    return (datetime(2026, 10, day, 9, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(cwd: Path, *args: str, date: str | None = None, name: str = "Ada Ng", email: str = "ada@example.test") -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name,
           "GIT_COMMITTER_EMAIL": email}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    r = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed")
    return r.stdout.strip()


def make_dev_repo(dest: Path, *, canary: str | None = None) -> dict[str, Any]:
    """Write the dev repo at `dest` (created). `canary` puts a unique token in author names, messages and a path, for the
    leak tests (the numbers do not change). Returns the truth dict."""
    dest.mkdir(parents=True, exist_ok=True)
    _git(dest, "init", "-q", "-b", "main")
    a_name = f"Ada Ng {canary}" if canary else "Ada Ng"
    a_mail = f"ada.{canary.lower()}@canary-mail.example" if canary else "ada@example.test"
    n = [0]

    def commit(msg: str, files: dict[str, str], minute: int, day: int, remove: tuple[str, ...] = ()) -> None:
        for p, text in files.items():
            f = dest / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        for p in remove:
            (dest / p).unlink()
        _git(dest, "add", "-A")
        n[0] += 1
        stamp = _stamp(day, minute)
        _git(dest, "commit", "-q", "-m", msg + (f" {('INC-' + canary.upper())}" if canary and n[0] % 5 == 0 else ""),
             date=stamp, name=a_name, email=a_mail)

    base = {"README.md": "# Dev repo\n", "src/__init__.py": "", "tests/__init__.py": "", "src/billing.py": BILLING,
            "src/auth.py": AUTH, "src/exporter.py": EXPORTER, "src/report.py": REPORT, "tests/test_billing.py": TEST_BILLING,
            "tests/test_auth.py": TEST_AUTH, "tests/test_report.py": TEST_REPORT}
    if canary:
        base[f"src/customer_{canary.lower()}.py"] = f'"""Customer {canary} export."""\n'
    commit("Initial commit", base, 0, 1)
    b = BILLING
    steps = [("Add proration to billing", "\n\ndef prorate(amount, days):\n    return amount * days / 30\n"),
             ("Fix rounding in billing", "\n\ndef rounded(amount):\n    return round(amount, 2)\n"),
             ("Fix billing again", "\n\ndef floor_cents(amount):\n    return int(amount * 100) / 100\n"),
             ("Fix billing edge case", "\n\ndef clamp(amount):\n    return max(amount, 0)\n"),
             ("Tweak billing", "\n\ndef double(amount):\n    return amount * 3\n"),
             ("Update billing", "\n\ndef half(amount):\n    return amount / 3\n")]
    for i, (msg, extra) in enumerate(steps):
        b += extra
        commit(msg, {"src/billing.py": b}, 10 + (i % 3) * 30 if i < 3 else 10 + (i - 3) * 120, 2 + (i // 3))
    e = EXPORTER
    for i, (msg, extra) in enumerate([("Add csv exporter options", "\n\ndef header(cols):\n    return ','.join(cols)\n"),
                                      ("Fix exporter header", "\n\ndef quote(v):\n    return '\"' + str(v) + '\"'\n"),
                                      ("Fix exporter quoting", "\n\ndef join(rows):\n    return '\\n'.join(rows)\n")]):
        e += extra
        commit(msg, {"src/exporter.py": e}, 30 + i * 40, 4)
    au, ta = AUTH, TEST_AUTH
    for i in range(4):
        au += f"\n\ndef rule_{i}(user):\n    return bool(user)\n"
        ta += f"\n    def test_rule_{i}(self):\n        self.assertTrue(auth.rule_{i}('ada'))\n"
        commit(f"Add auth rule {i}", {"src/auth.py": au, "tests/test_auth.py": ta}, 30 + i * 90, 5 + i // 2)
    seed = "ROWS = [\n" + "".join(f"    ({i}, 'row{i}'),\n" for i in range(520)) + "]\n"
    commit("Add seed data", {"data/seed_rows.py": seed}, 10, 8)
    more = "MORE = [\n" + "".join(f"    ({i}, 'more{i}'),\n" for i in range(480)) + "]\n"
    commit("Add more seed data", {"data/more_rows.py": more}, 50, 8)
    first_giant = _git(dest, "log", "--format=%H", "--grep=Add seed data", "-n", "1")
    second_giant = _git(dest, "log", "--format=%H", "--grep=Add more seed data", "-n", "1")
    for sha, minute in ((first_giant, 10), (second_giant, 40)):
        _git(dest, "revert", "--no-edit", sha, date=_stamp(9, minute), name=a_name, email=a_mail)
    commit("Refactor report layout", {"src/report.py": REPORT + "\n\ndef header():\n    return 'REPORT'\n",
                                      "tests/test_report.py": TEST_REPORT + "\n    def test_h(self):\n        self.assertEqual(report.header(), 'REPORT')\n"},
           20, 10)
    return dict(TRUTH_DEV)


def make_digests(dest: Path, *, canary: str | None = None) -> dict[str, Any]:
    """Twelve commit digests (fixed-vocabulary fields and an id each) for one week. Returns {digests, truth}."""
    cats = ["feature", "feature", "fix", "fix", "fix", "refactor", "test", "docs", "chore", "revert", "feature", "fix"]
    sizes = ["small", "medium", "tiny", "small", "large", "medium", "small", "tiny", "tiny", "huge", "small", "tiny"]
    digs = []
    for i, (c, s) in enumerate(zip(cats, sizes)):
        digs.append({"id": f"d_{(0x3a1000 + i * 977):06x}", "category": c, "size_bucket": s, "touches_tests": c in ("test", "feature") and i % 2 == 0})
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"digests": digs}))
    counts: dict[str, int] = {}
    for d in digs:
        counts[d["category"]] = counts.get(d["category"], 0) + 1
    return {"digests": digs, "truth": {"n": len(digs), "by_category": counts}}
