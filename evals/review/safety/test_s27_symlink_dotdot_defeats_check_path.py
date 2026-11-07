"""S-27 (Low, needs a symlink that already exists): the identity check normalises `..` LEXICALLY (os.path.abspath) before it stats each prefix, but the
operating system resolves `..` after following a symlink. `<symlink to data/queue>/../.token` is `data/.token` to the kernel and `<tmp>/links/.token` to
check_path, which allows it. Nothing the agent's own tools can do creates such a symlink today (the sandbox cannot read through one), so this is
hardening: stat the FULL path with the kernel (os.stat / os.path.realpath) as well as each lexical prefix. Temp dir only."""
from __future__ import annotations

import os

from understudy_agent.security.paths import data_dir
from understudy_agent.security.settings import SettingsGuard


def test_a_symlink_followed_by_dotdot_reaches_a_protected_file_that_check_path_allows(tmp_path):
    d = data_dir()
    (d / "queue").mkdir(parents=True, exist_ok=True)
    (d / ".token").write_text("secret")
    links = tmp_path / "links"
    links.mkdir()
    os.symlink(d / "queue", links / "L")
    sneaky = str(links / "L") + "/../.token"
    assert open(sneaky).read() == "secret"                       # the kernel resolves it to the token
    assert not SettingsGuard().check_path(sneaky).allowed, "check_path allowed a path the kernel resolves to data/.token"
