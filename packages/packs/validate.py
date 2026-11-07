#!/usr/bin/env python
"""Standalone role pack validator (ROL-1) until the engine's loader exists.

    uv run python packages/packs/validate.py              # every pack, plus the schema examples
    uv run python packages/packs/validate.py PACK_DIR ... # specific pack directories
    uv run python packages/packs/validate.py --quiet

Checks, per pack: pack.yaml against packages/schema/pack.schema.json; every file it points at against
the matching sub-schema; cross-file references (cogs, skills, templates, roles); the mapping's test
vectors through the reference mapper (refmap.py); and that no label vocabulary matches the sensitive
fields list. Across packs: the three packs differ visibly. Exit code 1 on any error.
"""
from __future__ import annotations

import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCHEMA_DIR = ROOT / "packages" / "schema"

sys.path.insert(0, str(HERE))
from refmap import map_events  # noqa: E402

BASE_COGS = ("READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE",
             "COMPARE", "CHECK", "DECIDE", "IDLE", "REVERT", "ASK")
QUESTION_IDS = ["tools", "risky", "tone", "pace", "hours"]
TASK_FILES = {"task.yaml": "task", "household_generator.yaml": "household_generator", "sites.yaml": "sites"}


# ---------------------------------------------------------------- loading helpers

def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


_PACK_SCHEMA: dict | None = None


def pack_schema() -> dict:
    global _PACK_SCHEMA
    if _PACK_SCHEMA is None:
        _PACK_SCHEMA = load_json(SCHEMA_DIR / "pack.schema.json")
    return _PACK_SCHEMA


def def_validator(name: str) -> Draft202012Validator:
    """Validator for one of the $defs in pack.schema.json (sub-file schemas)."""
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": pack_schema()["$defs"]})


def schema_errors(validator: Draft202012Validator, data: Any, where: str) -> list[str]:
    out = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"{where}: {path}: {err.message[:300]}")
    return out


# ---------------------------------------------------------------- one pack

