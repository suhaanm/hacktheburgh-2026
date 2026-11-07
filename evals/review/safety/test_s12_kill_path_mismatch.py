"""S-12 (Low): two different data-dir rules. security/paths.data_dir() strips, expands ~ and resolves UNDERSTUDY_DATA_DIR; supervisor.data_dir()
(used by MacActuator, Supervisor and every kill_flag_path() caller) does none of that. With UNDERSTUDY_DATA_DIR="~/und" the services write
the kill file where the pipeline looks and the actuator and watchdog look in a literal ./~/und/KILL. Fakes only."""
from __future__ import annotations

from understudy_agent.security.killflag import is_killed, set_kill
from understudy_agent.supervisor import kill_flag_path


def test_the_actuator_and_the_pipeline_look_for_the_same_kill_file(tmp_path, monkeypatch):
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", " ~/und ")
    set_kill("test")
    assert is_killed(), "the pipeline's own flag is set"
    assert kill_flag_path().exists(), f"MacActuator/Supervisor look at {kill_flag_path()!s}, not where the flag was written"
