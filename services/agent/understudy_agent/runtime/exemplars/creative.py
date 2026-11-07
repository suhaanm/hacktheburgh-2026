"""Creative exemplar (BGA-6, P2): a short weekly write-up drafted from digest records, citing digest ids only.

The records hold fixed-vocabulary fields and an id each (`understudy_engine.localmodel` digests have this shape); no
commit message, name or path is involved. A vetted script writes the draft; CODE checks that every id in it is one of the
supplied ids, that the cited list matches the draft, and that every count in it is right.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..results import VerifyCtx, register_schema, register_verifier
from ..spec import Check, RoleDef, register_role
from .base import Exemplar, Menu, WorkspaceNeeds, register_exemplar, register_menu, script_text

SUMMARY_V1: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["draft", "cited"],
    "properties": {"draft": {"type": "string", "maxLength": 600},
                   "cited": {"type": "array", "maxItems": 24, "items": {"type": "string", "pattern": "^d_[0-9a-f]{6}$"}}},
}
register_schema("summary_v1", SUMMARY_V1)
register_role(RoleDef("weekly_writer", "Draft a short weekly write-up from digest records, citing record ids only.",
                      frozenset({"write_workspace", "run_python", "emit_result", "list_dir"}), frozenset({"tmp"}),
                      "summary_v1", "weekly_writer"))
register_menu("weekly_writer", Menu(files={"input": "input/digests.json", "script": "summarize.py", "result": "result.json"},
                                    templates={"weekly_summary": script_text("weekly_summary.py")}),
              "Draft a short weekly write-up from the digest records the worker supplied.")
_ID = re.compile(r"d_[0-9a-f]{6}")
_BRACKET = re.compile(r"\[(d_[0-9a-f]{6})\]")


def verify_summary(ctx: VerifyCtx) -> list[Check]:
    digs = json.loads(Path(ctx.params["digests_path"]).read_text())["digests"]
    ids = {d["id"] for d in digs}
    draft, cited = ctx.output["draft"], ctx.output["cited"]
    in_draft = _ID.findall(draft)
    counts: dict[str, int] = {}
    for d in digs:
        counts[d["category"]] = counts.get(d["category"], 0) + 1
    said = {m.group(2): int(m.group(1)) for m in re.finditer(r"(\d+) (feature|fix|refactor|test|docs|chore|revert|other)\b", draft)}
    return [Check(name="cites_only_supplied_ids", ok=bool(in_draft) and set(in_draft) <= ids and set(cited) <= ids),
            Check(name="cited_list_matches_the_draft", ok=set(cited) == set(in_draft) == set(_BRACKET.findall(draft))),
            Check(name="counts_are_right", ok=said == counts and f"{len(digs)} changes" in draft),
            Check(name="no_links_or_addresses", ok=not re.search(r"https?://|@|www\.", draft))]


register_verifier("weekly_writer", verify_summary)


def prepare(params: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    from .fixtures import make_digests

    p = dict(params or {})
    path = run_dir / "fixtures" / "digests.json"
    if p.get("digests"):
        digs = [d for d in p["digests"] if isinstance(d, dict) and re.fullmatch(r"d_[0-9a-f]{6}", str(d.get("id")))]
        if not digs:
            raise ValueError("digests need ids like d_3a1000")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"digests": [{"id": d["id"], "category": str(d.get("category", "other")),
                                                 "size_bucket": str(d.get("size_bucket", "small")),
                                                 "touches_tests": bool(d.get("touches_tests"))} for d in digs]}))
        p["digests"] = len(digs)
    else:
        info = make_digests(path)
        p.update(synthetic=True, truth=info["truth"], digests=len(info["digests"]))
    p["digests_path"] = str(path)
    return p


def needs(role: str, params: dict[str, Any]) -> WorkspaceNeeds:
    return WorkspaceNeeds(inputs=((Path(params["digests_path"]), "digests.json"),))


def mock_steps(role: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"tool": "write_workspace", "file": "script", "template": "weekly_summary"},
            {"tool": "run_python", "file": "script"}, {"tool": "emit_result", "file": "result"}]


register_exemplar(Exemplar(kind="creative.weekly_summary", title="Draft a weekly write-up from digests",
                           describe="Draft a weekly write-up that cites digest ids only.", roles=("weekly_writer",),
                           needs=needs, prepare=prepare, mock_steps=mock_steps, explicit_files=()))