def validate_pack(pack_dir: Path) -> list[str]:
    """Return a list of error strings for one pack directory (empty list means valid)."""
    pack_dir = Path(pack_dir)
    errs: list[str] = []
    name = pack_dir.name
    pack_yaml = pack_dir / "pack.yaml"
    if not pack_yaml.is_file():
        return [f"{name}: pack.yaml missing"]
    try:
        pack = load_yaml(pack_yaml)
    except yaml.YAMLError as e:
        return [f"{name}/pack.yaml: invalid YAML: {e}"]

    errs += schema_errors(Draft202012Validator(pack_schema()), pack, f"{name}/pack.yaml")
    if errs:
        return errs  # structure is wrong; cross checks would only add noise

    if pack["id"] != name:
        errs.append(f"{name}/pack.yaml: id {pack['id']!r} must equal the directory name")

    # --- onboarding
    qs = pack["onboarding"]["questions"]
    if [q["id"] for q in qs] != QUESTION_IDS:
        errs.append(f"{name}: onboarding question ids must be {QUESTION_IDS} in order, got {[q['id'] for q in qs]}")
    for q in qs:
        if q["kind"] in ("multi", "single"):
            values = [o["value"] for o in q["options"]]
            if len(values) != len(set(values)):
                errs.append(f"{name}: question {q['id']} has duplicate option values")
            if q["kind"] == "single" and sum(1 for o in q["options"] if o.get("default")) != 1:
                errs.append(f"{name}: single question {q['id']} must have exactly one default option")
        if q["id"] == "risky":
            for o in q["options"]:
                if "risk_class" not in o or "patterns" not in o:
                    errs.append(f"{name}: risky option {o['value']} needs risk_class and patterns")
        if q["id"] in ("tone", "pace") and q["kind"] != "single":
            errs.append(f"{name}: question {q['id']} must be kind single")
        if q["id"] == "hours" and q["kind"] != "hours":
            errs.append(f"{name}: question hours must be kind hours")
        if q["id"] in ("tools", "risky") and q["kind"] != "multi":
            errs.append(f"{name}: question {q['id']} must be kind multi")

    # --- referenced files
    def need(rel: str, schema_def: str, label: str, kind: str = "yaml") -> Any:
        path = pack_dir / rel
        if not path.is_file():
            errs.append(f"{name}: {label} file {rel} is missing")
            return None
        try:
            data = load_yaml(path) if kind == "yaml" else load_json(path)
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            errs.append(f"{name}/{rel}: cannot parse: {e}")
            return None
        errs.extend(schema_errors(def_validator(schema_def), data, f"{name}/{rel}"))
        return data

    mapping = need(pack["cogs"]["mapping"], "mapping", "mapping")
    steps = need(pack["expert_policy"]["steps"], "expert_steps", "expert steps") if "expert_policy" in pack else None
    routines = need(pack["routines"], "routine_templates", "routines")
    curriculum = need(pack["curriculum"], "curriculum", "curriculum")
    persona = need(pack["persona"], "persona", "persona")
    priors = need(pack["priors"], "priors", "priors")
    sensitive = need(pack["risk_classes"]["sensitive_fields"], "sensitive_fields", "sensitive fields", "json")

    if "tasks" in pack:
        tasks_dir = pack_dir / pack["tasks"]
        if not tasks_dir.is_dir():
            errs.append(f"{name}: tasks directory {pack['tasks']} is missing")
        else:
            for fname, sdef in TASK_FILES.items():
                need(f"{pack['tasks'].rstrip('/')}/{fname}", sdef, f"task file {fname}")

    extra = list(pack["cogs"]["extra"])
    all_cogs = set(BASE_COGS) | set(extra)
    for c in extra:
        if c in BASE_COGS:
            errs.append(f"{name}: extra cog {c} duplicates a base cog")

    def check_cogs(cogs: list[str], where: str) -> None:
        for c in cogs:
            if c not in all_cogs:
                errs.append(f"{name}: {where}: unknown cog {c}")

    # --- risk classes and sensitive patterns
    for cls in ("irreversible", "outward"):
        for pat in pack["risk_classes"][cls]:
            try:
                re.compile(pat, re.I)
            except re.error as e:
                errs.append(f"{name}: risk_classes.{cls} pattern {pat!r} is not a regex: {e}")
    global_sensitive = load_json(SCHEMA_DIR / "sensitive_fields.json")
    sens_patterns: list[re.Pattern] = []
    for src in (global_sensitive, sensitive or {}):
        for pat in src.get("patterns", []):
            try:
                sens_patterns.append(re.compile(pat, re.I))
            except re.error as e:
                errs.append(f"{name}: sensitive pattern {pat!r} is not a regex: {e}")

    # --- mapping
    domain_roles: set[str] = set()
    if mapping and not errs:
        domain_roles = set(mapping["domain_roles"])
        label_roles = set(mapping["label_roles"])
        produced: set[str] = set()
        seen_rule_ids: set[str] = set()
        for section in ("role_rules", "base_rules"):
            for rule in mapping[section]:
                rid = rule["id"]
                if rid in seen_rule_ids:
                    errs.append(f"{name}: mapping rule id {rid} is used twice")
                seen_rule_ids.add(rid)
                if "cog" in rule:
                    check_cogs([rule["cog"]], f"mapping rule {rid}")
                    produced.add(rule["cog"])
                when = rule["when"]
                for key, roles in (("domain_role", domain_roles), ("label_role", label_roles)):
                    if key in when:
                        for r in ([when[key]] if isinstance(when[key], str) else when[key]):
                            if r not in roles:
                                errs.append(f"{name}: mapping rule {rid}: {key} {r!r} is not declared")
                for key in ("prev_cog", "not_prev_cog"):
                    if key in when:
                        check_cogs([when[key]] if isinstance(when[key], str) else when[key], f"mapping rule {rid}.{key}")
        for c in extra:
            if c not in produced:
                errs.append(f"{name}: extra cog {c} is never produced by a mapping rule")
        for vocab_role, spec in mapping["label_roles"].items():
            for word in spec["vocab"]:
                if word != word.strip().lower():
                    errs.append(f"{name}: label vocab {word!r} in {vocab_role} must be trimmed lower case")
                for pat in sens_patterns:
                    if pat.search(word):
                        errs.append(f"{name}: label vocab {word!r} in {vocab_role} matches sensitive pattern {pat.pattern!r}")
        for ex in mapping.get("examples", []):
            if len(ex["events"]) != len(ex["expect"]):
                errs.append(f"{name}: mapping example {ex['name']!r}: events and expect differ in length")
                continue
            got = map_events(mapping, ex["events"], ex["hash_roles"])
            if got != ex["expect"]:
                errs.append(f"{name}: mapping example {ex['name']!r}: expected {ex['expect']} but reference mapper gave {got}")
        if not mapping.get("examples"):
            errs.append(f"{name}: mapping.yaml has no test vectors (examples)")

    # --- onboarding options against the mapping and the risk classes
    if mapping and domain_roles:
        for q in qs:
            for o in q.get("options", []):
                if "domain_role" in o and o["domain_role"] not in domain_roles:
                    errs.append(f"{name}: onboarding option {o['value']}: domain_role {o['domain_role']!r} is not in mapping.yaml")

    # --- curriculum
    skill_ids: set[str] = set()
    if curriculum and not errs:
        sk = curriculum["skills"]
        skill_ids = {s["id"] for s in sk}
        if len(skill_ids) != len(sk):
            errs.append(f"{name}: curriculum has duplicate skill ids")
        if sorted(s["order"] for s in sk) != list(range(1, len(sk) + 1)):
            errs.append(f"{name}: curriculum order must be 1..{len(sk)} without gaps")
        for s in sk:
            check_cogs(s["cogs"], f"curriculum skill {s['id']}")
            for p in s["prerequisites"]:
                if p not in skill_ids:
                    errs.append(f"{name}: curriculum skill {s['id']}: unknown prerequisite {p}")
                elif next(x for x in sk if x["id"] == p)["order"] >= s["order"]:
                    errs.append(f"{name}: curriculum skill {s['id']}: prerequisite {p} must come earlier")

    # --- expert steps
    if steps and not errs:
        check_ids = [c["id"] for c in steps["checks"]]
        if len(check_ids) != len(set(check_ids)):
            errs.append(f"{name}: expert steps have duplicate check ids")
        ids = set(check_ids)
        graph = {c["id"]: list(c["after"]) for c in steps["checks"]}
        for c in steps["checks"]:
            check_cogs(c["cogs"], f"expert check {c['id']}")
            for a in c["after"]:
                if a not in ids:
                    errs.append(f"{name}: expert check {c['id']}: unknown 'after' {a}")
            if "skill" in c and curriculum and c["skill"] not in skill_ids:
                errs.append(f"{name}: expert check {c['id']}: unknown skill {c['skill']}")
            if c.get("critical") and not c["required"]:
                errs.append(f"{name}: expert check {c['id']} is critical but not required")
        if _has_cycle(graph):
            errs.append(f"{name}: expert steps 'after' relations contain a cycle")
        for r in steps.get("allowed_reorderings", []):
            for m in r.get("permutable", []):
                if m not in ids:
                    errs.append(f"{name}: allowed_reordering {r['id']}: unknown check {m}")
        if steps["coverage"] != pack["expert_policy"]["coverage"]:
            errs.append(f"{name}: expert steps coverage {steps['coverage']!r} disagrees with pack.yaml")

    # --- routines
    template_ids: set[str] = set()
    if routines and not errs:
        for t in routines["templates"]:
            if t["id"] in template_ids:
                errs.append(f"{name}: duplicate routine template {t['id']}")
            template_ids.add(t["id"])
            check_cogs(t["cogs"], f"routine template {t['id']}")
            check_cogs(t.get("skill_cogs", []), f"routine template {t['id']}.skill_cogs")
            check_cogs(t.get("judgement_cogs", []), f"routine template {t['id']}.judgement_cogs")
            for c in t.get("skill_cogs", []):
                if c not in t["cogs"]:
                    errs.append(f"{name}: routine template {t['id']}: skill_cog {c} is not in its cogs")
            if t["learning_relevant"] and not t.get("skill_cogs"):
                errs.append(f"{name}: routine template {t['id']}: learning_relevant needs skill_cogs")
            if len(set(t["cogs"])) < 2:
                errs.append(f"{name}: routine template {t['id']}: a template of one repeated cog is not matchable")
        check_cogs(routines.get("defaults", {}).get("judgement_cogs", []), "routines.defaults.judgement_cogs")

    # --- persona
    if persona and not errs:
        check_cogs(list(persona["cog_dwell_s"]), "persona.cog_dwell_s")
        for d in persona["apprentice"]["deficits"]:
            check_cogs(d["cogs"], f"persona deficit {d['id']}")
            if "insert_before" in d:
                check_cogs([d["insert_before"]], f"persona deficit {d['id']}.insert_before")
            if d["kind"] == "insert" and "insert_before" not in d:
                errs.append(f"{name}: persona deficit {d['id']}: kind insert needs insert_before")
            if d["kind"] == "slow" and "multiplier" not in d:
                errs.append(f"{name}: persona deficit {d['id']}: kind slow needs multiplier")
            if curriculum and d["skill"] not in skill_ids:
                errs.append(f"{name}: persona deficit {d['id']}: unknown skill {d['skill']}")
        for r in persona["planted_routines"]:
            if routines and r["template"] not in template_ids:
                errs.append(f"{name}: persona planted routine {r['id']}: unknown template {r['template']}")

    if priors and not errs:
        check_cogs(list(priors.get("cog_dwell_s", {})), "priors.cog_dwell_s")

    # --- tasks (deep packs)
    if pack["depth"] == "deep" and "tasks" in pack and not errs:
        sites = load_yaml(pack_dir / pack["tasks"] / "sites.yaml")
        for s in sites["sites"]:
            if s["domain_role"] not in domain_roles:
                errs.append(f"{name}: sites.yaml: site {s['id']} domain_role {s['domain_role']!r} is not in mapping.yaml")
        task = load_yaml(pack_dir / pack["tasks"] / "task.yaml")
        if persona and task["id"] != persona.get("task"):
            errs.append(f"{name}: persona.task {persona.get('task')!r} must equal tasks/task.yaml id {task['id']!r}")
        if steps and task["id"] != steps["task"]:
            errs.append(f"{name}: expert_steps.task {steps['task']!r} must equal tasks/task.yaml id {task['id']!r}")
    return errs


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    indeg = {n: 0 for n in graph}
    for n, deps in graph.items():
        for d in deps:
            if d in indeg:
                indeg[n] += 1
    q = deque(n for n, k in indeg.items() if k == 0)
    seen = 0
    while q:
        n = q.popleft()
        seen += 1
        for m, deps in graph.items():
            if n in deps:
                indeg[m] -= 1
                if indeg[m] == 0:
                    q.append(m)
    return seen != len(graph)


