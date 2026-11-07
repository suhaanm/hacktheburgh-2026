from __future__ import annotations

import sys
import types

import pytest

from understudy_engine.cli import main


def fake_plugins(monkeypatch, result=0):
    calls = []
    pkg = types.ModuleType("understudy_engine.plugins")
    pkg.__path__ = []                                           # a package
    cli = types.ModuleType("understudy_engine.plugins.cli")

    def validate_command(paths, quiet=False):
        calls.append((list(paths), quiet))
        return result

    cli.validate_command = validate_command
    monkeypatch.setitem(sys.modules, "understudy_engine.plugins", pkg)
    monkeypatch.setitem(sys.modules, "understudy_engine.plugins.cli", cli)
    return calls


def test_plugin_validate_calls_the_plugins_package_and_passes_the_exit_code_through(monkeypatch):
    calls = fake_plugins(monkeypatch, result=0)
    assert main(["plugin", "validate"]) == 0
    assert calls == [([], False)]
    assert main(["plugin", "validate", "a/b", "c.yaml", "--quiet"]) == 0 and calls[-1] == (["a/b", "c.yaml"], True)
    fake_plugins(monkeypatch, result=1)
    assert main(["plugin", "validate", "x"]) == 1                 # a failed validation is exit 1
    fake_plugins(monkeypatch, result=3)
    assert main(["plugin", "validate"]) == 3                      # whatever the package returns


def test_a_missing_plugins_package_prints_a_plain_message_and_exits_2(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "understudy_engine.plugins", None)          # import halted: as if the package were absent
    monkeypatch.setitem(sys.modules, "understudy_engine.plugins.cli", None)
    assert main(["plugin", "validate", "x"]) == 2
    err = capsys.readouterr().err
    assert "plugin validation is not available" in err and "plugins package" in err and "Traceback" not in err


def test_the_subcommand_requires_validate(capsys):
    with pytest.raises(SystemExit) as e:
        main(["plugin"])
    assert e.value.code == 2
