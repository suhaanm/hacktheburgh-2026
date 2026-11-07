"""Canary flows for the privacy track's measurement (PRV-1): the REAL git flow, run with canaries planted.

``FLOWS`` is discovered by ``understudy_engine.privacy.evaluate`` (``understudy_engine/<layer>/canary_flows.py``). Each flow:
a fixture of commits (author, email, message, customer, file paths) is planted with unique tokens, written into a real git
repository, and sent through the whole layer: git source, digest (the local-model track's), features, comparison with the
reference experts, suggestion selection and wording through ``egress.send(..., port=port)``. Only the model port is faked.
"""
from __future__ import annotations

import tempfile

from ..privacy.testing import CanaryFlow, CapturingPort


def make_fixtures() -> dict:
    """Fresh nested fixtures. 24 commits: all large and none touching a test, so two or more habits are flagged and the layer
    has something to word; messages, names and paths are what the canary kit plants tokens into."""
    return {
        "repo": {"name": "Billing Service"},
        "commits": [
            {"author": "Dev Person", "email": "dev.person@example.test", "message": f"fix rounding bug {i}", "customer": "Some Customer Ltd",
             "files": [{"path": f"src/module{i % 4}/core.py"}, {"path": f"src/module{i % 4}/helpers.py"}],
             "lines": 330 if i % 2 else 14, "minute": 75}
            for i in range(24)
        ],
    }


def run(fixtures: dict, port: CapturingPort) -> dict:
    from . import service, synth

    commits = []
    for c in fixtures["commits"]:
        commits.append({
            "message": f"{c['message']}\n\nCustomer: {c['customer']}\nReported-by: {c['author']} <{c['email']}>",
            "author": c["author"], "email": c["email"], "paths": [f["path"] for f in c["files"]],
            "lines": c["lines"], "minute": c["minute"],
        })
    with tempfile.TemporaryDirectory(prefix="git-canary-") as tmp:
        repo = synth.repo_from_commits(commits, tmp)
        return service.habits_for_repo(repo, label="p_canary", repo_id="r_canary", reword=True, port=port)


FLOWS = [CanaryFlow(name="git.habits", make_fixtures=make_fixtures, run=run, layer="git", kind="integration", min_requests=1, mode="replace")]