# ---------------------------------------------------------------- across packs

def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def compare_packs(packs: dict[str, dict]) -> list[str]:
    """The packs must differ visibly in onboarding, extra cogs, risk classes and tone defaults."""
    errs: list[str] = []
    names = sorted(packs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pa, pb = packs[a], packs[b]
            tag = f"{a} vs {b}"
            ea, eb = set(pa["cogs"]["extra"]), set(pb["cogs"]["extra"])
            if ea & eb:
                errs.append(f"{tag}: extra cogs overlap: {sorted(ea & eb)}")
            ia, ib = set(pa["risk_classes"]["irreversible"]), set(pb["risk_classes"]["irreversible"])
            if _jaccard(ia, ib) > 0.4:
                errs.append(f"{tag}: irreversible risk classes too similar (Jaccard {_jaccard(ia, ib):.2f})")
            ta, tb = pa["tone_defaults"], pb["tone_defaults"]
            if (ta["length"], ta["voice"], ta.get("pace")) == (tb["length"], tb["voice"], tb.get("pace")):
                errs.append(f"{tag}: tone defaults are identical")
            qa = {q["id"]: q for q in pa["onboarding"]["questions"]}
            qb = {q["id"]: q for q in pb["onboarding"]["questions"]}
            for qid in ("tools", "risky"):
                va = {o["value"] for o in qa[qid]["options"]}
                vb = {o["value"] for o in qb[qid]["options"]}
                if _jaccard(va, vb) > 0.4:
                    errs.append(f"{tag}: question {qid} options too similar (Jaccard {_jaccard(va, vb):.2f})")
            for qid in QUESTION_IDS:
                if qa[qid]["prompt"] == qb[qid]["prompt"]:
                    errs.append(f"{tag}: question {qid} has the same prompt")
            if qa["hours"]["default_hours"] == qb["hours"]["default_hours"]:
                errs.append(f"{tag}: default hours are identical")
    return errs


# ---------------------------------------------------------------- schema package self-checks

EXAMPLE_SCHEMAS = {
    "steps.": "steps.schema.json",
    "routine.": "routine.schema.json",
    "queue_item.": "queue_item.schema.json",
    "memory.frontmatter.": "memory.frontmatter.schema.json",
    "ext_rect.": "ext_rect.schema.json",
    "event.": "event.schema.json",
}


def validate_schema_package() -> list[str]:
    """Every schema is itself valid JSON Schema, the lead's files still validate, and examples pass."""
    errs: list[str] = []
    for p in sorted(SCHEMA_DIR.glob("*.schema.json")):
        try:
            Draft202012Validator.check_schema(load_json(p))
        except Exception as e:  # noqa: BLE001
            errs.append(f"{p.name}: not a valid JSON Schema: {e}")
    errs += schema_errors(def_validator("sensitive_fields"), load_json(SCHEMA_DIR / "sensitive_fields.json"),
                          "schema/sensitive_fields.json")
    ex_dir = SCHEMA_DIR / "examples"
    if ex_dir.is_dir():
        for p in sorted(ex_dir.glob("*.json")):
            if p.name.startswith("invalid."):
                continue
            prefix = next((k for k in EXAMPLE_SCHEMAS if p.name.startswith(k)), None)
            if prefix is None:
                errs.append(f"schema/examples/{p.name}: no schema is registered for this file name")
                continue
            schema = load_json(SCHEMA_DIR / EXAMPLE_SCHEMAS[prefix])
            errs += schema_errors(Draft202012Validator(schema), load_json(p), f"schema/examples/{p.name}")
    return errs


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    args = [a for a in argv if not a.startswith("--")]
    pack_dirs = [Path(a) for a in args] if args else sorted(
        d for d in HERE.iterdir() if d.is_dir() and (d / "pack.yaml").is_file())
    failed = False

    def report(label: str, errs: list[str]) -> None:
        nonlocal failed
        if errs:
            failed = True
            print(f"FAIL  {label}")
            for e in errs:
                print(f"      {e}")
        elif not quiet:
            print(f"ok    {label}")

    report("schema package", validate_schema_package())
    loaded: dict[str, dict] = {}
    for d in pack_dirs:
        report(f"pack {d.name}", validate_pack(d))
        try:
            loaded[d.name] = load_yaml(d / "pack.yaml")
        except Exception:  # noqa: BLE001
            pass
    if len(loaded) > 1:
        report("packs differ visibly", compare_packs(loaded))
    if not pack_dirs:
        print("FAIL  no packs found")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
