"""Licence and hygiene checks for vendor/clicky (NFR-6, SEC-10): headers, licence text, standard library only, and no
allowlist wording, so the modules can move into the agent service without tripping its own SEC-10 test."""
from __future__ import annotations

import ast
import re
import sys

from .conftest import VENDOR

SEC10 = re.compile(r"allow[\s_\-]?list|white[\s_\-]?list|allowed[_\s](domains?|hosts?|sites?|urls?|origins?)|"
                   r"permitted[_\s](domains?|sites?|hosts?)", re.IGNORECASE)
PY_FILES = sorted((VENDOR / "clicky_lift").glob("*.py"))
STDLIB = set(sys.stdlib_module_names)


def test_there_are_modules_to_check():
    assert {p.name for p in PY_FILES} >= {"__init__.py", "lease.py", "postcheck.py"}


def test_every_lifted_file_carries_the_adapted_from_header():
    for p in PY_FILES:
        head = p.read_text(encoding="utf-8").splitlines()[:3]
        assert head[0].startswith("# Adapted from rickkdev/clicky (fork of farzaa/clicky) (MIT) "), p.name
        assert "Copyright (c) 2026 Farza" in head[1] and "vendor/clicky/LICENSE" in head[1], p.name


def test_full_mit_licence_text_is_kept():
    text = (VENDOR / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License") and "Copyright (c) 2026 Farza" in text
    assert "Permission is hereby granted, free of charge" in text and "THE SOFTWARE IS PROVIDED \"AS IS\"" in text


NO_IO = {"subprocess", "socket", "ssl", "urllib", "http", "ftplib", "smtplib", "os", "shutil", "ctypes", "pathlib",
         "importlib", "pickle", "marshal"}


def test_standard_library_only_no_io_and_no_dynamic_code():
    """The lifts are pure logic: no network, no processes, no files, no eval. (Clicky's bridge client used a shell.)"""
    for p in PY_FILES:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                assert m in STDLIB, f"{p.name} imports non-stdlib {m}"
                assert m not in NO_IO, f"{p.name} imports {m}"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "open", "__import__"}, f"{p.name} calls {node.func.id}"


def test_no_allowlist_wording_in_the_vendored_sources():
    hits = [f"{p.name}:{i}: {line.strip()[:80]}" for p in PY_FILES
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if SEC10.search(line)]
    assert not hits, "SEC-10 wording:\n" + "\n".join(hits)


def test_readme_names_both_modules_and_the_licence():
    readme = (VENDOR / "README.md").read_text(encoding="utf-8")
    for needle in ("lease.py", "postcheck.py", "LICENSE", "rickkdev/clicky", "farzaa/clicky", "MIT"):
        assert needle in readme, needle
