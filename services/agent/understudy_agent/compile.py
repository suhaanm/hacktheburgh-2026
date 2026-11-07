"""Compile an L1 recording into a step-DSL bundle (HND-3).

    recording (packages/schema/recording.schema.json)  ->  draft bundle (packages/schema/steps.schema.json)
      -> static validation (schema, params, selectors are CSS, no code)
      -> DRY RUN on the sandbox with a synthetic household: every selector must match exactly one element, every
         precondition and postcondition must hold, the result fields must pass the code check, and an irreversible
         step is never executed (the dry run stops in front of it)
      -> saved to data/routines/<id>/steps.json (or steps.<site>.json)

A model may DRAFT the mapping from recorded field slots to household parameters when the rules cannot decide; code
validates the draft. Model-generated code is never executed: bundles are data.

The health-related "limited capability" question matches the sensitive-field list, so the recorder never captures it.
Compile therefore takes that field from the household parameters, never from the recording: if the recording has no
step for it, a `select` step is inserted at the position the site's page order puts it.
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jsonschema

from .completion import validate_result_fields
from .models.port import ModelPort
from .sandbox_sites.bundles import CANONICAL_PARAMS
from .sandbox_sites.households import Household
from .sandbox_sites.oracle import site_expected
from .sandbox_sites.recordings import slot_name
from .sandbox_sites.specs import SITES, site_base_urls
from .security.labels import IRREVERSIBLE_CLASSES, OUTWARD_CLASSES, classify_label
from .supervisor import data_dir, repo_root
from .tiers.base import GateStop, TierError
from .tiers.dsl import DslRuntime, goto_hosts, run_bundle, to_internal, validate_bundle
from .tiers.heuristic import param_for

ENUMS = {"adults": ["1", "2"], "limited_capability": ["no", "yes"], "tenure": ["rent", "own"],
         "bedrooms": ["1", "2", "3", "4"]}
KNOWN_IRREVERSIBLE_SELECTORS = {"#submit-note", "#cn-submit"}
FROM_HOUSEHOLD_ONLY = ("limited_capability",)  # sensitive by wording: never recorded, always from the household

PARAM_MAP_SCHEMA: dict[str, Any] = {
    "title": "param_mapping",
    "type": "object",
    "properties": {"mappings": {"type": "array", "items": {"type": "object", "properties": {
        "slot": {"type": "string", "maxLength": 40}, "canonical": {"type": "string", "maxLength": 40}},
        "required": ["slot", "canonical"]}}},
    "required": ["mappings"],
}


@dataclass
class CompileReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    site: str | None = None
    layout: str | None = None
    mapped: dict[str, str] = field(default_factory=dict)
    model_drafted: list[str] = field(default_factory=list)
    inserted_from_household: list[str] = field(default_factory=list)
    dry_run: dict[str, Any] = field(default_factory=dict)
    path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ----------------------------------------------------------------------------- schemas
def steps_schema() -> dict[str, Any]:
    return json.loads((repo_root() / "packages" / "schema" / "steps.schema.json").read_text())


def recording_schema() -> dict[str, Any]:
    return json.loads((repo_root() / "packages" / "schema" / "recording.schema.json").read_text())


def validate_recording(rec: dict[str, Any]) -> list[str]:
    v = jsonschema.Draft202012Validator(recording_schema())
    return [f"{'/'.join(str(x) for x in e.path) or 'recording'}: {e.message[:140]}" for e in v.iter_errors(rec)]


def validate_platform_bundle(bundle: dict[str, Any]) -> list[str]:
    """Schema check plus the semantic checks the schema cannot express."""
    errs = [f"{'/'.join(str(x) for x in e.path) or 'bundle'}: {e.message[:140]}"
            for e in jsonschema.Draft202012Validator(steps_schema()).iter_errors(bundle)]
    if errs:
        return errs[:8]
    declared = set(bundle["params"])
    for st in bundle["steps"]:
        for k in ("param", "url_param"):
            if k in st and st[k] not in declared:
                errs.append(f"{st['id']}: undeclared {k} {st[k]!r}")
    errs += validate_bundle(bundle)
    return errs


# ----------------------------------------------------------------------------- slot to household parameter
def detect_site(rec: dict[str, Any], base_urls: dict[str, str]) -> str | None:
    first = next((s for s in rec["steps"] if s["op"] == "goto"), None)
    if not first:
        return None
    host = urlsplit(first["url"])
    for site, u in base_urls.items():
        b = urlsplit(u)
        if (host.hostname, host.port) == (b.hostname, b.port):
            return site
    return None


def detect_layout(rec: dict[str, Any], site: str) -> str:
    sels = {s.get("selector") for s in rec["steps"]}
    spec = SITES[site]
    v2 = sum(1 for p in spec.fields_v2 if spec.selector(p, "v2") in sels)
    v1 = sum(1 for p in spec.fields_v1 if spec.selector(p, "v1") in sels)
    return "v2" if v2 > v1 else "v1"


def rule_map(rec: dict[str, Any], site: str | None) -> dict[str, str]:
    """slot -> canonical household parameter, from the site spec or from the label rules. Unknown slots are absent."""
    out: dict[str, str] = {}
    keys: dict[str, str] = {}
    if site:
        for layout in ("v1", "v2"):
            for canon, key in SITES[site].fields(layout).items():
                keys[slot_name(key)] = canon
    for st in rec["steps"]:
        slot = st.get("param")
        if not slot or slot in out:
            continue
        if slot in keys:
            out[slot] = keys[slot]
        elif st.get("name"):
            canon, _ = param_for(st["name"], st.get("role", "textbox"))
            if canon in CANONICAL_PARAMS:
                out[slot] = canon
    return out


def draft_map(model: ModelPort | None, unmapped: list[str]) -> dict[str, str]:
    """A model may propose canonical names for slots the rules could not place; code validates every answer."""
    if not unmapped or model is None:
        return {}
    msgs = [{"role": "system", "content": "Map each recorded form-field slot to one household parameter. Only use the "
                                          "listed names. Return mappings for the slots you can place."},
            {"role": "user", "content": json.dumps({"slots": unmapped, "household_parameters": CANONICAL_PARAMS})}]
    try:
        out = model.plan(msgs, PARAM_MAP_SCHEMA)
    except Exception:  # noqa: BLE001
        return {}
    good: dict[str, str] = {}
    for m in out.get("mappings", []) if isinstance(out, dict) else []:
        if m.get("slot") in unmapped and m.get("canonical") in CANONICAL_PARAMS:
            good[m["slot"]] = m["canonical"]
    return good


def insert_household_only(rec: dict[str, Any], mapping: dict[str, str], site: str | None, layout: str,
                          rep: CompileReport) -> dict[str, Any]:
    """Make sure every FROM_HOUSEHOLD_ONLY field has a step, taken from the household and never from the recording."""
    if site is None:
        return rec
    spec = SITES[site]
    order = [p for page in spec.steps for p in page]
    rec = copy.deepcopy(rec)
    for canon in FROM_HOUSEHOLD_ONLY:
        if canon not in order:
            continue
        # a recorded step for it (if any) is dropped: the value never comes from the recording
        rec["steps"] = [s for s in rec["steps"] if mapping.get(s.get("param", ""), None) != canon]
        recorded = [(i, mapping[s["param"]]) for i, s in enumerate(rec["steps"]) if s.get("param") in mapping]
        before = [i for i, c in recorded if c in order and order.index(c) < order.index(canon)]
        at = (max(before) + 1) if before else 1
        prev_t = rec["steps"][at - 1].get("t_ms", 0)
        slot = slot_name(spec.fields(layout)[canon])
        step = {"op": "select", "t_ms": prev_t + 1, "selector": spec.selector(canon, layout), "param": slot}
        rec["steps"].insert(at, step)
        mapping[slot] = canon
        rep.inserted_from_household.append(canon)
        rep.warnings.append(f"{canon} is taken from the household parameters, not from the recording")
    return rec


# ----------------------------------------------------------------------------- the draft
def build_bundle(rec: dict[str, Any], mapping: dict[str, str], *, site: str | None, layout: str) -> dict[str, Any]:
    spec = SITES[site] if site else None
    params: dict[str, Any] = {}
    for canon in dict.fromkeys(mapping[s["param"]] for s in rec["steps"] if s.get("param")):
        decl: dict[str, Any] = ({"type": "enum", "values": ENUMS[canon]} if canon in ENUMS else {"type": "string"})
        decl["source"] = f"household.params.{canon}"
        if spec and canon in spec.transforms:
            mul, nd = spec.transforms[canon]
            decl["transform"] = {"mul": mul, "round": nd}
        params[canon] = decl
    recorded = rec["steps"]
    steps: list[dict[str, Any]] = []

    def next_selector(i: int) -> str | None:
        for st in recorded[i + 1:]:
            if st.get("selector"):
                return st["selector"]
            if st["op"] == "goto":
                return None
        return None

    for i, r in enumerate(recorded):
        sid = f"s{len(steps) + 1}"
        op = r["op"]
        step: dict[str, Any] = {"id": sid, "op": op}
        sel = r.get("selector")
        if op == "goto":
            step["url"] = r["url"]
            step["precondition"] = {"always": True}
            nxt = next_selector(i)
            step["postcondition"] = {"selector_visible": nxt} if nxt else {"always": True}
        else:
            if sel:
                step["selector"] = sel
            else:
                step["role"], step["name"] = r["role"], r["name"]
            step["precondition"] = {"selector_visible": sel} if sel else {"always": True}
            if op in ("fill", "select"):
                canon = mapping[r["param"]]
                step["param"] = canon
                transformed = "transform" in params[canon]
                step["postcondition"] = ({"field_equals": {"selector": sel, "param": canon}}
                                         if sel and not transformed else
                                         ({"selector_visible": sel} if sel else {"always": True}))
            else:  # click
                nxt = next_selector(i)
                if sel == "#cliff-btn":
                    nxt = "#cliff-panel"
                step["postcondition"] = {"selector_visible": nxt} if nxt else {"always": True}
                risky = classify_label(r.get("name") or "") & (IRREVERSIBLE_CLASSES | OUTWARD_CLASSES)
                if risky or sel in KNOWN_IRREVERSIBLE_SELECTORS:
                    step["irreversible"] = True
        steps.append(step)
    # reading the result is part of the routine: the compiled script ends by reading what the page shows
    if spec:
        res = spec.result(layout)
        steps.append({"id": f"s{len(steps) + 1}", "op": "wait_for", "selector": res["amount"],
                      "precondition": {"always": True}, "postcondition": {"selector_visible": res["amount"]}})
        for name in ("amount", "status", "ref"):
            steps.append({"id": f"s{len(steps) + 1}", "op": "extract", "name": name, "selector": res[name],
                          "precondition": {"selector_visible": res[name]}, "postcondition": {"always": True}})
        steps.append({"id": f"s{len(steps) + 1}", "op": "checkpoint", "name": "result_read", "resumable": True,
                      "precondition": {"always": True}, "postcondition": {"always": True}})
    else:
        steps.append({"id": f"s{len(steps) + 1}", "op": "checkpoint", "name": "recorded_steps_done", "resumable": True,
                      "precondition": {"always": True}, "postcondition": {"always": True}})
    title = f"{spec.name} ({layout})" if spec else f"Recorded routine {rec['routine_id']}"
    return {"schema": 1, "id": rec["routine_id"], "role": rec["role"], "title": title[:100],
            "created_from": rec["recording_id"], "never": ["submit", "submit to claimant record"],
            "params": params, "steps": steps}


def compile_draft(rec: dict[str, Any], *, base_urls: dict[str, str] | None = None,
                  model: ModelPort | None = None) -> tuple[dict[str, Any] | None, CompileReport]:
    rep = CompileReport(ok=False)
    errs = validate_recording(rec)
    if errs:
        rep.errors = ["recording: " + e for e in errs[:5]]
        return None, rep
    site = detect_site(rec, base_urls or site_base_urls())
    layout = detect_layout(rec, site) if site else "v1"
    rep.site, rep.layout = site, layout
    mapping = rule_map(rec, site)
    slots = list(dict.fromkeys(s["param"] for s in rec["steps"] if s.get("param")))
    unmapped = [s for s in slots if s not in mapping]
    drafted = draft_map(model, unmapped)
    mapping.update(drafted)
    rep.model_drafted = sorted(drafted)
    still = [s for s in slots if s not in mapping]
    if still:
        rep.errors.append(f"cannot place field slot(s) {still} on a household parameter")
        return None, rep
    rec = insert_household_only(rec, mapping, site, layout, rep)
    rep.mapped = dict(mapping)
    bundle = build_bundle(rec, mapping, site=site, layout=layout)
    errs = validate_platform_bundle(bundle)
    if errs:
        rep.errors += ["bundle: " + e for e in errs]
        return None, rep
    return bundle, rep


# ----------------------------------------------------------------------------- dry run
async def dry_run(bundle: dict[str, Any], *, household: Household, site: str | None, host: Any, model: ModelPort,
                  base_url: str = "", audit: Any = None, queue: Any = None) -> dict[str, Any]:
    """Run the bundle on the sandbox. Irreversible steps are never executed."""
    import tempfile

    from .audit import AuditLog
    from .queue import ApprovalQueue
    from .tiers.safety import Guard

    if audit is None:  # a dry run is not a production action: keep it out of the real audit log and morning report
        scratch = Path(tempfile.mkdtemp(prefix="understudy-dry-"))
        audit, queue = AuditLog(scratch / "audit.jsonl"), ApprovalQueue(scratch / "queue")
    ctx = await host.new_context()
    try:
        page = await ctx.new_page()
        guard = Guard(model, run_id="r_compile_dry", mode="compiled", audit=audit, queue=queue,
                      recorded_hosts=frozenset(goto_hosts(to_internal(bundle))))
        rt = DslRuntime(page=page, params=household.params(), base_url=base_url, navigator="dry-run", guard=guard,
                        stop_before_irreversible=True, pre_timeout_ms=2500, post_timeout_ms=4000)
        res = await run_bundle(bundle, rt)
    finally:
        await ctx.close()
    out: dict[str, Any] = {"steps_run": res.steps_run, "outputs": res.outputs, "checkpoints": res.checkpoints,
                           "stopped_before": res.stopped_before or None, "matches_expected": None}
    if site and {"amount", "status", "ref"} <= set(res.outputs):
        fields, problems = validate_result_fields(site, res.outputs)
        want = site_expected(site, household)["uc_monthly"]
        out["matches_expected"] = bool(fields and abs(fields.amount - want) <= 0.06)
        out["problems"] = problems
    return out


async def compile_and_check(rec: dict[str, Any], *, model: ModelPort, host: Any, household: Household,
                            base_urls: dict[str, str] | None = None, audit: Any = None, queue: Any = None
                            ) -> tuple[dict[str, Any] | None, CompileReport]:
    urls = base_urls or site_base_urls()
    bundle, rep = compile_draft(rec, base_urls=urls, model=model)
    if bundle is None:
        return None, rep
    try:
        rep.dry_run = await dry_run(bundle, household=household, site=rep.site, host=host, model=model, audit=audit,
                                    queue=queue)
    except GateStop as exc:
        rep.errors.append(f"dry run: the gate stopped a step ({getattr(exc.decision, 'verdict', '')}); mark it irreversible")
        return None, rep
    except (TierError, ValueError) as exc:
        rep.errors.append(f"dry run failed: {type(exc).__name__}: {str(exc)[:140]}")
        return None, rep
    except Exception as exc:  # noqa: BLE001 - selector problems and timeouts are compile failures, not crashes
        rep.errors.append(f"dry run failed: {type(exc).__name__}: {str(exc)[:140]}")
        return None, rep
    if rep.site and rep.dry_run.get("matches_expected") is not True:
        rep.errors.append("dry run did not reproduce the site's documented result")
        return None, rep
    rep.ok = True
    return bundle, rep


# ----------------------------------------------------------------------------- persistence
def routine_dir(routine_id: str, root: Path | None = None) -> Path:
    return (root or data_dir()) / "routines" / routine_id


def save_bundle(bundle: dict[str, Any], *, name: str | None = None, root: Path | None = None) -> Path:
    """data/routines/<id>/steps.json, or steps.<name>.json for further sites of the same routine."""
    d = routine_dir(bundle["id"], root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / (f"steps.{name}.json" if name else "steps.json")
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(bundle, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def load_bundles(routine_id: str, root: Path | None = None) -> dict[str, dict[str, Any]]:
    d = routine_dir(routine_id, root)
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(d.glob("steps*.json")):
        m = re.fullmatch(r"steps(?:\.([a-z0-9_]+))?\.json", p.name)
        if m:
            out[m.group(1) or "primary"] = json.loads(p.read_text())
    return out


def load_recording(routine_id: str, root: Path | None = None) -> dict[str, Any] | None:
    p = routine_dir(routine_id, root) / "recording.json"
    return json.loads(p.read_text()) if p.exists() else None


def bundles_by_site(routine_id: str, root: Path | None = None) -> dict[str, dict[str, Any]]:
    """The routine's bundles keyed by site. `steps.json` is the first calculator (site a) unless a `steps.a.json`
    exists; `steps.<site>.json` are the others."""
    got = load_bundles(routine_id, root)
    primary = got.pop("primary", None)
    if primary is not None and "a" not in got:
        got = {"a": primary, **got}
    return dict(sorted(got.items()))
